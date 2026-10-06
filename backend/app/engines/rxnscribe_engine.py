"""RxnScribe wrapper used only for layout: it finds molecules, condition texts
and how they form reactions. Molecule recognition and OCR are done separately."""
from __future__ import annotations

from dataclasses import dataclass, field

import torch
from PIL import Image


@dataclass
class LayoutBox:
    kind: str  # "mol" | "text" | "ident"
    bbox: tuple[float, float, float, float]  # pixels x0, y0, x1, y1
    score: float = 0.0


@dataclass
class LayoutReaction:
    reactants: list[LayoutBox] = field(default_factory=list)
    conditions: list[LayoutBox] = field(default_factory=list)
    products: list[LayoutBox] = field(default_factory=list)


_KIND = {"[Mol]": "mol", "[Txt]": "text", "[Idt]": "ident"}


class RxnScribeEngine:
    def __init__(self, checkpoint: str, device: torch.device, accel: torch.device | None = None):
        # The backbone would otherwise download ImageNet weights that the
        # checkpoint overwrites anyway; keep everything offline.
        import rxnscribe.pix2seq.backbone as backbone
        from rxnscribe import interface

        backbone.is_main_process = lambda: False

        class _Layout(interface.RxnScribe):
            def get_molscribe(self):
                return None

            def get_ocr_model(self):
                return None

        self._model = _Layout(checkpoint, device=device)
        if accel is not None and accel != device:
            self._split_devices(accel, device)

    def _split_devices(self, accel: torch.device, device: torch.device) -> None:
        """Run the CNN backbone on the accelerator (big speed-up) and keep the
        autoregressive transformer on CPU (many tiny ops, faster there)."""
        from rxnscribe.pix2seq.misc import nested_tensor_from_tensor_list

        model = self._model.model
        model.backbone.to(accel)
        model.input_proj.to(accel)

        def forward(image_tensor, targets=None, max_len=500):
            if isinstance(image_tensor, (list, torch.Tensor)):
                image_tensor = nested_tensor_from_tensor_list(image_tensor.to(accel))
            features, pos = model.backbone(image_tensor)
            src, mask = features[-1].decompose()
            mask = torch.zeros_like(mask).bool().to(device)
            src = model.input_proj(src).to(device)
            return model.transformer(src, None, mask, pos[-1].to(device), max_len=max_len)

        model.forward = forward

    @torch.inference_mode()
    def predict(self, image: Image.Image) -> list[LayoutReaction]:
        w, h = image.size
        raw = self._model.predict_image(image, molscribe=False, ocr=False)
        reactions = []
        for r in raw:
            rx = LayoutReaction()
            for role in ("reactants", "conditions", "products"):
                for ent in r.get(role, []):
                    kind = _KIND.get(ent.get("category"), "text")
                    x0, y0, x1, y1 = ent["bbox"]
                    box = LayoutBox(
                        kind=kind,
                        bbox=(x0 * w, y0 * h, x1 * w, y1 * h),
                        score=float(ent.get("score", 0.0) or 0.0),
                    )
                    getattr(rx, role).append(box)
            if rx.reactants or rx.products:
                reactions.append(rx)
        return reactions
