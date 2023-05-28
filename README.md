# Fine Tuning Local Models

1. Launch instance at [Lambda](https://lambdalabs.com)
    1. I used a `gpu_1x_a10` instance (0.60c per hour)
2. Update everything
    1. `sudo apt update`
    2. `sudo apt upgrade`
3. Clone fine tuning repo + setup depenencies
    1. `git clone https://github.com/adam-fallon/fine-tune-local-model-example`
    2. `python -m venv env`
    3. `source .venv/bin/activate`
    4. `pip install -r requirements.txt`
    6. `cd lit-parrot`
4. Install PyTorch dev with FlashAttention
   1. `pip install --index-url https://download.pytorch.org/whl/nightly/cu118 --pre 'torch>=2.1.0dev'`
5. Download Weights
    1. `python scripts/download.py --repo_id togethercomputer/RedPajama-INCITE-Base-3B-v1`
6. Convert weights to work with Parrot
    1. `python scripts/convert_hf_checkpoint.py --checkpoint_dir checkpoints/togethercomputer/RedPajama-INCITE-Base-3B-v1`
7. Create checkpoints
    1. `python scripts/prepare_alpaca.py --destination_path data/dolly --checkpoint_dir checkpoints/togethercomputer/RedPajama-INCITE-Base-3B-v1`
 8. FineTune
    1. `python finetune_adapter.py --data_dir data/dolly --checkpoint_dir checkpoints/togethercomputer/RedPajama-INCITE-Base-3B-v1`
 9.  Test a prompt
    1. `python generate_adapter.py --adapter_path out/adapter/alpaca/iter-015999.pth --checkpoint_dir checkpoints/togethercomputer/RedPajama-INCITE-Base-3B-v1 --prompt "Who is the author of the Game of Thrones?"`