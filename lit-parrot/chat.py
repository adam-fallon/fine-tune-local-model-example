import json
import re
import sys
import time
import warnings
from pathlib import Path
from typing import Optional, Tuple, List

import lightning as L
import torch

from lit_parrot import Parrot, Tokenizer, Config
from lit_parrot.utils import EmptyInitOnDevice, lazy_load, check_valid_checkpoint_dir


@torch.no_grad()
def generate(
    model: Parrot,
    idx: torch.Tensor,
    max_new_tokens: int,
    *,
    max_seq_length: Optional[int] = None,
    temperature: float = 1.0,
    top_k: Optional[int] = None,
    stop_tokens: Tuple[List[int], ...] = tuple(),
):
    """Takes a conditioning sequence (prompt) as input and continues to generate as many tokens as possible.

    Args:
        model: The model to use.
        idx: Tensor of shape (T) with indices of the prompt sequence.
        max_new_tokens: The number of new tokens to generate.
        max_seq_length: The maximum sequence length allowed.
        temperature: Scales the predicted logits by 1 / temperature
        top_k: If specified, only sample among the tokens with the k highest probabilities
        stop_tokens: If specified, stop generating any more token once one of this list is generated.
    """
    T = idx.size(0)
    T_new = T + max_new_tokens
    if max_seq_length is None:
        max_seq_length = min(T_new, model.config.block_size)
    # otherwise this would use more memory than necessary
    assert max_seq_length <= T_new

    device = idx.device
    stop_tokens = [torch.tensor(tokens, device=device) for tokens in stop_tokens]
    input_pos = torch.arange(0, T, device=device)

    # buffer holds the tokens that haven't been yield yet
    buffer_length = max((len(tokens) for tokens in stop_tokens), default=1)
    buffer = torch.full((buffer_length,), -999, device=device)  # fill with non-existing token

    if idx.device.type == "xla":
        import torch_xla.core.xla_model as xm

        xm.mark_step()

    yield_i = -1
    for t in range(max_new_tokens):
        # forward
        logits = model(idx.view(1, -1), max_seq_length, input_pos)
        logits = logits[0, -1] / temperature

        # optionally crop the logits to only the top k options
        if top_k is not None:
            v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
            logits = torch.where(logits < v[[-1]], -float("Inf"), logits)

        probs = torch.nn.functional.softmax(logits, dim=-1)
        idx = torch.multinomial(probs, num_samples=1)

        # advance
        input_pos = input_pos[-1:] + 1

        if idx.device.type == "xla":
            xm.mark_step()

        # concatenate the new generation
        buffer[min(t, buffer_length - 1)] = idx

        # check the stop condition
        for tokens in stop_tokens:
            l = len(tokens)
            if torch.equal(buffer[-l:], tokens):
                # stop token hit, yield any leftovers that aren't part of it
                if buffer_length > l:  # avoid an empty yield
                    yield buffer[:-l]
                return
        # if the buffer is full
        if t - yield_i >= buffer_length:
            # we know this idx is not part of stop tokens, safe to yield
            yield buffer[0]
            # roll once to the left, as next generation will be put at the end
            buffer = torch.roll(buffer, -1, 0)
            yield_i += 1


def main(
    *,
    top_k: int = 200,
    temperature: float = 0.8,
    checkpoint_dir: Path = Path(f"checkpoints/stabilityai/stablelm-tuned-alpha-3b"),
    quantize: Optional[str] = None,
) -> None:
    """Starts a conversation with a tuned Parrot model.

    Args:
        top_k: The number of top most probable tokens to consider in the sampling process.
        temperature: A value controlling the randomness of the sampling process. Higher values result in more random
            samples.
        checkpoint_dir: The checkpoint directory to load.
        quantize: Whether to quantize the model and using which method:
            ``"llm.int8"``: LLM.int8() mode,
            ``"gptq.int4"``: GPTQ 4-bit mode.
    """
    check_valid_checkpoint_dir(checkpoint_dir)

    with open(checkpoint_dir / "lit_config.json") as fp:
        config = Config(**json.load(fp))

    fabric = L.Fabric(devices=1)
    dtype = torch.bfloat16 if fabric.device.type == "cuda" and torch.cuda.is_bf16_supported() else torch.float32

    checkpoint_path = checkpoint_dir / "lit_model.pth"
    print(f"Loading model {str(checkpoint_path)!r} with {config.__dict__}", file=sys.stderr)
    with EmptyInitOnDevice(device=fabric.device, dtype=dtype, quantization_mode=quantize):
        model = Parrot(config)
    with lazy_load(checkpoint_path) as checkpoint:
        model.load_state_dict(checkpoint)

    model.eval()
    model = fabric.setup_module(model)

    tokenizer = Tokenizer(checkpoint_dir / "tokenizer.json", checkpoint_dir / "tokenizer_config.json")
    system_prompt, stop_tokens = prompt_config(checkpoint_dir, tokenizer)

    while True:
        try:
            prompt = input(">> Prompt: ")
        except KeyboardInterrupt:
            break
        if not prompt:
            break
        prompt = system_prompt.format(prompt=prompt)
        encoded_prompt = tokenizer.encode(prompt, device=fabric.device)
        y = generate(
            model,
            encoded_prompt,
            max_new_tokens=model.config.block_size,  # type: ignore[union-attr,arg-type]
            temperature=temperature,
            top_k=top_k,
            stop_tokens=stop_tokens,
        )
        model.reset_cache()
        print(">> Reply: ", end="")
        try:
            tokens_generated = 0
            t0 = time.perf_counter()
            for token in y:
                print(tokenizer.decode(token), end="", flush=True)
                tokens_generated += 1
            t = time.perf_counter() - t0
            print(f"\nTime for inference: {t:.02f} sec total, {tokens_generated / t:.02f} tokens/sec", file=sys.stderr)
        except KeyboardInterrupt:
            # support stopping generation
            pass
        print()


def prompt_config(checkpoint_dir: Path, tokenizer: Tokenizer) -> Tuple[str, Tuple[List[int], ...]]:
    checkpoint_name = str(checkpoint_dir)
    if re.search(r"stabilityai.*tuned-alpha", checkpoint_name):
        system_prompt = (
            "<|SYSTEM|># StableLM Tuned (Alpha version)\n- StableLM is a helpful and harmless open-source AI language"
            " model developed by StabilityAI.\n- StableLM is excited to be able to help the user, but will refuse to do"
            " anything that could be considered harmful to the user.\n- StableLM is more than just an information"
            " source, StableLM is also able to write poetry, short stories, and make jokes.\n- StableLM will refuse to"
            " participate in anything that could harm a human.<|USER|>{prompt}<|ASSISTANT|>"
        )
        stop_tokens = (
            [tokenizer.eos_id],
            [tokenizer.token_to_id("<|SYSTEM|>")],
            [tokenizer.token_to_id("<|ASSISTANT|>")],
            [tokenizer.token_to_id("<|USER|>")],
        )
        return system_prompt, stop_tokens
    if re.search(r"togethercomputer.*Chat", checkpoint_name):
        system_prompt = "<human>: {prompt}\n<bot>:"
        lt, gt = tokenizer.token_to_id("<"), tokenizer.token_to_id(">:")
        stop_tokens = (
            [tokenizer.eos_id],
            # annoyingly, there's no single stop token for these
            [lt, tokenizer.token_to_id("human"), gt],
            [lt, tokenizer.token_to_id("bot"), gt],
        )
        return system_prompt, stop_tokens
    if re.search(r"togethercomputer.*Instruct", checkpoint_name):
        system_prompt = "Q: {prompt}\nA:"
        colon = tokenizer.token_to_id(":")
        stop_tokens = (
            [tokenizer.eos_id],
            # annoyingly, there's no single stop token for these
            [tokenizer.token_to_id("Q"), colon],
            [tokenizer.token_to_id("Question")],
            [tokenizer.token_to_id("A"), colon],
            [tokenizer.token_to_id("Label"), colon],
            [187, 187],  # '\n', '\n'
            [535],  # '\n\n'
            [2756],  # '\n\n\n'
        )
        return system_prompt, stop_tokens

    # default format
    return "{prompt}", ([tokenizer.eos_id],)


if __name__ == "__main__":
    from jsonargparse import CLI

    torch.set_float32_matmul_precision("high")
    warnings.filterwarnings(
        # Triggered internally at ../aten/src/ATen/EmptyTensor.cpp:31
        "ignore",
        message="ComplexHalf support is experimental and many operators don't support it yet",
    )
    warnings.filterwarnings(
        # Triggered in bitsandbytes/autograd/_functions.py:298
        "ignore",
        message="MatMul8bitLt: inputs will be cast from torch.bfloat16 to float16 during quantization",
    )
    CLI(main)
