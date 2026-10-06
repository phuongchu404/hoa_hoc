"""Download the model checkpoints once (~1.6 GB). Afterwards everything runs offline."""
from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

MODELS = [
    ("yujieq/MolScribe", "swin_base_char_aux_1m680k.pth"),  # structure recognition
    ("yujieq/RxnScribe", "pix2seq_reaction_full.ckpt"),  # reaction layout
]


def main() -> int:
    target = Path(__file__).resolve().parent.parent / "models"
    target.mkdir(exist_ok=True)
    for repo, name in MODELS:
        dest = target / name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"✓ {name} (đã có)")
            continue
        print(f"↓ {repo}/{name} ...", flush=True)
        hf_hub_download(repo, name, local_dir=target)
        print(f"✓ {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
