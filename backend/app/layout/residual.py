"""Find drawn structures the layout model did not report: reagents drawn above
or below an arrow (a Grignard, an epoxide, a catalyst) and structures in side
boxes ("catalyst A"). Everything already explained (molecule boxes, OCR text,
arrows, brackets, frames) is masked; what remains is grouped into blobs."""
from __future__ import annotations

import cv2
import numpy as np

Box = tuple[float, float, float, float]


def find_residual_boxes(arr: np.ndarray, mol_boxes: list[Box], text_boxes: list[Box],
                        bond_px: float) -> list[Box]:
    h, w = arr.shape[:2]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    def clear(b: Box, pad: float) -> None:
        x0, y0, x1, y1 = (int(max(0, b[0] - pad)), int(max(0, b[1] - pad)),
                          int(min(w, b[2] + pad)), int(min(h, b[3] + pad)))
        ink[y0:y1, x0:x1] = 0

    for b in mol_boxes:
        clear(b, 4)
    # remove lines, arrows, brackets and frames
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    for i in range(1, n):
        x, y, cw, ch, area = st[i]
        long_side, short_side = max(cw, ch), max(1, min(cw, ch))
        thin = long_side >= 2.5 * bond_px and long_side >= 6 * short_side
        frame = False
        if cw > 2 * bond_px and ch > 2 * bond_px:
            comp = lab[y:y + ch, x:x + cw] == i
            m = max(3, int(0.06 * min(cw, ch)))
            border = comp.copy()
            border[m:-m, m:-m] = False
            frame = comp.sum() > 0 and border.sum() / comp.sum() > 0.85
        bracket = ch >= 2 * bond_px and cw <= 0.5 * bond_px  # [ ] around intermediates
        if thin or frame or bracket:
            ink[lab == i] = 0
    for b in text_boxes:  # text is masked last: it may sit inside a frame
        clear(b, 2)

    # merge strokes of one structure: close gaps up to ~half a bond
    k = max(3, int(0.5 * bond_px))
    merged = cv2.dilate(ink, np.ones((k, k), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    out: list[Box] = []
    for i in range(1, n):
        x, y, cw, ch, area = st[i]
        real = int((ink[y:y + ch, x:x + cw] > 0).sum())
        if max(cw, ch) < 1.6 * bond_px or min(cw, ch) < 0.5 * bond_px or real < 3 * bond_px:
            continue  # specks, "+" signs, degree marks
        half = k / 2
        out.append((x + half, y + half, x + cw - half, y + ch - half))
    return out


def grow_with_labels(box: Box, texts: list[tuple[Box, str]], bond_px: float) -> Box:
    """Atom labels (MgBr, SH, i-Pr, OMe) were masked as text: pull back in short
    label-like texts touching the blob, but not solvents or step numbers."""
    import re

    from ..engines.ocr import _REAGENT_SET

    label_like = re.compile(r"^[A-Za-z][A-Za-z0-9+\-⊕⊖()]{0,7}$")
    x0, y0, x1, y1 = box
    pad = 0.6 * bond_px
    changed = True
    while changed:
        changed = False
        for t, text in texts:
            word = text.strip()
            from ..chem.abbreviations import lookup as _lookup_label

            is_label = _lookup_label(word) is not None
            if not label_like.match(word) or (word in _REAGENT_SET and not is_label) or t[2] - t[0] > 2.5 * bond_px:
                continue
            if t[0] < x1 + pad and t[2] > x0 - pad and t[1] < y1 + pad and t[3] > y0 - pad:
                nx0, ny0, nx1, ny1 = min(x0, t[0]), min(y0, t[1]), max(x1, t[2]), max(y1, t[3])
                if (nx0, ny0, nx1, ny1) != (x0, y0, x1, y1):
                    x0, y0, x1, y1 = nx0, ny0, nx1, ny1
                    changed = True
    return (x0, y0, x1, y1)
