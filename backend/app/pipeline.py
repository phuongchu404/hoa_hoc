"""Image -> Document pipeline.

layout (RxnScribe) ─┐
                    ├─> molecule crops ─> MolScribe (2 views) ─> RDKit build ─┐
OCR (Vision) ───────┘                                                        ├─> Document
                       arrows (OpenCV) ───────────────────────────────────────┘
"""
from __future__ import annotations

import hashlib
import re
import io
import logging
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image, ImageOps
from rdkit import Chem

from .chem import io as chem_io
from .chem.structure import BuiltMolecule, build_molecule
from .config import Settings
from .engines.molscribe_engine import MolScribeEngine, RawGraph
from .engines.ocr import OcrEngine, TextLine
from .engines.rxnscribe_engine import LayoutReaction, RxnScribeEngine
from .layout.arrows import find_arrow
from .schemas import Arrow, Document, Molecule, Reaction, TextBlock

log = logging.getLogger(__name__)

Box = tuple[float, float, float, float]


# ----------------------------------------------------------------------------- utils


def load_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, rgba)
    return img.convert("RGB")


def _iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _center_in(pt: tuple[float, float], b: Box, pad: float = 0.0) -> bool:
    return b[0] - pad <= pt[0] <= b[2] + pad and b[1] - pad <= pt[1] <= b[3] + pad


def _content_box(arr: np.ndarray) -> Box:
    gray = arr.mean(axis=2)
    ys, xs = np.where(gray < 200)
    h, w = gray.shape
    if len(xs) == 0:
        return (0, 0, w, h)
    return (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1))


def _clean_crop(crop: np.ndarray, core: Box) -> np.ndarray:
    """Whiten every ink blob that does not touch the molecule box: stray text,
    dashed separators and arrow tails from neighbouring objects confuse the
    recogniser (e.g. a lone 'N' becomes an extra fragment)."""
    import cv2

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, lab, st, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    bx0, by0, bx1, by1 = core
    keep = np.zeros(n, dtype=bool)
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        keep[i] = not (x + w < bx0 or x > bx1 or y + h < by0 or y > by1)
    out = crop.copy()
    out[(lab > 0) & ~keep[lab]] = 255
    return out


def _views(arr: np.ndarray, box: Box, tta: bool) -> list[tuple[np.ndarray, tuple[float, float, float, float]]]:
    """Crops fed to MolScribe with the pixel rectangle (x0, y0, w, h) that the
    model's 0..1 coordinates map onto. Several views of one molecule give
    independent readings that are cross-checked afterwards."""
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = box
    pad = max(4.0, 0.03 * max(x1 - x0, y1 - y0))
    vx0, vy0 = int(max(0, x0 - pad)), int(max(0, y0 - pad))
    vx1, vy1 = int(min(w, x1 + pad)), int(min(h, y1 + pad))
    padded = np.ascontiguousarray(arr[vy0:vy1, vx0:vx1])
    views = [(padded, (vx0, vy0, vx1 - vx0, vy1 - vy0))]
    if tta:
        core = (x0 - vx0 - 1, y0 - vy0 - 1, x1 - vx0 + 1, y1 - vy0 + 1)
        clean = _clean_crop(padded, core)
        views.append((clean, (vx0, vy0, vx1 - vx0, vy1 - vy0)))
        m = int(0.15 * max(clean.shape[0], clean.shape[1])) + 4
        framed = np.pad(clean, ((m, m), (m, m), (0, 0)), constant_values=255)
        views.append((framed, (vx0 - m, vy0 - m, (vx1 - vx0) + 2 * m, (vy1 - vy0) + 2 * m)))
    return views


def _flat(smiles: str) -> str:
    """Canonical SMILES without stereo (constitution only)."""
    m = Chem.MolFromSmiles(smiles) if smiles else None
    return Chem.MolToSmiles(m, isomericSmiles=False) if m else smiles


def _pick_accelerator(name: str) -> torch.device | None:
    name = (name or "none").lower()
    if name == "none":
        return None
    if name in ("auto", "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    if name in ("auto", "cuda") and torch.cuda.is_available():
        return torch.device("cuda")
    return None


@dataclass
class _Candidate:
    built: BuiltMolecule
    graph: RawGraph
    smiles: str


# ----------------------------------------------------------------------------- pipeline


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.threads > 0:
            torch.set_num_threads(settings.threads)
        self.device = torch.device(settings.device)
        self.accel = _pick_accelerator(settings.accelerator)
        t = time.perf_counter()
        self.molscribe = MolScribeEngine(str(settings.molscribe_path), self.device, accel=self.accel)
        self.rxnscribe = RxnScribeEngine(str(settings.rxnscribe_path), self.device, accel=self.accel)
        self.ocr = OcrEngine()
        self.load_seconds = time.perf_counter() - t
        self._lock = threading.Lock()  # models are not thread-safe
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr")
        self._cache: OrderedDict[str, Document] = OrderedDict()
        log.info("models loaded in %.1fs (decoder %s, encoder %s)", self.load_seconds, self.device, self.accel)

    # -------------------------------------------------------------- public API

    def warmup(self) -> None:
        img = Image.new("RGB", (200, 120), "white")
        from PIL import ImageDraw

        d = ImageDraw.Draw(img)
        d.line([(40, 60), (80, 40), (120, 60), (160, 40)], fill="black", width=2)
        try:
            self.recognize(img, use_cache=False)
        except Exception:  # pragma: no cover
            log.exception("warm-up failed")

    def recognize(self, image: Image.Image, use_cache: bool = True) -> Document:
        key = hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest()[:16]
        if use_cache and key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key].model_copy(deep=True)

        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        arr = np.asarray(image)
        ocr_future = self._pool.submit(self.ocr.recognize, image)

        with self._lock:
            t = time.perf_counter()
            layout = _merge_partial_reactions(self.rxnscribe.predict(image))
            timings["layout"] = time.perf_counter() - t

            boxes, roles = self._collect_molecule_boxes(layout)
            if not boxes:
                boxes = [_content_box(arr)]
            # OCR ran in parallel with layout; its words are used to verify labels
            t = time.perf_counter()
            lines = ocr_future.result()
            timings["ocr_wait"] = time.perf_counter() - t
            t = time.perf_counter()
            mols = self._recognize_boxes(arr, boxes, source="image", lines=lines)
            timings["molecules"] = time.perf_counter() - t
            mols, boxes, roles = _drop_text_boxes(mols, boxes, roles, lines)
            layout, roles = _merge_partial_roles(layout, roles)
            t = time.perf_counter()
            extra, extra_boxes = self._residual_structures(arr, mols, boxes, lines)
            timings["agents"] = time.perf_counter() - t

        doc = Document(id=key, image_width=image.width, image_height=image.height, molecules=mols)
        self._assemble_reactions(doc, arr, layout, boxes, roles, lines, extra_boxes)
        self._attach_agents(doc, extra, extra_boxes)
        bond_px = sorted(m.bond_px for m in mols if m.bond_px)
        if bond_px and bond_px[len(bond_px) // 2] < 25:
            doc.notices.append(
                f"Ảnh có độ phân giải thấp (~{bond_px[len(bond_px) // 2]:.0f} px mỗi liên kết). "
                "Khung cấu trúc thường vẫn đúng, nhưng nhãn và lập thể (nêm/gạch) dễ bị đọc sai — "
                "hãy kiểm tra các thẻ màu vàng, hoặc dùng ảnh nét hơn (phóng to tài liệu trước khi chụp)."
            )
        timings["total"] = time.perf_counter() - t0
        doc.timings = {k: round(v, 3) for k, v in timings.items()}

        self._cache[key] = doc.model_copy(deep=True)
        while len(self._cache) > self.settings.cache_size:
            self._cache.popitem(last=False)
        return doc

    def recognize_region(self, image: Image.Image, bbox: Box) -> Molecule:
        arr = np.asarray(image)
        x0, y0, x1, y1 = bbox
        w, h = image.size
        box = (max(0.0, x0), max(0.0, y0), min(float(w), x1), min(float(h), y1))
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            raise ValueError("Vùng chọn quá nhỏ")
        with self._lock:
            lines = self.ocr.recognize(image)
            mol = self._recognize_boxes(arr, [box], source="region", lines=lines)[0]
        return mol

    # -------------------------------------------------------------- molecules

    @staticmethod
    def _collect_molecule_boxes(layout: list[LayoutReaction]) -> tuple[list[Box], list[dict]]:
        boxes: list[Box] = []
        roles: list[dict] = []  # per reaction: {"reactants": [box idx], "products": [...]}
        for rx in layout:
            role = {"reactants": [], "products": []}
            for name in ("reactants", "products"):
                for b in getattr(rx, name):
                    if b.kind != "mol":
                        continue
                    idx = next((i for i, ob in enumerate(boxes) if _iou(ob, b.bbox) > 0.6), None)
                    if idx is None:
                        boxes.append(b.bbox)
                        idx = len(boxes) - 1
                    role[name].append(idx)
            roles.append(role)
        return boxes, roles

    def _recognize_boxes(self, arr: np.ndarray, boxes: list[Box], source: str,
                         lines: list[TextLine] | None = None) -> list[Molecule]:
        tta = self.settings.tta
        views: list[np.ndarray] = []
        owners: list[tuple[int, int]] = []
        origins: list[tuple[float, float, float, float]] = []
        for bi, box in enumerate(boxes):
            for v, origin in _views(arr, box, tta):
                views.append(v)
                owners.append(bi)
                origins.append(origin)
        graphs = self.molscribe.predict(views)

        cands: dict[int, list[_Candidate]] = {i: [] for i in range(len(boxes))}
        for bi, origin, g in zip(owners, origins, graphs):
            ox, oy, vw, vh = origin
            px = [(ox + x * vw, oy + y * vh) for x, y in g.coords]
            symbols, notes = _ocr_fix_labels(g.symbols, px, g.edges, lines or [])
            edges = g.edges
            if "[*drop*]" in symbols:
                keep = [k for k, s_ in enumerate(symbols) if s_ != "[*drop*]"]
                symbols = [symbols[k] for k in keep]
                px = [px[k] for k in keep]
                edges = [[g.edges[a][b] for b in keep] for a in keep]
            try:
                built = build_molecule(symbols, px, edges)
                built.warnings[:0] = notes
            except Exception as exc:  # never fail the whole document
                log.exception("build failed")
                built = BuiltMolecule(Chem.Mol(), errors=[f"Lỗi dựng cấu trúc: {exc}"])
            smi = chem_io.mol_info(built).smiles if built.mol.GetNumAtoms() else ""
            cands[bi].append(_Candidate(built, g, smi))

        out: list[Molecule] = []
        for bi, box in enumerate(boxes):
            cs = cands[bi]
            # agreement is judged on the constitution; stereo is a tie-breaker
            # (wedges are the first thing lost in low-resolution images)
            flat = {id(c): _flat(c.smiles) for c in cs}
            votes = {c.smiles: sum(1 for o in cs if flat[id(o)] == flat[id(c)]) for c in cs}
            # valid chemistry first, then fully understood labels, then agreement
            # between views, then fewest guessed labels, then model confidence
            best = max(cs, key=lambda c: (
                c.built.ok and bool(c.smiles),
                -c.built.unknown_labels,
                votes[c.smiles],
                -c.built.fuzzy_labels,
                "." not in c.smiles,
                c.smiles.count("@") + c.smiles.count("/") + c.smiles.count("\\"),
                c.graph.confidence,
            ))
            alts = sorted({c.smiles for c in cs if c.smiles and c.smiles != best.smiles})
            mol = self.molecule_from_built(
                best.built,
                mol_id=f"m{bi + 1}",
                bbox=list(box),
                source=source,
                confidence=best.graph.confidence,
            )
            if alts:
                mol.alternatives = alts
                if votes[best.smiles] * 2 <= len(cs):  # no majority among the views
                    mol.warnings.append("Các lần đọc cho kết quả khác nhau — hãy kiểm tra lại cấu trúc")
                    if mol.status == "ok":
                        mol.status = "warning"
            out.append(mol)
        return out

    def molecule_from_built(self, built: BuiltMolecule, mol_id: str, bbox: list[float] | None,
                            source: str, confidence: float | None = None) -> Molecule:
        info = chem_io.mol_info(built)
        warnings = list(built.warnings)
        errors = list(built.errors)
        if confidence is not None and confidence < 0.4:
            errors.append(f"Không đọc được cấu trúc này (độ tin cậy {confidence:.0%}) — hãy vẽ lại bằng nút Sửa")
        elif confidence is not None and confidence < self.settings.low_confidence:
            warnings.append(f"Độ tin cậy thấp ({confidence:.0%})")
        if built.mol.GetNumAtoms() and "." in info.smiles:
            warnings.append("Cấu trúc gồm nhiều mảnh rời nhau")
        status = "error" if errors else ("warning" if warnings else "ok")
        try:
            svg = chem_io.to_svg(built) if built.mol.GetNumAtoms() else ""
        except Exception:
            log.exception("svg failed")
            svg = ""
        try:
            molfile = chem_io.to_molfile(built) if built.mol.GetNumAtoms() else ""
        except Exception:
            log.exception("molfile failed")
            molfile = ""
        return Molecule(
            id=mol_id,
            bbox=bbox,
            molfile=molfile,
            smiles=info.smiles,
            formula=info.formula,
            mol_weight=info.mol_weight,
            exact_mass=info.exact_mass,
            inchi=info.inchi,
            inchikey=info.inchikey,
            svg=svg,
            confidence=round(confidence, 4) if confidence is not None else None,
            status=status,
            warnings=warnings,
            errors=errors,
            source=source,  # type: ignore[arg-type]
            bond_px=built.bond_px,
        )

    # -------------------------------------------------------------- agents / side structures

    def _residual_structures(self, arr: np.ndarray, mols: list[Molecule], boxes: list[Box],
                             lines: list[TextLine]) -> tuple[list[Molecule], list[Box]]:
        from .layout.residual import find_residual_boxes, grow_with_labels

        bond_px = sorted(m.bond_px for m in mols if m.bond_px)
        bond = bond_px[len(bond_px) // 2] if bond_px else 30.0
        text_boxes = [ln.bbox for ln in lines]
        blobs = find_residual_boxes(arr, boxes, text_boxes, bond)
        if not blobs:
            return [], []
        texts = [(ln.bbox, ln.text) for ln in lines]
        grown = [grow_with_labels(b, texts, bond) for b in blobs]
        found = self._recognize_boxes(arr, grown, source="image", lines=lines)
        keep_m, keep_b = [], []
        for m, b in zip(found, grown):
            heavy = Chem.MolFromSmiles(m.smiles).GetNumHeavyAtoms() if m.smiles and Chem.MolFromSmiles(m.smiles) else 0
            if m.status == "error" or heavy < 3 or (m.confidence or 0) < 0.75 or "*" in m.smiles \
                    or any("bậc liên kết" in w for w in m.warnings):
                continue
            keep_m.append(m)
            keep_b.append(b)
        start = len(mols)
        for k, m in enumerate(keep_m):
            m.id = f"m{start + k + 1}"
        return keep_m, keep_b

    @staticmethod
    def _bond_hint(doc: Document) -> float:
        v = sorted(m.bond_px for m in doc.molecules if m.bond_px)
        return v[len(v) // 2] if v else 30.0

    def _attach_agents(self, doc: Document, extra: list[Molecule], extra_boxes: list[Box]) -> None:
        """Structures next to an arrow become that reaction's agents; others stay
        as stand-alone molecules (e.g. a catalyst drawn in a side box)."""
        arrows = {a.id: a for a in doc.arrows}
        for m, b in zip(extra, extra_boxes):
            doc.molecules.append(m)
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            best, best_d = None, float("inf")
            boxes_of = {mm.id: mm.bbox for mm in doc.molecules if mm.bbox}
            for r in doc.reactions:
                a = arrows.get(r.arrow) if r.arrow else None
                if a is None:
                    continue
                ax0, ax1 = sorted((a.tail[0], a.head[0]))
                ay0, ay1 = sorted((a.tail[1], a.head[1]))
                # a multi-step arrow (A -> [text] -> B) spans the whole gap
                rb = [boxes_of[i] for i in r.reactants if i in boxes_of]
                pb = [boxes_of[i] for i in r.products if i in boxes_of]
                if rb and pb and ax1 - ax0 >= ay1 - ay0:
                    gap0, gap1 = max(b[2] for b in rb), min(b[0] for b in pb)
                    if gap1 > gap0:
                        ax0, ax1 = min(ax0, gap0), max(ax1, gap1)
                dx = max(0.0, ax0 - cx, cx - ax1)
                dy = max(0.0, ay0 - cy, cy - ay1)
                horizontal = ax1 - ax0 >= ay1 - ay0
                # a reagent sits over/under a horizontal arrow (or beside a vertical one)
                d = dy + 3 * dx if horizontal else dx + 3 * dy
                limit = max(3.0 * max(b[3] - b[1], b[2] - b[0]), 6 * self._bond_hint(doc))
                if d < best_d and d < limit:
                    best, best_d = r, d
            if best is not None:
                best.agents.append(m.id)
                best.reaction_smiles = _reaction_smiles(doc, best)

    # -------------------------------------------------------------- reactions / text

    def _assemble_reactions(self, doc: Document, arr: np.ndarray, layout: list[LayoutReaction],
                            boxes: list[Box], roles: list[dict], lines: list[TextLine],
                            extra_boxes: list[Box] | None = None) -> None:
        gray = arr.mean(axis=2).astype(np.uint8)
        all_boxes = list(boxes) + list(extra_boxes or [])
        lines = [_trim_line(ln, all_boxes) for ln in lines]
        used_lines: set[int] = set()
        # OCR lines inside molecule boxes are atom labels, not free text
        for li, ln in enumerate(lines):
            c = ((ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2)
            if any(_center_in(c, b) for b in all_boxes):
                used_lines.add(li)

        text_n = 0
        for ri, (rx, role) in enumerate(zip(layout, roles)):
            reaction = Reaction(
                id=f"r{ri + 1}",
                reactants=[f"m{i + 1}" for i in role["reactants"]],
                products=[f"m{i + 1}" for i in role["products"]],
            )
            cond_boxes = [b.bbox for b in rx.conditions]
            tail, head = find_arrow(
                gray,
                [boxes[i] for i in role["reactants"]],
                [boxes[i] for i in role["products"]],
                cond_boxes,
            )
            arrow = Arrow(id=f"a{ri + 1}", tail=list(tail), head=list(head))
            doc.arrows.append(arrow)
            reaction.arrow = arrow.id
            arrow_y = (tail[1] + head[1]) / 2
            for cb in cond_boxes:
                members = []
                for li, ln in enumerate(lines):
                    if li in used_lines:
                        continue
                    c = ((ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2)
                    if _center_in(c, cb, pad=6):
                        members.append(li)
                if not members:
                    continue
                members.sort(key=lambda i: (lines[i].bbox[1], lines[i].bbox[0]))
                used_lines.update(members)
                text = _join_lines([lines[i] for i in members])
                bb = [
                    min(lines[i].bbox[0] for i in members), min(lines[i].bbox[1] for i in members),
                    max(lines[i].bbox[2] for i in members), max(lines[i].bbox[3] for i in members),
                ]
                text_n += 1
                tb = TextBlock(id=f"t{text_n}", bbox=bb, text=text)
                doc.texts.append(tb)
                if (bb[1] + bb[3]) / 2 < arrow_y:
                    reaction.conditions_above.append(tb.id)
                else:
                    reaction.conditions_below.append(tb.id)
            reaction.reaction_smiles = _reaction_smiles(doc, reaction)
            doc.reactions.append(reaction)

            # "+" between reactants / products (OCR often merges it into a molecule box)
            for side in (role["reactants"], role["products"]):
                ordered = sorted(side, key=lambda i: boxes[i][0])
                for a, b in zip(ordered, ordered[1:]):
                    ba, bb = boxes[a], boxes[b]
                    cx = (ba[2] + bb[0]) / 2
                    cy = (ba[1] + ba[3] + bb[1] + bb[3]) / 4
                    text_n += 1
                    doc.texts.append(TextBlock(id=f"t{text_n}", bbox=[cx - 8, cy - 9, cx + 8, cy + 9], text="+"))

        # stray text inside a reaction's arrow gap (e.g. 'THF' under a drawn
        # reagent) is a condition of that reaction
        boxes_by_id = {f"m{i + 1}": b for i, b in enumerate(boxes)}
        for li, ln in enumerate(lines):
            if li in used_lines or not ln.text.strip() or ln.text.strip() == "+":
                continue
            cx, cy = (ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2
            for reaction in doc.reactions:
                a = next((x for x in doc.arrows if x.id == reaction.arrow), None)
                rb = [boxes_by_id[i] for i in reaction.reactants if i in boxes_by_id]
                pb = [boxes_by_id[i] for i in reaction.products if i in boxes_by_id]
                if a is None or not rb or not pb or abs(a.head[0] - a.tail[0]) < abs(a.head[1] - a.tail[1]):
                    continue
                gx0, gx1 = sorted((max(b[2] for b in rb), min(b[0] for b in pb)))
                ay = (a.tail[1] + a.head[1]) / 2
                span = max(b[3] for b in rb + pb) - min(b[1] for b in rb + pb)
                if gx0 <= cx <= gx1 and abs(cy - ay) < 0.75 * span:
                    text_n += 1
                    tb = TextBlock(id=f"t{text_n}", bbox=list(ln.bbox), text=ln.text)
                    doc.texts.append(tb)
                    (reaction.conditions_above if cy < ay else reaction.conditions_below).append(tb.id)
                    used_lines.add(li)
                    break

        # read conditions arrow segment by segment (left to right), then top-down
        tmap = {t.id: t for t in doc.texts}
        seg = 4 * self._bond_hint(doc)
        for reaction in doc.reactions:
            key = lambda tid: (int(((tmap[tid].bbox[0] + tmap[tid].bbox[2]) / 2) // seg), tmap[tid].bbox[1])  # noqa: E731
            reaction.conditions_above.sort(key=key)
            reaction.conditions_below.sort(key=key)

        # remaining lines: free text (labels, numbering ...)
        for li, ln in enumerate(lines):
            if li in used_lines or not ln.text.strip() or ln.text.strip() == "+":
                continue
            text_n += 1
            doc.texts.append(TextBlock(id=f"t{text_n}", bbox=list(ln.bbox), text=ln.text))


def _merge_partial_reactions(layout: list[LayoutReaction]) -> list[LayoutReaction]:
    """A multi-step arrow through an intermediate written as text ('C11H18O')
    comes back as 'A -> ?' and '? -> B'; join such neighbours into A -> B."""
    out: list[LayoutReaction] = []
    for rx in layout:
        prev = out[-1] if out else None
        mols = lambda bs: [b for b in bs if b.kind == "mol"]  # noqa: E731
        if prev is not None and not mols(prev.products) and not mols(rx.reactants) and mols(rx.products):
            prev.conditions.extend(prev.products + rx.reactants)  # the intermediate's text
            prev.conditions.extend(rx.conditions)
            prev.products.extend(rx.products)
            continue
        out.append(rx)
    return [rx for rx in out if [b for b in rx.reactants + rx.products if b.kind == "mol"]]


def _merge_partial_roles(layout: list[LayoutReaction], roles: list[dict]):
    """Same as _merge_partial_reactions, after text boxes were removed from the
    molecule list (an intermediate written as a formula)."""
    out_l: list[LayoutReaction] = []
    out_r: list[dict] = []
    for rx, role in zip(layout, roles):
        if out_r and not out_r[-1]["products"] and not role["reactants"] and role["products"]:
            out_l[-1].conditions.extend(rx.conditions + [b for b in rx.reactants if b.kind != "mol"])
            out_r[-1]["products"] = list(role["products"])
            continue
        out_l.append(rx)
        out_r.append({k: list(v) for k, v in role.items()})
    keep = [k for k, r in enumerate(out_r) if r["reactants"] or r["products"]]
    return [out_l[k] for k in keep], [out_r[k] for k in keep]


def _words(lines: list[TextLine]):
    """Split OCR lines into words with an estimated x-range per word."""
    out = []
    for ln in lines:
        x0, y0, x1, y1 = ln.bbox
        total = max(1, len(ln.text))
        pos = 0
        for word in ln.text.split(" "):
            start, end = pos, pos + len(word)
            pos = end + 1
            w = word.strip(",;:-—")
            if w:
                out.append((w, x0 + (x1 - x0) * start / total, x0 + (x1 - x0) * end / total, y0, y1, ln.confidence))
        # a lost subscript can split one label into two words: "COCO CH3"
        words = [w for w in out if w[3] == y0 and w[4] == y1]
        for a, b in zip(words, words[1:]):
            if len(a[0]) < 2 or len(b[0]) < 2:  # never glue a lone "H" / "N" onto a label
                continue
            for glue in ("2", ""):
                out.append((a[0] + glue + b[0], a[1], b[2], y0, y1, ln.confidence))
    return out


def _ocr_fix_labels(symbols: list[str], px: list[tuple[float, float]], edges, lines: list[TextLine]):
    """MolScribe sometimes hallucinates a label ('p-Tolyl' -> 'PMBO', 'OMOM' ->
    'OMM'). The OCR text printed at the same place is used instead when it is a
    known group and disagrees with the model."""
    from .chem import abbreviations as abbr
    from .chem.condensed import parse as parse_condensed
    from .chem.structure import _parse_atom_label, _strip_brackets

    if not lines:
        return symbols, []
    n = len(symbols)
    lengths = [
        float(np.hypot(px[i][0] - px[j][0], px[i][1] - px[j][1]))
        for i in range(n) for j in range(i + 1, n) if edges[i][j]
    ]
    bond = float(np.median(lengths)) if lengths else 30.0
    words = _words(lines)
    out, notes = list(symbols), []
    chosen: dict[int, str] = {}
    for i, sym in enumerate(symbols):
        lab = _strip_brackets(sym).replace("@", "")
        if len(lab) < 2 or _parse_atom_label(lab) is not None:
            continue
        x, y = px[i]
        near = []
        for w, wx0, wx1, wy0, wy1, conf in words:
            d = max(0.0, wx0 - x, x - wx1) + max(0.0, wy0 - y, y - wy1)
            if d < 0.6 * bond:
                near.append((w, conf, d))
        if not near:
            continue

        def known(t: str) -> bool:
            return abbr.lookup(t) is not None or parse_condensed(t) is not None or abbr.is_rgroup(t)

        if any(w.lower() == lab.lower() for w, _, _ in near):
            continue  # the model agrees with the printed text
        valid = [(w, c, d) for w, c, d in near if len(w) >= 2 and _parse_atom_label(w) is None and known(w)]
        if not valid:
            continue
        # prefer the closest word, then the longest valid reading
        tok, conf, _ = min(valid, key=lambda t: (round(t[2] / max(bond * 0.2, 1)), -len(t[0])))
        lab_known = abbr.lookup(lab) is not None
        strip = lambda t: re.sub(r"[\d\-]", "", t).lower()  # noqa: E731
        if lab_known and strip(tok) == strip(lab):
            continue  # same label, OCR only lost a subscript (CO2Me read as COMe)
        # a valid model label is only overruled by a dictionary group, never by
        # something that merely parses (Me + stray I -> "MeI")
        if lab_known and abbr.lookup(tok) is None:
            continue
        if not lab_known or (conf >= 0.5 and len(tok) >= 3):
            out[i] = f"[{tok}]"
            chosen[i] = tok
            notes.append(f"Nhãn \"{lab}\" được sửa theo chữ trong ảnh thành \"{tok}\"")
    # MolScribe sometimes splits one long label into two bonded label atoms that
    # now carry the same text: keep the one attached to the skeleton
    drop: set[int] = set()
    for i in chosen:
        for j in chosen:
            if i < j and chosen[i] == chosen[j]:
                deg = lambda k: sum(1 for m in range(n) if edges[k][m] and m not in (i, j))  # noqa: E731
                if edges[i][j] or min(deg(i), deg(j)) == 0:
                    drop.add(j if deg(i) >= deg(j) else i)
    if drop:
        out = [("[*drop*]" if k in drop else s_) for k, s_ in enumerate(out)]
    return out, notes


def _drop_text_boxes(mols: list[Molecule], boxes: list[Box], roles: list[dict], lines: list[TextLine]):
    """A 'molecule' box that is mostly OCR text (a formula such as C17H14N2O3
    or a phrase) and reads poorly is text, not a structure."""
    drop: set[int] = set()
    for k, (m, b) in enumerate(zip(mols, boxes)):
        area = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
        covered = 0.0
        for ln in lines:
            cx, cy = (ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2
            if _center_in((cx, cy), b):
                covered += (ln.bbox[2] - ln.bbox[0]) * (ln.bbox[3] - ln.bbox[1])
        if covered / area > 0.35 and (m.confidence or 0) < 0.75:
            drop.add(k)
    if not drop:
        return mols, boxes, roles
    keep = [k for k in range(len(mols)) if k not in drop]
    remap = {old: new for new, old in enumerate(keep)}
    new_mols = []
    for new, old in enumerate(keep):
        m = mols[old]
        m.id = f"m{new + 1}"
        new_mols.append(m)
    new_roles = [
        {name: [remap[i] for i in idxs if i in remap] for name, idxs in role.items()} for role in roles
    ]
    return new_mols, [boxes[k] for k in keep], new_roles


def _trim_line(ln: TextLine, boxes: list[Box]) -> TextLine:
    """An OCR line can run into a molecule ('THF/H2O BocHN' where BocHN is an atom
    label). Estimate each word's position from its characters and drop words
    lying inside a molecule box."""
    x0, y0, x1, y1 = ln.bbox
    cy = (y0 + y1) / 2
    hits = [b for b in boxes if b[1] <= cy <= b[3] and b[0] < x1 and b[2] > x0]
    if not hits or " " not in ln.text:
        return ln
    total = len(ln.text)
    words, pos = [], 0
    for word in ln.text.split(" "):
        start, end = pos, pos + len(word)
        pos = end + 1
        wx = x0 + (x1 - x0) * ((start + end) / 2) / max(1, total)
        if not any(b[0] <= wx <= b[2] for b in hits):
            words.append((word, x0 + (x1 - x0) * start / total, x0 + (x1 - x0) * end / total))
    if not words or len(words) == len(ln.text.split(" ")):
        return ln
    return TextLine(" ".join(w for w, _, _ in words).strip(), (words[0][1], y0, words[-1][2], y1), ln.confidence)


def _join_lines(lines: list[TextLine]) -> str:
    """Join OCR lines of a condition block; lines on the same row are merged."""
    rows: list[list[TextLine]] = []
    for ln in lines:
        cy = (ln.bbox[1] + ln.bbox[3]) / 2
        if rows:
            last = rows[-1][-1]
            if abs((last.bbox[1] + last.bbox[3]) / 2 - cy) < 0.5 * (ln.bbox[3] - ln.bbox[1]):
                rows[-1].append(ln)
                continue
        rows.append([ln])
    return "\n".join(" ".join(x.text for x in sorted(r, key=lambda l: l.bbox[0])) for r in rows)


def _reaction_smiles(doc: Document, reaction: Reaction) -> str:
    by_id = {m.id: m for m in doc.molecules}
    left = ".".join(by_id[i].smiles for i in reaction.reactants if i in by_id and by_id[i].smiles)
    mid = ".".join(by_id[i].smiles for i in reaction.agents if i in by_id and by_id[i].smiles)
    right = ".".join(by_id[i].smiles for i in reaction.products if i in by_id and by_id[i].smiles)
    return f"{left}>{mid}>{right}"
