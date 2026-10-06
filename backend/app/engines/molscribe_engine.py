"""MolScribe wrapper returning the raw predicted graph (atoms, coordinates, bond
matrix, confidences). Graph -> molecule conversion is done by app.chem.structure,
which replaces MolScribe's own (RDKit-incompatible) post-processing."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import torch

log = logging.getLogger(__name__)


@dataclass
class RawGraph:
    symbols: list[str]
    coords: list[tuple[float, float]]  # normalised 0..1 inside the input crop
    edges: list[list[int]]
    confidence: float
    atom_scores: list[float]
    smiles_hint: str  # MolScribe's own token SMILES (debug only)


class MolScribeEngine:
    def __init__(self, checkpoint: str, device: torch.device, batch_size: int = 16,
                 accel: torch.device | None = None):
        """device runs the autoregressive decoder; accel (e.g. mps) optionally
        runs the Swin image encoder, which is ~4x faster on Apple GPUs."""
        from molscribe import MolScribe

        self.device = device
        self.batch_size = batch_size
        self._model = MolScribe(checkpoint, device=device)
        self._model.decoder.compute_confidence = True
        self.encoder_device = accel or device
        if self.encoder_device != device:
            self._model.encoder.to(self.encoder_device)

    @torch.inference_mode()
    def predict(self, images: list[np.ndarray]) -> list[RawGraph]:
        """images: list of RGB uint8 arrays (H, W, 3)."""
        m = self._model
        out: list[RawGraph] = []
        for start in range(0, len(images), self.batch_size):
            batch = images[start:start + self.batch_size]
            tensors = [m.transform(image=img, keypoints=[])["image"] for img in batch]
            x = torch.stack(tensors, dim=0).to(self.encoder_device)
            features, hiddens = m.encoder(x)
            if self.encoder_device != self.device:
                features = _to(features, self.device)
                hiddens = _to(hiddens, self.device)
            preds = m.decoder.decode(features, hiddens)
            for p in preds:
                cc = p["chartok_coords"]
                out.append(
                    RawGraph(
                        symbols=list(cc["symbols"]),
                        coords=[(float(a), float(b)) for a, b in cc["coords"]],
                        edges=[list(map(int, row)) for row in p["edges"]],
                        confidence=float(p.get("overall_score", 0.0)),
                        atom_scores=[float(s) for s in cc.get("atom_scores", [])],
                        smiles_hint=cc.get("smiles", ""),
                    )
                )
        return out


def _to(obj, device):
    if torch.is_tensor(obj):
        return obj.to(device)
    if isinstance(obj, (list, tuple)):
        return type(obj)(_to(o, device) for o in obj)
    return obj
