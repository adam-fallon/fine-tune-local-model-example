let
  pkgs = import <nixpkgs> {};
in pkgs.mkShell {
  buildInputs = [
    pkgs.python3
    pkgs.python3.pkgs.requests
  ];
  shellHook = ''
    # Tells pip to put packages into $PIP_PREFIX instead of the usual locations.
    # See https://pip.pypa.io/en/stable/user_guide/#environment-variables.
    export PIP_PREFIX=$(pwd)/_build/pip_packages
    export PYTHONPATH="$PIP_PREFIX/${pkgs.python3.sitePackages}:$PYTHONPATH"
    export PATH="$PIP_PREFIX/bin:$PATH"
    unset SOURCE_DATE_EPOCH
    export PYTORCH_ENABLE_MPS_FALLBACK=1

    make_venv() {
        python -m venv .venv
    }

    activate_venv() {
        source .venv/bin/activate
        pip install -r requirements.txt
    }

    install_lit_parrot() {
        git clone https://github.com/Lightning-AI/lit-parrot
    }

    # for cuda
    install_torch_dev_gpu() {
        pip install --index-url https://download.pytorch.org/whl/nightly/cu118 --pre 'torch>=2.1.0dev'
    }

    # for cpu
    install_torch_dev_cpu() {
        pip install --index-url https://download.pytorch.org/whl/nightly/cpu --pre 'torch>=2.1.0dev'
    }

    # download the model weights
    download_weights() {
        python scripts/download.py --repo_id togethercomputer/RedPajama-INCITE-Base-3B-v1
    }

    # convert the weights to Lit-Parrot format
    convert_weights_to_parrot() {
        python scripts/convert_hf_checkpoint.py --checkpoint_dir checkpoints/togethercomputer/RedPajama-INCITE-Base-3B-v1
    }

    create_checkpoints() {
        python scripts/prepare_alpaca.py --destination_path data/dolly --checkpoint_dir checkpoints/togethercomputer/RedPajama-INCITE-Base-3B-v1
    }

    finetune() {
        python finetune_adapter.py --data_dir data/dolly --checkpoint_dir checkpoints/togethercomputer/RedPajama-INCITE-Base-3B-v1        
    }

    setup() {
        install_lit_parrot
        make_venv
        activate_venv
        cd lit-parrot
        install_torch_dev_cpu # or install_torch_dev_gpu
        download_weights
        convert_weights_to_parrot
        create_checkpoints
    }
  '';
}