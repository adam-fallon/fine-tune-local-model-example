# Fine Tuning Local Models

1. Install nix.
   1. Easiest way is `curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install`
2. Run `nix-shell` in this directory.
3. Run `setup`
   1. Run `setup-gpu` if you have a GPU.
4. Fine tune;
   1. `finetune`