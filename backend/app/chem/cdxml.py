"""ChemDraw CDXML writer.

Produces a native, fully editable ChemDraw document: molecules (abbreviations
kept as ChemDraw nicknames/fragments), reaction arrows, condition text with
formula subscripts and a <scheme>/<step> so ChemDraw knows reactants/products.
Layout follows the source image.
"""
from __future__ import annotations

import math
import re

import numpy as np
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from rdkit import Chem

from ..engines.ocr import looks_like_formula
from ..schemas import Document
from . import abbreviations as abbr
from .structure import BOND_LENGTH, BuiltMolecule

CD_BOND = 14.4  # ChemDraw ACS-style bond length in points
UNIT_TO_PT = CD_BOND / BOND_LENGTH
FONT_ID = 3
LABEL_SIZE = 10
CAPTION_SIZE = 10
CHAR_W = 6.2  # approx. width of an Arial 10pt capital
MARGIN = 36.0
FACE_PLAIN, FACE_SUPER, FACE_FORMULA = 0, 32, 96


def _f(v: float) -> str:
    return f"{v:.2f}"


class _Ids:
    def __init__(self) -> None:
        self._n = 1000

    def __call__(self) -> int:
        self._n += 1
        return self._n


@dataclass
class _Bounds:
    x0: float = math.inf
    y0: float = math.inf
    x1: float = -math.inf
    y1: float = -math.inf

    def add(self, x: float, y: float, pad: float = 0.0) -> None:
        self.x0 = min(self.x0, x - pad)
        self.y0 = min(self.y0, y - pad)
        self.x1 = max(self.x1, x + pad)
        self.y1 = max(self.y1, y + pad)

    def add_box(self, b: "_Bounds") -> None:
        if b.valid:
            self.add(b.x0, b.y0)
            self.add(b.x1, b.y1)

    @property
    def valid(self) -> bool:
        return self.x0 <= self.x1 and self.y0 <= self.y1

    def bbox(self) -> str:
        return f"{_f(self.x0)} {_f(self.y0)} {_f(self.x1)} {_f(self.y1)}"


@dataclass
class _Placed:
    """A molecule converted to CDXML with its fragment id and bounds."""
    xml: str
    frag_id: int
    bounds: _Bounds = field(default_factory=_Bounds)


# ----------------------------------------------------------------------------- text helpers


def _runs_xml(runs: list[tuple[str, int]], size: int) -> str:
    return "".join(
        f'<s font="{FONT_ID}" size="{size}" color="0" face="{face}">{escape(text)}</s>'
        for text, face in runs if text
    )


def _caption_runs(text: str) -> list[tuple[str, int]]:
    """Condition text -> runs; tokens like Rh2(OAc)4 get the ChemDraw 'formula'
    face so digits are drawn as subscripts."""
    runs: list[tuple[str, int]] = []
    for li, line in enumerate(text.split("\n")):
        if li:
            runs.append(("\n", FACE_PLAIN))
        tokens = line.split(" ")
        for ti, tok in enumerate(tokens):
            if ti:
                runs.append((" ", FACE_PLAIN))
            core = tok.rstrip(",;.")
            tail = tok[len(core):]
            if core and looks_like_formula(core):
                runs.append((core, FACE_FORMULA))
                runs.append((tail, FACE_PLAIN))
            else:
                runs.append((tok, FACE_PLAIN))
    # merge consecutive runs with the same face
    merged: list[tuple[str, int]] = []
    for t, f in runs:
        if merged and merged[-1][1] == f:
            merged[-1] = (merged[-1][0] + t, f)
        else:
            merged.append((t, f))
    return merged


LINE_H = 10.4  # ChemDraw "auto" line height for 10 pt Arial
ASCENT = 7.3
DESCENT = 2.5


def _text_width(text: str) -> float:
    return max((len(l) for l in text.split("\n")), default=1) * CHAR_W * 0.82


def _text_xml(ids: _Ids, text: str, x: float, first_baseline: float,
              justification: str = "Center") -> tuple[str, int, _Bounds]:
    """Caption whose first line's baseline is at first_baseline; x is the
    centre (Center), left edge (Left) or right edge (Right)."""
    tid = ids()
    n = len(text.split("\n"))
    width = _text_width(text)
    x0 = {"Center": x - width / 2, "Left": x, "Right": x - width}[justification]
    b = _Bounds()
    b.add(x0, first_baseline - ASCENT)
    b.add(x0 + width, first_baseline + (n - 1) * LINE_H + DESCENT)
    xml = (
        f'<t id="{tid}" p="{_f(x)} {_f(first_baseline)}" BoundingBox="{b.bbox()}" Z="{tid}" '
        f'CaptionJustification="{justification}" Justification="{justification}" '
        f'LineHeight="auto">{_runs_xml(_caption_runs(text), CAPTION_SIZE)}</t>'
    )
    return xml, tid, b


# ----------------------------------------------------------------------------- molecules


def _atom_label(atom: Chem.Atom, x: float, y: float, nbr_xs: list[float]) -> tuple[str, str] | None:
    """Return (runs-xml, justification) for atoms that need a visible label."""
    z = atom.GetAtomicNum()
    chg = atom.GetFormalCharge()
    iso = atom.GetIsotope()
    if z == 0:
        label = atom.GetProp("dummyLabel") if atom.HasProp("dummyLabel") else "R"
        return _runs_xml([(label, FACE_FORMULA)], LABEL_SIZE), "Left"
    if z == 6 and chg == 0 and iso == 0 and atom.GetDegree() > 0:
        return None
    el = atom.GetSymbol()
    h = atom.GetTotalNumHs()
    hs = "" if h == 0 else ("H" if h == 1 else f"H{h}")
    # H on the left when every bond leaves to the right. ChemDraw reverses
    # right-justified labels itself, so the text stays "OH" and shows "HO".
    h_left = bool(hs) and bool(nbr_xs) and all(nx > x + 0.1 for nx in nbr_xs)
    main = el + hs
    if iso:
        main = f"{iso}{main}"
    if chg:
        mag = abs(chg)
        main += (str(mag) if mag > 1 else "") + ("+" if chg > 0 else "-")
    return _runs_xml([(main, FACE_FORMULA)], LABEL_SIZE), ("Right" if h_left else "Left")


_LABEL_TOKEN = re.compile(r"\([^()]*\)\d*|(?:[a-z]-?)?[A-Z][a-z]?\d*|[^A-Z(]+")


def attach_first_label(label: str) -> str:
    """'EtO2C' -> 'CO2Et', 'TBSO' -> 'OTBS', 'MeO' -> 'OMe' (drawn right-to-left
    label -> the spelling that starts at the attachment atom)."""
    ab = abbr.lookup(label)
    if ab is not None:
        return ab.label
    tokens = _LABEL_TOKEN.findall(label)
    if "".join(tokens) != label or len(tokens) < 2:
        return label
    return "".join(reversed(tokens))


def _label_t(runs_xml: str, x: float, y: float, justification: str, first_len: int = 1) -> str:
    half = CHAR_W * first_len / 2
    px = x - half if justification == "Left" else x + half
    return (
        f'<t p="{_f(px)} {_f(y + 3.6)}" LabelJustification="{justification}" '
        f'LabelAlignment="{justification}">{runs_xml}</t>'
    )


def _node_attrs(atom: Chem.Atom) -> str:
    attrs = []
    z = atom.GetAtomicNum()
    if z == 0:
        attrs.append('NodeType="GenericNickname"')
        label = atom.GetProp("dummyLabel") if atom.HasProp("dummyLabel") else "R"
        attrs.append(f'GenericNickname="{escape(label)}"')
    elif z != 6:
        attrs.append(f'Element="{z}"')
        attrs.append(f'NumHydrogens="{atom.GetTotalNumHs()}"')
    if atom.GetFormalCharge():
        attrs.append(f'Charge="{atom.GetFormalCharge()}"')
    if atom.GetIsotope() and z != 0:
        attrs.append(f'Isotope="{atom.GetIsotope()}"')
    return " ".join(attrs)


def _bond_attrs(bond: Chem.Bond, begin_first: bool) -> str:
    attrs = []
    bt = bond.GetBondType()
    if bt == Chem.BondType.DOUBLE:
        attrs.append('Order="2"')
    elif bt == Chem.BondType.TRIPLE:
        attrs.append('Order="3"')
    elif bt == Chem.BondType.AROMATIC:
        attrs.append('Order="1.5"')
    d = bond.GetBondDir()
    if begin_first:
        if d == Chem.BondDir.BEGINWEDGE:
            attrs.append('Display="WedgeBegin"')
        elif d == Chem.BondDir.BEGINDASH:
            attrs.append('Display="WedgedHashBegin"')
    else:
        if d == Chem.BondDir.BEGINWEDGE:
            attrs.append('Display="WedgeEnd"')
        elif d == Chem.BondDir.BEGINDASH:
            attrs.append('Display="WedgedHashEnd"')
    return " ".join(attrs)


def _prepared(built: BuiltMolecule) -> Chem.Mol:
    mol = Chem.Mol(built.mol)
    try:
        Chem.Kekulize(mol, clearAromaticFlags=True)
    except Exception:
        pass
    try:
        Chem.WedgeMolBonds(mol, mol.GetConformer())
    except Exception:
        pass
    return mol


def molecule_xml(built: BuiltMolecule, ids: _Ids, offset: tuple[float, float],
                 contract_labels: bool = True) -> _Placed:
    """Render one molecule as a CDXML <fragment>. Coordinates: molecule units
    (y up) -> points (y down) + offset."""
    mol = _prepared(built)
    conf = mol.GetConformer()
    ox, oy = offset

    def pt(i: int) -> tuple[float, float]:
        p = conf.GetAtomPosition(i)
        return p.x * UNIT_TO_PT + ox, -p.y * UNIT_TO_PT + oy

    groups = built.groups if contract_labels else []
    group_of: dict[int, int] = {}
    for gi, g in enumerate(groups):
        for a in g.atoms:
            group_of[a] = gi

    frag_id = ids()
    node_id: dict[int, int] = {}
    group_node: dict[int, int] = {}
    bounds = _Bounds()
    parts: list[str] = []

    # plain atoms
    for atom in mol.GetAtoms():
        i = atom.GetIdx()
        if i in group_of:
            continue
        nid = ids()
        node_id[i] = nid
        x, y = pt(i)
        bounds.add(x, y, 4)
        nbr_xs = [pt(n.GetIdx())[0] for n in atom.GetNeighbors()]
        label = _atom_label(atom, x, y, nbr_xs)
        attrs = _node_attrs(atom)
        if label:
            runs, just = label
            parts.append(f'<n id="{nid}" p="{_f(x)} {_f(y)}" Z="{nid}" {attrs}>'
                         f'{_label_t(runs, x, y, just, len(atom.GetSymbol()))}</n>')
        else:
            parts.append(f'<n id="{nid}" p="{_f(x)} {_f(y)}" Z="{nid}" {attrs}/>')

    # contracted abbreviations as ChemDraw fragment nicknames
    for gi, g in enumerate(groups):
        gid = ids()
        group_node[gi] = gid
        ax, ay = pt(g.attach_atom)
        inner_ids: dict[int, int] = {}
        inner: list[str] = []
        inner_frag = ids()
        for a in g.atoms:
            iid = ids()
            inner_ids[a] = iid
            x, y = pt(a)
            inner.append(f'<n id="{iid}" p="{_f(x)} {_f(y)}" Z="{iid}" {_node_attrs(mol.GetAtomWithIdx(a))}/>')
        ext_num = 0
        for b in mol.GetBonds():
            a1, a2 = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
            in1, in2 = a1 in inner_ids, a2 in inner_ids
            if in1 and in2:
                bid = ids()
                inner.append(f'<b id="{bid}" Z="{bid}" B="{inner_ids[a1]}" E="{inner_ids[a2]}" {_bond_attrs(b, True)}/>')
            elif in1 or in2:
                inside, outside = (a1, a2) if in1 else (a2, a1)
                ext_num += 1
                xid = ids()
                ox_, oy_ = pt(outside)
                inner.append(f'<n id="{xid}" p="{_f(ox_)} {_f(oy_)}" Z="{xid}" '
                             f'NodeType="ExternalConnectionPoint" ExternalConnectionNum="{ext_num}"/>')
                bid = ids()
                inner.append(f'<b id="{bid}" Z="{bid}" B="{xid}" E="{inner_ids[inside]}" {_bond_attrs(b, False)}/>')
        nb_x = pt(g.neighbor)[0] if g.neighbor is not None else ax - 1
        just = "Right" if nb_x > ax + 0.1 else "Left"
        # ChemDraw draws right-justified labels in reverse token order, so it
        # must be given the attachment-first spelling ("CO2Et" shows "EtO2C").
        text = attach_first_label(g.label) if just == "Right" else g.label
        label_xml = _label_t(_runs_xml([(text, FACE_FORMULA)], LABEL_SIZE), ax, ay, just)
        width = CHAR_W * 0.8 * len(g.label)
        if just == "Left":
            bounds.add(ax - CHAR_W / 2, ay - 6)
            bounds.add(ax + width, ay + 6)
        else:
            bounds.add(ax - width, ay - 6)
            bounds.add(ax + CHAR_W / 2, ay + 6)
        parts.append(
            f'<n id="{gid}" p="{_f(ax)} {_f(ay)}" Z="{gid}" NodeType="Fragment">'
            f'<fragment id="{inner_frag}">{"".join(inner)}</fragment>{label_xml}</n>'
        )

    def outer_id(i: int) -> int:
        return group_node[group_of[i]] if i in group_of else node_id[i]

    for b in mol.GetBonds():
        a1, a2 = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        g1, g2 = group_of.get(a1), group_of.get(a2)
        if g1 is not None and g1 == g2:
            continue  # inside a nickname
        bid = ids()
        parts.append(f'<b id="{bid}" Z="{bid}" B="{outer_id(a1)}" E="{outer_id(a2)}" {_bond_attrs(b, True)}/>')

    xml = f'<fragment id="{frag_id}" BoundingBox="{bounds.bbox()}" Z="{frag_id}">{"".join(parts)}</fragment>'
    return _Placed(xml=xml, frag_id=frag_id, bounds=bounds)


def _visible_center(built: BuiltMolecule, contract: bool) -> tuple[float, float]:
    conf = built.mol.GetConformer()
    hidden = set()
    if contract:
        for g in built.groups:
            hidden.update(a for a in g.atoms if a != g.attach_atom)
    xs, ys = [], []
    for i in range(built.mol.GetNumAtoms()):
        if i in hidden:
            continue
        p = conf.GetAtomPosition(i)
        xs.append(p.x)
        ys.append(p.y)
    if not xs:
        return 0.0, 0.0
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


# ----------------------------------------------------------------------------- document


def _header(bounds: _Bounds) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<!DOCTYPE CDXML SYSTEM "http://www.cambridgesoft.com/xml/cdxml.dtd" >\n'
        f'<CDXML CreationProgram="ChemImage Converter" Name="scheme.cdxml" BoundingBox="{bounds.bbox()}" '
        'WindowPosition="0 0" WindowSize="0 0" FractionalWidths="yes" InterpretChemically="yes" '
        'ShowAtomQuery="yes" ShowAtomStereo="no" ShowAtomEnhancedStereo="yes" ShowAtomNumber="no" '
        'ShowBondQuery="yes" ShowBondRxn="yes" ShowBondStereo="no" ShowTerminalCarbonLabels="no" '
        'ShowNonTerminalCarbonLabels="no" HideImplicitHydrogens="no" '
        f'LabelFont="{FONT_ID}" LabelSize="{LABEL_SIZE}" LabelFace="96" '
        f'CaptionFont="{FONT_ID}" CaptionSize="{CAPTION_SIZE}" HashSpacing="2.50" MarginWidth="1.60" '
        'LineWidth="0.60" BoldWidth="2" BondLength="14.40" BondSpacing="18" ChainAngle="120" '
        'LabelJustification="Auto" CaptionJustification="Left" AminoAcidTermini="HOH" '
        'ShowSequenceTermini="yes" ShowSequenceBonds="yes" PrintMargins="36 36 36 36" '
        'color="0" bgcolor="1">'
        '<colortable><color r="1" g="1" b="1"/><color r="0" g="0" b="0"/>'
        '<color r="1" g="0" b="0"/><color r="1" g="1" b="0"/><color r="0" g="1" b="0"/>'
        '<color r="0" g="1" b="1"/><color r="0" g="0" b="1"/><color r="1" g="0" b="1"/></colortable>'
        f'<fonttable><font id="{FONT_ID}" charset="iso-8859-1" name="Arial"/></fonttable>'
    )


def _arrow_xml(ids: _Ids, tail, head) -> tuple[str, int, _Bounds]:
    aid = ids()
    b = _Bounds()
    b.add(*tail, 2)
    b.add(*head, 2)
    xml = (
        f'<arrow id="{aid}" BoundingBox="{b.bbox()}" Z="{aid}" FillType="None" ArrowheadHead="Full" '
        f'ArrowheadType="Solid" HeadSize="1000" ArrowheadCenterSize="875" ArrowheadWidth="250" '
        f'Head3D="{_f(head[0])} {_f(head[1])} 0" Tail3D="{_f(tail[0])} {_f(tail[1])} 0"/>'
    )
    return xml, aid, b


def document_to_cdxml(doc: Document, built: dict[str, BuiltMolecule], contract_labels: bool = True,
                      only_molecule: str | None = None) -> str:
    """Whole document (or one molecule) as CDXML.

    Reaction schemes are re-flowed row by row like ChemDraw's own reaction
    layout: order and vertical arrangement follow the image, horizontal
    spacing is computed so labels, '+' signs, arrows and condition text never
    collide at ChemDraw's standard sizes (14.4 pt bonds, 10 pt Arial)."""
    ids = _Ids()
    bond_pxs = [m.bond_px for m in doc.molecules if m.bond_px]
    px_bond = sorted(bond_pxs)[len(bond_pxs) // 2] if bond_pxs else 30.0
    s = CD_BOND / px_bond  # image pixels -> points

    # molecules rendered around their own visible centre (0, 0)
    mols: dict[str, _Placed] = {}
    img_center: dict[str, tuple[float, float]] = {}
    img_span: dict[str, tuple[float, float]] = {}
    order = [m for m in doc.molecules if only_molecule in (None, m.id)]
    for m in order:
        b = built.get(m.id)
        if b is None or b.mol.GetNumAtoms() == 0 or b.mol.GetNumConformers() == 0:
            continue
        cx_u, cy_u = _visible_center(b, contract_labels)
        mols[m.id] = molecule_xml(b, ids, (-cx_u * UNIT_TO_PT, cy_u * UNIT_TO_PT), contract_labels)
        if m.bond_px and m.source in ("image", "region"):
            k = m.bond_px / BOND_LENGTH
            img_center[m.id] = (cx_u * k, -cy_u * k)
        elif m.bbox:
            img_center[m.id] = ((m.bbox[0] + m.bbox[2]) / 2, (m.bbox[1] + m.bbox[3]) / 2)
        else:
            img_center[m.id] = (len(img_center) * 400.0, 0.0)
        if m.bbox:
            img_span[m.id] = (m.bbox[1], m.bbox[3])
        else:
            cy = img_center[m.id][1]
            img_span[m.id] = (cy - 50, cy + 50)

    out = _Scene()
    if only_molecule is not None:
        for mid, pl in mols.items():
            out.add_molecule(mid, pl, 0.0, 0.0)
        return out.to_cdxml(ids, [])

    texts = {t.id: t for t in doc.texts}
    arrows = {a.id: a for a in doc.arrows}
    side_of: dict[str, tuple[str, str]] = {}
    for r in doc.reactions:
        for i in r.reactants:
            side_of.setdefault(i, (r.id, "reactants"))
        for i in r.products:
            side_of.setdefault(i, (r.id, "products"))

    # ---- items to place: molecules + reaction arrows (with their conditions)
    items: list[_Item] = []
    agent_ids = {a for r in doc.reactions for a in r.agents}
    for mid in mols:
        if mid in agent_ids:
            continue  # drawn with their arrow, not in the row
        y0, y1 = img_span[mid]
        items.append(_Item("mol", mid, img_center[mid][0], img_center[mid][1], y0, y1))
    rx_by_arrow = {r.arrow: r for r in doc.reactions if r.arrow}
    for aid, a in arrows.items():
        r = rx_by_arrow.get(aid)
        if r is None:
            continue
        cx, cy = (a.tail[0] + a.head[0]) / 2, (a.tail[1] + a.head[1]) / 2
        y0, y1 = cy - 5, cy + 5
        for tid in r.conditions_above + r.conditions_below:
            if tid in texts:
                y0 = min(y0, texts[tid].bbox[1])
                y1 = max(y1, texts[tid].bbox[3])
        items.append(_Item("arrow", aid, cx, cy, y0, y1, reaction=r))

    horizontal = all(abs(a.head[1] - a.tail[1]) <= abs(a.head[0] - a.tail[0]) for a in arrows.values())
    rx_of: dict[str, str] = {}
    for r in doc.reactions:
        for m in r.reactants + r.products:
            rx_of["mol:" + m] = r.id
        if r.arrow:
            rx_of["arrow:" + r.arrow] = r.id
    rows = _rows(items, rx_of)
    row_of = {(it.kind, it.id): k for k, row in enumerate(rows) for it in row}
    linear = horizontal and all(
        len({row_of.get(("mol", m)) for m in r.reactants + r.products} | {row_of.get(("arrow", r.arrow))}) == 1
        for r in doc.reactions if r.arrow
    )

    steps: list[str] = []
    if not linear:
        _absolute_layout(out, ids, doc, mols, img_center, arrows, texts, s)
    else:
        prev_bottom: float | None = None
        prev_ref: float | None = None
        prev_y: float = 0.0
        for row in rows:
            row.sort(key=lambda it: it.x)
            arrows_in_row = [it for it in row if it.kind == "arrow"]
            ref_img = (sum(it.cy for it in arrows_in_row) / len(arrows_in_row)) if arrows_in_row \
                else sum(it.cy for it in row) / len(row)
            scene = _Scene()
            cursor = 0.0
            prev: _Item | None = None
            for it in row:
                y = (it.cy - ref_img) * s
                if it.kind == "mol":
                    pl = mols[it.id]
                    if prev is not None and prev.kind == "mol":
                        if it.id in side_of and side_of.get(prev.id) == side_of[it.id]:
                            plus_x = cursor + PLUS_GAP + 3
                            scene.add_plus(plus_x, (y + scene.last_center_y) / 2)
                            cursor = plus_x + 3 + PLUS_GAP
                        else:
                            cursor += MOL_GAP
                    dx = cursor - pl.bounds.x0
                    scene.add_molecule(it.id, pl, dx, y)
                    cursor = pl.bounds.x1 + dx
                else:
                    r = it.reaction
                    a = arrows[it.id]
                    above = [texts[i] for i in r.conditions_above if i in texts]
                    below = [texts[i] for i in r.conditions_below if i in texts]
                    agents = [mols[m] for m in r.agents if m in mols]
                    width = max([_text_width(t.text) for t in above + below]
                                + [pl.bounds.x1 - pl.bounds.x0 for pl in agents] + [0.0])
                    length = max(MIN_ARROW, width + 16)
                    tail_x = cursor + ARROW_GAP
                    head_x = tail_x + length
                    if a.head[0] < a.tail[0]:  # arrow pointing left
                        tail_x, head_x = head_x, tail_x
                    scene.add_arrow(it.id, (tail_x, 0.0), (head_x, 0.0), above, below)
                    # reagent structures stacked over the condition text
                    n_above = sum(len(t.text.split("\n")) for t in above)
                    bottom = -(TEXT_GAP + DESCENT + (ASCENT + (n_above - 1) * LINE_H + 2 * len(above) if n_above else 0) + 6)
                    cx_arrow = (tail_x + head_x) / 2
                    for mid_, pl in zip([m for m in r.agents if m in mols], agents):
                        dx = cx_arrow - (pl.bounds.x0 + pl.bounds.x1) / 2
                        dy = bottom - pl.bounds.y1
                        scene.add_molecule(mid_, pl, dx, dy)
                        bottom = dy + pl.bounds.y0 - 6
                    cursor = max(tail_x, head_x) + ARROW_GAP
                prev = it
            scene.flush(ids)
            # free text beside this row (e.g. "1.", "(a)")
            row_y0 = min(it.y0 for it in row)
            row_y1 = max(it.y1 for it in row)
            first_x = row[0].x
            for t in doc.texts:
                if t.id in scene.text_ids or t.text.strip() == "+" or _is_condition(doc, t.id):
                    continue
                tcx, tcy = (t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2
                if not (row_y0 - 10 <= tcy <= row_y1 + 10):
                    continue
                ty = (tcy - ref_img) * s
                if tcx < first_x:
                    scene.add_text(t, scene.bounds.x0 - 10, ty, "Right")
                else:
                    scene.add_text(t, (tcx - first_x) * s + scene.first_x, ty, "Center")
            scene.flush(ids)
            # stack rows: keep the image spacing, never overlap the previous row
            if prev_bottom is None:
                row_y = ref_img * s
            else:
                row_y = prev_y + (ref_img - prev_ref) * s
                top = row_y + scene.bounds.y0
                if top < prev_bottom + ROW_GAP:
                    row_y += prev_bottom + ROW_GAP - top
            out.merge(scene, 0.0, row_y)
            prev_bottom = row_y + scene.bounds.y1
            prev_ref, prev_y = ref_img, row_y

    # remaining free text (not beside any row): below the drawing
    y = (out.bounds.y1 if out.bounds.valid else 0.0) + 18
    for t in sorted(doc.texts, key=lambda t: (t.bbox[1], t.bbox[0])):
        if t.id in out.text_ids or t.text.strip() == "+" or _is_condition(doc, t.id):
            continue
        out.add_text(t, (out.bounds.x0 if out.bounds.valid else 0.0), y, "Left")
        y += LINE_H * (len(t.text.split("\n")) + 0.4)

    for r in doc.reactions:
        frag = lambda xs: " ".join(str(out.frag_of[x]) for x in xs if x in out.frag_of)  # noqa: E731
        tx = lambda xs: " ".join(str(out.text_of[x]) for x in xs if x in out.text_of)  # noqa: E731
        attrs = [f'ReactionStepReactants="{frag(r.reactants)}"', f'ReactionStepProducts="{frag(r.products)}"']
        if r.arrow in out.arrow_of:
            attrs.append(f'ReactionStepArrows="{out.arrow_of[r.arrow]}"')
        above_ids = " ".join(x for x in (frag(r.agents), tx(r.conditions_above)) if x)
        if above_ids:
            attrs.append(f'ReactionStepObjectsAboveArrow="{above_ids}"')
        if tx(r.conditions_below):
            attrs.append(f'ReactionStepObjectsBelowArrow="{tx(r.conditions_below)}"')
        steps.append(f'<step id="{ids()}" {" ".join(attrs)}/>')
    return out.to_cdxml(ids, steps)


def _absolute_layout(out: "_Scene", ids: _Ids, doc: Document, mols: dict, img_center: dict,
                     arrows: dict, texts: dict, s: float) -> None:
    """Multi-row / branched schemes (vertical or U-shaped arrows): keep every
    object where it is in the image, spread the drawing just enough that
    molecules at ChemDraw size do not collide, then trim arrows to the gaps."""
    centres = {mid: (img_center[mid][0] * s, img_center[mid][1] * s) for mid in mols}

    def box(mid: str, k: float) -> _Bounds:
        b, (cx, cy) = mols[mid].bounds, centres[mid]
        return _Bounds(b.x0 + cx * k, b.y0 + cy * k, b.x1 + cx * k, b.y1 + cy * k)

    def collide(k: float) -> bool:
        ids_ = list(mols)
        for x in range(len(ids_)):
            a = box(ids_[x], k)
            for y in range(x + 1, len(ids_)):
                b = box(ids_[y], k)
                if a.x0 < b.x1 + 8 and b.x0 < a.x1 + 8 and a.y0 < b.y1 + 8 and b.y0 < a.y1 + 8:
                    return True
        return False

    k = 1.0
    while k < 3.0 and collide(k):
        k += 0.1

    scene = _Scene()
    placed: dict[str, _Bounds] = {}
    for mid, pl in mols.items():
        cx, cy = centres[mid]
        scene.add_molecule(mid, pl, cx * k, cy * k)
        placed[mid] = box(mid, k)

    def union(ids_: list[str]) -> _Bounds | None:
        bs = [placed[i] for i in ids_ if i in placed]
        if not bs:
            return None
        u = _Bounds()
        for b in bs:
            u.add_box(b)
        return u

    def inside(p, b: _Bounds | None, pad: float) -> bool:
        return b is not None and b.x0 - pad <= p[0] <= b.x1 + pad and b.y0 - pad <= p[1] <= b.y1 + pad

    by_arrow = {r.arrow: r for r in doc.reactions if r.arrow}
    for aid, a in arrows.items():
        r = by_arrow.get(aid)
        tail = np.array(a.tail) * s * k
        head = np.array(a.head) * s * k
        if r is not None:
            vec = head - tail
            length = float(np.linalg.norm(vec))
            if length > 1e-6:
                u = vec / length
                rb, pb = union(r.reactants), union(r.products)
                for _ in range(400):  # walk the tail out of the reactants
                    if not inside(tail, rb, ARROW_GAP) or np.linalg.norm(head - tail) < 24:
                        break
                    tail = tail + u
                for _ in range(400):  # and the head out of the products
                    if not inside(head, pb, ARROW_GAP) or np.linalg.norm(head - tail) < 24:
                        break
                    head = head - u
        above = [texts[i] for i in (r.conditions_above if r else []) if i in texts]
        below = [texts[i] for i in (r.conditions_below if r else []) if i in texts]
        sides = {
            t.id: ("left" if (t.bbox[0] + t.bbox[2]) / 2 * s * k < (tail[0] + head[0]) / 2 else "right")
            for t in above + below
        }
        scene.add_arrow(aid, (float(tail[0]), float(tail[1])), (float(head[0]), float(head[1])), above, below, sides)

    for r in doc.reactions:
        for group in (r.reactants, r.products):
            bs = sorted((placed[i] for i in group if i in placed), key=lambda b: b.x0)
            for b1, b2 in zip(bs, bs[1:]):
                if b2.x0 > b1.x1:
                    scene.add_plus((b1.x1 + b2.x0) / 2, ((b1.y0 + b1.y1) / 2 + (b2.y0 + b2.y1) / 2) / 2)

    cond = {i for r in doc.reactions for i in r.conditions_above + r.conditions_below}
    for t in doc.texts:
        if t.id in cond or t.text.strip() == "+":
            continue
        cx = (t.bbox[0] + t.bbox[2]) / 2 * s * k
        cy = (t.bbox[1] + t.bbox[3]) / 2 * s * k
        scene.add_text(t, cx, cy, "Center")
    scene.flush(ids)
    out.merge(scene, 0.0, 0.0)


def _is_condition(doc: Document, tid: str) -> bool:
    return any(tid in r.conditions_above or tid in r.conditions_below for r in doc.reactions)


PLUS_GAP = 9.0
MOL_GAP = 28.0
MIN_ARROW = 46.0
ROW_GAP = 22.0


@dataclass
class _Item:
    kind: str  # "mol" | "arrow"
    id: str
    x: float  # image centre
    cy: float
    y0: float  # image vertical span
    y1: float
    reaction: object = None


def _rows(items: list[_Item], same_reaction: dict[str, str] | None = None) -> list[list[_Item]]:
    """Group items into rows: overlapping vertical spans, and everything that
    belongs to one reaction (stacked reactants A over B still form one row)."""
    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for a in range(n):
        for b in range(a + 1, n):
            ia, ib = items[a], items[b]
            overlap = min(ia.y1, ib.y1) - max(ia.y0, ib.y0)
            if overlap > 0.3 * min(ia.y1 - ia.y0, ib.y1 - ib.y0):
                union(a, b)
            elif same_reaction:
                ra = same_reaction.get(ia.kind + ":" + ia.id)
                rb = same_reaction.get(ib.kind + ":" + ib.id)
                if ra and ra == rb:
                    union(a, b)
    groups: dict[int, list[_Item]] = {}
    for k in range(n):
        groups.setdefault(find(k), []).append(items[k])
    return sorted(groups.values(), key=lambda g: min(i.y0 for i in g))


class _Scene:
    """Collects positioned CDXML objects; every object is stored with its own
    translation so whole rows can be moved."""

    def __init__(self) -> None:
        self.parts: list[tuple[str, float, float]] = []  # (xml, dx, dy)
        self.bounds = _Bounds()
        self.frag_of: dict[str, int] = {}
        self.text_of: dict[str, int] = {}
        self.arrow_of: dict[str, int] = {}
        self.text_ids: set[str] = set()
        self.last_center_y = 0.0
        self.first_x = 0.0
        self._pending: list[tuple[str, object]] = []
        self._children: list[tuple["_Scene", float, float]] = []

    def _grow(self, b: _Bounds, dx: float, dy: float) -> None:
        if b.valid:
            if not self.bounds.valid:
                self.first_x = b.x0 + dx
            self.bounds.add(b.x0 + dx, b.y0 + dy)
            self.bounds.add(b.x1 + dx, b.y1 + dy)

    def add_molecule(self, mid: str, pl: _Placed, dx: float, dy: float) -> None:
        self.parts.append((pl.xml, dx, dy))
        self._grow(pl.bounds, dx, dy)
        self.frag_of[mid] = pl.frag_id
        self.last_center_y = dy  # molecules are drawn around their visible centre

    def add_plus(self, x: float, y: float) -> None:
        self._pending.append(("plus", (x, y)))

    def add_arrow(self, aid: str, tail, head, above, below, sides=None) -> None:
        self._pending.append(("arrow", (aid, tail, head, above, below, sides or {})))

    def add_text(self, t, x: float, y: float, just: str) -> None:
        self._pending.append(("text", (t, x, y, just)))

    def flush(self, ids: _Ids) -> None:
        self._flush(ids)

    def _flush(self, ids: _Ids) -> None:
        for kind, data in self._pending:
            if kind == "plus":
                x, y = data
                xml, _, tb = _text_xml(ids, "+", x, y + ASCENT / 2)
                self.parts.append((xml, 0.0, 0.0))
                self._grow(tb, 0, 0)
            elif kind == "arrow":
                aid, tail, head, above, below, sides = data
                xml, xid, ab = _arrow_xml(ids, tail, head)
                self.parts.append((xml, 0.0, 0.0))
                self._grow(ab, 0, 0)
                self.arrow_of[aid] = xid
                for txml, tid, tb, src in _layout_conditions(ids, tail, head, above, below, sides):
                    self.parts.append((txml, 0.0, 0.0))
                    self._grow(tb, 0, 0)
                    self.text_of[src] = tid
                    self.text_ids.add(src)
            else:
                t, x, y, just = data
                n = len(t.text.split("\n"))
                first = y - (n - 1) * LINE_H / 2 + ASCENT / 2
                xml, tid, tb = _text_xml(ids, t.text, x, first, just)
                self.parts.append((xml, 0.0, 0.0))
                self._grow(tb, 0, 0)
                self.text_of[t.id] = tid
                self.text_ids.add(t.id)
        self._pending.clear()

    def merge(self, other: "_Scene", dx: float, dy: float) -> None:
        """Attach a (flushed) row scene, translated by (dx, dy)."""
        self._children.append((other, dx, dy))
        self.text_ids |= other.text_ids
        if other.bounds.valid:
            self.bounds.add(other.bounds.x0 + dx, other.bounds.y0 + dy)
            self.bounds.add(other.bounds.x1 + dx, other.bounds.y1 + dy)

    def to_cdxml(self, ids: _Ids, steps: list[str]) -> str:
        self._flush(ids)
        parts = list(self.parts)
        bounds = _Bounds()
        bounds.add_box(self.bounds)
        for child, cdx, cdy in self._children:
            child._flush(ids)
            for xml, dx, dy in child.parts:
                parts.append((xml, dx + cdx, dy + cdy))
            self.frag_of.update(child.frag_of)
            self.text_of.update(child.text_of)
            self.arrow_of.update(child.arrow_of)
        if not bounds.valid:
            bounds.add(0, 0)
        gx, gy = MARGIN - bounds.x0, MARGIN - bounds.y0
        body = "".join(_translate(xml, dx + gx, dy + gy) for xml, dx, dy in parts)
        page_w = bounds.x1 - bounds.x0 + 2 * MARGIN
        page_h = bounds.y1 - bounds.y0 + 2 * MARGIN
        wp, hp = max(1, math.ceil(page_w / 540)), max(1, math.ceil(page_h / 720))
        final = _Bounds(MARGIN, MARGIN, bounds.x1 + gx, bounds.y1 + gy)
        scheme = f'<scheme id="{ids()}">{"".join(steps)}</scheme>' if steps else ""
        return (
            _header(final)
            + f'<page id="{ids()}" BoundingBox="0 0 {_f(540 * wp)} {_f(720 * hp)}" '
            f'HeaderPosition="36" FooterPosition="36" PrintTrimMarks="yes" '
            f'HeightPages="{hp}" WidthPages="{wp}">'
            + body + scheme + "</page></CDXML>\n"
        )


ARROW_GAP = 7.0  # distance between arrow ends and molecules
TEXT_GAP = 3.5  # distance between condition text and the arrow


def _layout_conditions(ids: _Ids, tail, head, above, below, sides=None):
    """Condition text stacked directly above / below a horizontal arrow, or to
    the right of a vertical one."""
    out = []
    horizontal = abs(head[0] - tail[0]) >= abs(head[1] - tail[1])
    if horizontal:
        cx = (tail[0] + head[0]) / 2
        y = (tail[1] + head[1]) / 2
        bottom = y - TEXT_GAP - DESCENT  # baseline of the lowest line above
        for t in reversed(above):
            n = len(t.text.split("\n"))
            first = bottom - (n - 1) * LINE_H
            xml, tid, tb = _text_xml(ids, t.text, cx, first)
            out.append((xml, tid, tb, t.id))
            bottom = first - ASCENT - 2.0 - DESCENT
        top = y + TEXT_GAP + ASCENT  # baseline of the first line below
        for t in below:
            n = len(t.text.split("\n"))
            xml, tid, tb = _text_xml(ids, t.text, cx, top)
            out.append((xml, tid, tb, t.id))
            top += n * LINE_H + 2.0
    else:
        # vertical arrow: text beside it, on the side it was in the image
        sides = sides or {}
        yc = (tail[1] + head[1]) / 2
        for side in ("left", "right"):
            texts = [t for t in above + below if sides.get(t.id, "right") == side]
            if not texts:
                continue
            total = sum(len(t.text.split("\n")) for t in texts) + 0.3 * (len(texts) - 1)
            first = yc - (total - 1) * LINE_H / 2 + ASCENT / 2
            x = (min(tail[0], head[0]) - 6.0) if side == "left" else (max(tail[0], head[0]) + 6.0)
            for t in texts:
                xml, tid, tb = _text_xml(ids, t.text, x, first, "Right" if side == "left" else "Left")
                out.append((xml, tid, tb, t.id))
                first += (len(t.text.split("\n")) + 0.3) * LINE_H
    return out


def _translate(xml: str, dx: float, dy: float) -> str:
    """Shift every p / BoundingBox / Head3D / Tail3D coordinate attribute."""
    import re

    def shift_pairs(vals: list[float]) -> list[float]:
        return [v + (dx if i % 2 == 0 else dy) for i, v in enumerate(vals)]

    def repl_p(m: re.Match) -> str:
        vals = [float(v) for v in m.group(2).split()]
        return f'{m.group(1)}="{" ".join(_f(v) for v in shift_pairs(vals))}"'

    def repl_3d(m: re.Match) -> str:
        x, y, z = (float(v) for v in m.group(2).split())
        return f'{m.group(1)}="{_f(x + dx)} {_f(y + dy)} {z:g}"'

    xml = re.sub(r'\b(p|BoundingBox)="([-0-9. ]+)"', repl_p, xml)
    xml = re.sub(r'\b(Head3D|Tail3D)="([-0-9. ]+)"', repl_3d, xml)
    return xml
