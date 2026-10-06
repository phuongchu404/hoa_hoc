from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    models_dir: Path = Path(os.environ.get("CHEM_MODELS_DIR", BACKEND_DIR / "models"))
    molscribe_ckpt: str = os.environ.get("CHEM_MOLSCRIBE_CKPT", "swin_base_char_aux_1m680k.pth")
    rxnscribe_ckpt: str = os.environ.get("CHEM_RXNSCRIBE_CKPT", "pix2seq_reaction_full.ckpt")
    # decoders (many tiny sequential ops) run fastest on CPU; image encoders on
    # the Apple GPU. "auto" picks mps when available.
    device: str = os.environ.get("CHEM_DEVICE", "cpu")
    accelerator: str = os.environ.get("CHEM_ACCELERATOR", "auto")  # auto | mps | cuda | none
    threads: int = int(os.environ.get("CHEM_THREADS", "0"))  # 0 = torch default
    tta: bool = _env_bool("CHEM_TTA", True)  # second view per molecule for cross-checking
    warmup: bool = _env_bool("CHEM_WARMUP", True)
    cache_size: int = int(os.environ.get("CHEM_CACHE_SIZE", "64"))
    max_upload_mb: int = int(os.environ.get("CHEM_MAX_UPLOAD_MB", "25"))
    export_dir: Path = Path(os.environ.get("CHEM_EXPORT_DIR", Path.home() / "Documents" / "ChemImage Exports"))
    frontend_dist: Path = Path(os.environ.get("CHEM_FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist"))
    low_confidence: float = float(os.environ.get("CHEM_LOW_CONFIDENCE", "0.85"))
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    @property
    def molscribe_path(self) -> Path:
        return self.models_dir / self.molscribe_ckpt

    @property
    def rxnscribe_path(self) -> Path:
        return self.models_dir / self.rxnscribe_ckpt


settings = Settings()
