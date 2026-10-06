"""Turn a recognised molecular graph (atoms + bonds with image coordinates) into an
RDKit molecule with 2D coordinates, expanded abbreviations and stereochemistry.

Abbreviations (CO2Et, Ph, N2 ...) are expanded into real atoms so the chemistry
is exact, and recorded as ``AbbrevGroup`` so exports can show them contracted
again (molfile SUP S-groups, ChemDraw fragment nicknames, SVG labels).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Geometry import Point3D

from . import abbreviations as abbr

Chem.SetDefaultPickleProperties(Chem.PropertyPickleOptions.AllProps)
rdDepictor.SetPreferCoordGen(True)

BOND_LENGTH = 1.5  # Å-like units used for molfile / RDKit coordinates

# Elements accepted as plain atom labels. Ac, Pr, Ts, Bu ... are deliberately
# excluded: in organic drawings they are abbreviations, not elements.
_ATOM_ELEMENTS = {
    "H", "D", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I", "Se", "Te", "Ge", "As",
    "Li", "Na", "K", "Cs", "Mg", "Ca", "Ba", "Al", "Sn", "Pb", "Sb", "Bi", "Ti", "Zr", "V", "Cr",
    "Mo", "Mn", "Fe", "Ru", "Co", "Rh", "Ir", "Ni", "Pd", "Pt", "Cu", "Ag", "Au", "Zn", "Hg",
}
# Rare elements are almost always misread labels (Hf for HN, Ho, W, Ar = aryl ...)
# and are rejected so the label goes through abbreviation matching instead.
_CONDENSED_ELEMENTS = {"H", "D", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I", "Se", "Sn", "Li", "Na", "K", "Mg"}
_AROMATIC_LOWER = {"c": "C", "n": "N", "o": "O", "s": "S", "p": "P", "b": "B", "se": "Se"}
_ATOM_LABEL_RE = re.compile(
    r"^(?P<el>[A-Z][a-z]?|c|n|o|s|p|b|se)(?P<h>H\d*)?(?P<chg>(\+\d*|-\d*|\++|-+))?$"
)


@dataclass
class AbbrevGroup:
    label: str
    atoms: list[int]  # all atoms of the expanded group
    attach_atom: int  # group atom bonded to the skeleton
    neighbor: int | None  # skeleton atom it is bonded to
    position: tuple[float, float] = (0.0, 0.0)  # label position (molecule coords)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "atoms": self.atoms,
            "attach_atom": self.attach_atom,
            "neighbor": self.neighbor,
        }


@dataclass
class BuiltMolecule:
    mol: Chem.Mol
    groups: list[AbbrevGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    bond_px: float | None = None  # source-image pixels per bond (absolute coords)
    unknown_labels: int = 0  # labels kept as R/dummy because they were not understood
    fuzzy_labels: int = 0  # labels snapped to the closest known abbreviation

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------- helpers


def _strip_brackets(symbol: str) -> str:
    s = symbol.strip()
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        return s[1:-1]
    return s


def _parse_atom_label(label: str) -> Chem.Atom | None:
    """'O', 'OH', 'NH2', 'N+', 'O-', 'c', 'nH' -> atom; anything else -> None."""
    if label == "*":
        return Chem.Atom(0)
    # MolScribe writes stereocentres as C@H / C@@H; chirality itself is taken
    # from the wedge bonds, so the SMILES chirality marks are dropped.
    label = label.replace("@", "")
    m = _ATOM_LABEL_RE.match(label)
    if not m:
        # bracket-atom syntax such as 13CH3, 2H
        atom = Chem.AtomFromSmiles(f"[{label}]")
        if atom is not None and atom.GetSymbol() in _ATOM_ELEMENTS:
            atom.SetNoImplicit(False)
            return atom
        return None
    el = m.group("el")
    aromatic = el in _AROMATIC_LOWER
    if aromatic:
        el = _AROMATIC_LOWER[el]
    if el not in _ATOM_ELEMENTS:
        return None
    if el == "D":
        atom = Chem.Atom(1)
        atom.SetIsotope(2)
    else:
        atom = Chem.Atom(el)
    h = m.group("h")
    if h:
        atom.SetIntProp("_drawnH", int(h[1:] or 1))
    chg = m.group("chg")
    if chg:
        sign = 1 if chg[0] == "+" else -1
        rest = chg[1:]
        if rest.isdigit():
            n = int(rest)
        else:
            n = len(chg)
        atom.SetFormalCharge(sign * n)
    if aromatic:
        atom.SetIsAromatic(True)
    return atom


def _condensed_to_smiles(label: str, start_bond: int, end_bond: int | None, direction: int) -> str | None:
    """Condensed formula (e.g. CH2CH2OH, OCH2O) -> SMILES whose first atom is the
    start attachment. Uses MolScribe's formula parser."""
    try:
        from molscribe.chemistry import (
            _condensed_formula_list_to_smiles,
            _expand_carbon,
            _parse_formula,
        )
    except Exception:  # pragma: no cover
        return None
    if len(label) > 24:
        return None
    try:
        formula_list = _expand_carbon(_parse_formula(label))
        smiles, bonds_left, _, ok = _condensed_formula_list_to_smiles(
            formula_list, start_bond, end_bond, direction
        )
    except Exception:
        return None
    if not ok or not smiles:
        return None
    # reject parses that only "work" by inventing exotic elements (BocHf -> Hf)
    check = Chem.MolFromSmiles(smiles, sanitize=False)
    if check is None or any(
        a.GetAtomicNum() != 0 and a.GetSymbol() not in _CONDENSED_ELEMENTS for a in check.GetAtoms()
    ):
        return None
    return smiles


def _rotate_place(coords: np.ndarray, anchor_idx: int, toward_idx: int,
                  anchor_pos: np.ndarray, toward_pos: np.ndarray) -> np.ndarray:
    """Rigidly move fragment coords so coords[anchor] -> anchor_pos and the
    anchor->toward direction matches anchor_pos->toward_pos. RDKit depictions
    already use BOND_LENGTH, so no scaling is needed."""
    v_src = coords[toward_idx] - coords[anchor_idx]
    v_dst = toward_pos - anchor_pos
    a = math.atan2(v_dst[1], v_dst[0]) - math.atan2(v_src[1], v_src[0])
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return (coords - coords[anchor_idx]) @ rot.T + anchor_pos


def _fragment_with_coords(smiles: str) -> Chem.Mol | None:
    frag = Chem.MolFromSmiles(smiles)
    if frag is None:
        frag = Chem.MolFromSmiles(smiles, sanitize=False)
        if frag is None:
            return None
        frag.UpdatePropertyCache(strict=False)
    rdDepictor.Compute2DCoords(frag)
    # CoordGen depicts with unit bonds; match the skeleton's BOND_LENGTH
    conf = frag.GetConformer()
    lengths = [
        (conf.GetAtomPosition(b.GetBeginAtomIdx()) - conf.GetAtomPosition(b.GetEndAtomIdx())).Length()
        for b in frag.GetBonds()
    ]
    if lengths:
        k = BOND_LENGTH / float(np.median(lengths))
        for i in range(frag.GetNumAtoms()):
            p = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, Point3D(p.x * k, p.y * k, 0.0))
    return frag


# --------------------------------------------------------------------------- main API


def build_molecule(
    symbols: list[str],
    coords_px: list[tuple[float, float]],
    edges: list[list[int]],
) -> BuiltMolecule:
    """Build a molecule from a MolScribe-style graph.

    symbols: atom labels ("C", "[EtO2C]", "[N+]" ...)
    coords_px: atom positions in image pixels (y pointing down)
    edges: n x n matrix: 0 none, 1 single, 2 double, 3 triple, 4 aromatic,
           5/6 stereo single (MolScribe convention, see _resolve_wedges)
    """
    warnings: list[str] = []
    errors: list[str] = []
    symbols, coords_px, edges, dropped = _drop_stray_atoms(symbols, coords_px, edges)
    if dropped:
        warnings.append(f"Đã bỏ ký tự rời không thuộc phân tử: {', '.join(dropped)}")
    n = len(symbols)
    if n == 0:
        return BuiltMolecule(Chem.Mol(), errors=["Không nhận dạng được nguyên tử nào"])

    pts = np.asarray(coords_px, dtype=float).reshape(n, 2)
    # bond length in pixels -> scale to BOND_LENGTH units, flip y (molfile y is up)
    lengths = [
        float(np.linalg.norm(pts[i] - pts[j]))
        for i in range(n) for j in range(i + 1, n) if edges[i][j]
    ]
    px_bond = float(np.median(lengths)) if lengths else 30.0
    px_bond = max(px_bond, 1e-3)
    pos = np.stack([pts[:, 0], -pts[:, 1]], axis=1) * (BOND_LENGTH / px_bond)

    rw = Chem.RWMol()
    kinds: list[str] = []  # "atom" | "group" | "rgroup" | "unknown"
    labels: list[str] = []
    for sym in symbols:
        label = _strip_brackets(sym)
        labels.append(label)
        atom = _parse_atom_label(label)
        if atom is not None:
            kinds.append("atom")
        elif abbr.lookup(label) is not None:
            atom = Chem.Atom(0)
            kinds.append("group")
        elif abbr.is_rgroup(label):
            atom = Chem.Atom(0)
            m = re.match(r"^R(\d+)$", label)
            if m:
                atom.SetIsotope(int(m.group(1)))
            kinds.append("rgroup")
        else:
            atom = Chem.Atom(0)
            kinds.append("group")  # try condensed formula later
        if atom.GetAtomicNum() == 0:
            atom.SetProp("dummyLabel", label)
            atom.SetProp("molFileAlias", label)
        atom.SetNoImplicit(False)
        rw.AddAtom(atom)

    # ---- bonds
    wedge_candidates: list[tuple[int, int, int]] = []  # (i, j, code) from edges[i][j]
    for i in range(n):
        for j in range(i + 1, n):
            e = int(edges[i][j])
            if e == 0:
                continue
            if e == 1:
                rw.AddBond(i, j, Chem.BondType.SINGLE)
            elif e == 2:
                rw.AddBond(i, j, Chem.BondType.DOUBLE)
            elif e == 3:
                rw.AddBond(i, j, Chem.BondType.TRIPLE)
            elif e == 4:
                rw.AddBond(i, j, Chem.BondType.AROMATIC)
                rw.GetBondBetweenAtoms(i, j).SetIsAromatic(True)
                rw.GetAtomWithIdx(i).SetIsAromatic(True)
                rw.GetAtomWithIdx(j).SetIsAromatic(True)
            elif e in (5, 6):
                rw.AddBond(i, j, Chem.BondType.SINGLE)
                wedge_candidates.append((i, j, e))

    # ---- expand abbreviations / condensed formulas
    groups: list[AbbrevGroup] = []
    to_remove: list[int] = []
    replaced: dict[int, int] = {}  # label placeholder -> atom that now carries its bonds
    positions: dict[int, np.ndarray] = {i: pos[i] for i in range(n)}

    for i in range(n):
        if kinds[i] != "group":
            continue
        label = labels[i]
        placeholder = rw.GetAtomWithIdx(i)
        nbr_bonds = list(placeholder.GetBonds())
        nbrs = [b.GetOtherAtomIdx(i) for b in nbr_bonds]
        orders = [int(round(b.GetBondTypeAsDouble())) or 1 for b in nbr_bonds]
        ab = abbr.lookup(label)

        frag: Chem.Mol | None = None
        attach_in_frag = 0
        end_in_frag: int | None = None
        attach_order: int | None = None

        if ab is not None and len(nbrs) <= 1:
            frag = _fragment_with_coords(ab.smiles)
            dummy = 0
            dbond = frag.GetAtomWithIdx(dummy).GetBonds()[0]
            attach_in_frag = dbond.GetOtherAtomIdx(dummy)
            attach_order = int(round(dbond.GetBondTypeAsDouble()))
            frag_dummy = dummy
        else:
            frag_dummy = None
            smi_c = None
            if len(nbrs) == 1:
                from .condensed import parse_label

                smi_c = parse_label(label, neighbour_on_right=pos[nbrs[0]][0] > pos[i][0])
            if smi_c is not None:
                frag = _fragment_with_coords(smi_c)
                if frag is not None:
                    frag_dummy = 0
                    dbond = frag.GetAtomWithIdx(0).GetBonds()[0]
                    attach_in_frag = dbond.GetOtherAtomIdx(0)
                    attach_order = int(round(dbond.GetBondTypeAsDouble()))
            elif len(nbrs) == 1:
                direction = 1 if pos[nbrs[0]][0] <= pos[i][0] else -1
                smi = _condensed_to_smiles(label, orders[0], None, direction)
                if smi is None:
                    smi = _condensed_to_smiles(label, orders[0], None, -direction)
                if smi:
                    frag = _fragment_with_coords(smi)
                    attach_in_frag = 0
            elif len(nbrs) == 2:
                # left neighbour binds the first atom, right neighbour the last
                order_idx = sorted(range(2), key=lambda k: pos[nbrs[k]][0])
                nbrs = [nbrs[k] for k in order_idx]
                orders = [orders[k] for k in order_idx]
                smi = _condensed_to_smiles(label, orders[0], orders[1], 1)
                if smi:
                    marker = {1: "", 2: "=", 3: "#"}.get(orders[1], "")
                    frag = _fragment_with_coords(smi + marker + "[Xe]")
                    if frag is not None:
                        xe = [a.GetIdx() for a in frag.GetAtoms() if a.GetSymbol() == "Xe"][0]
                        end_in_frag = frag.GetAtomWithIdx(xe).GetNeighbors()[0].GetIdx()
                        frag_dummy = xe
                        attach_in_frag = 0
            elif len(nbrs) == 0:
                smi = _condensed_to_smiles(label, 0, None, 1)
                if smi:
                    frag = _fragment_with_coords(smi)

        if frag is None and len(nbrs) <= 1:
            # misread label: snap to the closest known abbreviation
            fz = abbr.lookup_fuzzy(label)
            if fz is not None:
                ab, spelled, _ = fz
                warnings.append(f"Nhãn đọc được \"{label}\" được hiểu là \"{spelled}\" — hãy kiểm tra")
                label = labels[i] = spelled
                frag = _fragment_with_coords(ab.smiles)
                frag_dummy = 0
                dbond = frag.GetAtomWithIdx(0).GetBonds()[0]
                attach_in_frag = dbond.GetOtherAtomIdx(0)
                attach_order = int(round(dbond.GetBondTypeAsDouble()))

        if frag is None:
            kinds[i] = "unknown"
            warnings.append(f"Không hiểu nhãn \"{label}\" — giữ nguyên dạng nhóm R/nhãn")
            continue

        # explicit hydrogens from condensed formulas are dropped (implicit later)
        keep = [
            a.GetIdx() for a in frag.GetAtoms()
            if a.GetIdx() != frag_dummy and not (a.GetAtomicNum() == 1 and a.GetIsotope() == 0)
        ]
        fcoords = np.array([
            [frag.GetConformer().GetAtomPosition(k).x, frag.GetConformer().GetAtomPosition(k).y]
            for k in range(frag.GetNumAtoms())
        ])
        # orient fragment: attachment atom at label position, pointing away from neighbour
        if nbrs:
            nb_pos = pos[nbrs[0]]
            if frag_dummy is not None and end_in_frag is None:
                fcoords = _rotate_place(fcoords, attach_in_frag, frag_dummy, pos[i], nb_pos)
            else:
                # point the fragment's centroid away from the neighbour
                centroid = np.mean(fcoords[keep], axis=0) if keep else fcoords[attach_in_frag]
                fake = 2 * fcoords[attach_in_frag] - centroid
                if np.linalg.norm(fake - fcoords[attach_in_frag]) < 1e-6:
                    fake = fcoords[attach_in_frag] + np.array([1.0, 0.0])
                ext = np.vstack([fcoords, fake])
                fcoords = _rotate_place(ext, attach_in_frag, len(fcoords), pos[i], nb_pos)[:-1]
        else:
            fcoords = fcoords - fcoords[attach_in_frag] + pos[i]

        index_map: dict[int, int] = {}
        for k in keep:
            fa = frag.GetAtomWithIdx(k)
            na = Chem.Atom(fa.GetAtomicNum())
            if fa.GetAtomicNum() == 0:  # R inside a label such as CO2R
                na.SetProp("dummyLabel", "R")
                na.SetProp("molFileAlias", "R")
            na.SetFormalCharge(fa.GetFormalCharge())
            na.SetIsotope(fa.GetIsotope())
            na.SetIsAromatic(fa.GetIsAromatic())
            na.SetNumExplicitHs(fa.GetNumExplicitHs())
            na.SetNoImplicit(fa.GetNoImplicit())
            new_idx = rw.AddAtom(na)
            index_map[k] = new_idx
            positions[new_idx] = fcoords[k]
        for b in frag.GetBonds():
            a1, a2 = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
            if a1 in index_map and a2 in index_map:
                rw.AddBond(index_map[a1], index_map[a2], b.GetBondType())
                if b.GetIsAromatic():
                    rw.GetBondBetweenAtoms(index_map[a1], index_map[a2]).SetIsAromatic(True)

        start_atom = index_map[attach_in_frag]
        for k, nb in enumerate(nbrs):
            target = start_atom if k == 0 or end_in_frag is None else index_map[end_in_frag]
            order = orders[k]
            if k == 0 and attach_order is not None:
                if attach_order != order:
                    warnings.append(
                        f"Nhãn \"{label}\": bậc liên kết vẽ ({order}) khác với nhóm chuẩn ({attach_order}) — dùng nhóm chuẩn"
                    )
                order = attach_order
            bt = {1: Chem.BondType.SINGLE, 2: Chem.BondType.DOUBLE, 3: Chem.BondType.TRIPLE}.get(
                order, Chem.BondType.SINGLE
            )
            rw.AddBond(nb, target, bt)
        to_remove.append(i)
        replaced[i] = start_atom
        groups.append(
            AbbrevGroup(
                label=label,
                atoms=list(index_map.values()),
                attach_atom=start_atom,
                neighbor=nbrs[0] if len(nbrs) == 1 else None,
                position=(float(pos[i][0]), float(pos[i][1])),
            )
        )

    # unknown labels stay as dummy atoms with their label
    for i in range(n):
        if kinds[i] == "unknown":
            a = rw.GetAtomWithIdx(i)
            a.SetProp("dummyLabel", labels[i])
            a.SetProp("molFileAlias", labels[i])

    # remove placeholders (highest index first) and remap group indices
    remap = list(range(rw.GetNumAtoms()))
    for idx in sorted(to_remove, reverse=True):
        rw.RemoveAtom(idx)
    removed = sorted(to_remove)
    for old in range(len(remap)):
        if old in to_remove:
            remap[old] = -1
        else:
            remap[old] = old - sum(1 for r in removed if r < old)
    for g in groups:
        g.atoms = [remap[a] for a in g.atoms]
        g.attach_atom = remap[g.attach_atom]
        g.neighbor = remap[g.neighbor] if g.neighbor is not None else None
    # a wedge drawn to a label (MeO, Ph, CO2Me ...) now ends on the label's attachment atom
    wedge_candidates = [
        (remap[replaced.get(i, i)], remap[replaced.get(j, j)], c) for i, j, c in wedge_candidates
    ]
    wedge_candidates = [(i, j, c) for i, j, c in wedge_candidates if i >= 0 and j >= 0]

    conf = Chem.Conformer(rw.GetNumAtoms())
    conf.Set3D(False)
    for old, new in enumerate(remap):
        if new >= 0:
            x, y = positions[old]
            conf.SetAtomPosition(new, Point3D(float(x), float(y), 0.0))
    rw.RemoveAllConformers()
    rw.AddConformer(conf, assignId=True)

    mol = rw.GetMol()
    mol, fixes = _fix_gem_diols(mol)
    warnings.extend(fixes)
    mol, sanitize_errors = _sanitize(mol)
    errors.extend(sanitize_errors)
    if mol.HasProp("_oniumFixed"):
        mol.ClearProp("_oniumFixed")
        warnings.append("Đã gán điện tích + cho nguyên tử hóa trị vượt mức (ion -onium, dấu ⊕ vẽ rời) — hãy kiểm tra")
    if not sanitize_errors:
        try:
            mol = _assign_stereo(mol, wedge_candidates)
        except Exception as exc:  # stereo is best effort, never lose the structure
            warnings.append(f"Không xác định được lập thể: {exc}")
    for a in mol.GetAtoms():
        if a.HasProp("_drawnH"):
            a.ClearProp("_drawnH")
    if not errors:
        try:
            mol, new_groups = _uncramp(mol, groups)
            groups += new_groups
        except Exception:  # layout repair is cosmetic; never lose the structure
            pass
    return BuiltMolecule(
        mol=mol, groups=groups, warnings=warnings, errors=errors, bond_px=px_bond,
        unknown_labels=sum(1 for k in kinds if k == "unknown"),
        fuzzy_labels=sum(1 for w in warnings if w.startswith("Nhãn đọc được")),
    )


def _uncramp(mol: Chem.Mol, groups: list[AbbrevGroup]) -> tuple[Chem.Mol, list[AbbrevGroup]]:
    """In small images MolScribe sometimes expands a label such as 'Ph' into
    ring atoms squeezed inside the label's few pixels. Re-depict such cramped
    atoms and, when they form a known substituent, show it as that label again."""
    conf = mol.GetConformer()
    pos = lambda i: np.array([conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y])  # noqa: E731
    in_group = {a for g in groups for a in g.atoms}
    n = mol.GetNumAtoms()
    lengths = [np.linalg.norm(pos(b.GetBeginAtomIdx()) - pos(b.GetEndAtomIdx())) for b in mol.GetBonds()]
    if not lengths or n < 4:
        return mol, []
    med = float(np.median(lengths))

    def side_of(bond) -> set[int]:
        """Atoms on the end-atom side of an acyclic bond."""
        start, block = bond.GetEndAtomIdx(), bond.GetBeginAtomIdx()
        seen, stack = {start}, [start]
        while stack:
            u = stack.pop()
            for nb in mol.GetAtomWithIdx(u).GetNeighbors():
                v = nb.GetIdx()
                if v != block and v not in seen:
                    seen.add(v)
                    stack.append(v)
        return seen

    def distorted(atoms: set[int]) -> bool:
        ring_lens = [
            np.linalg.norm(pos(bd.GetBeginAtomIdx()) - pos(bd.GetEndAtomIdx()))
            for bd in mol.GetBonds()
            if bd.IsInRing() and bd.GetBeginAtomIdx() in atoms and bd.GetEndAtomIdx() in atoms
        ]
        if ring_lens and max(ring_lens) / max(min(ring_lens), 1e-6) > 1.3:
            return True  # a drawn ring is regular; a squashed one was expanded from a label
        for bd in mol.GetBonds():
            i, j = bd.GetBeginAtomIdx(), bd.GetEndAtomIdx()
            if i in atoms and j in atoms:
                ln = np.linalg.norm(pos(i) - pos(j))
                if ln < 0.6 * med or ln > 1.6 * med:
                    return True
        lst = sorted(atoms)
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                if mol.GetBondBetweenAtoms(lst[x], lst[y]) is None and \
                        np.linalg.norm(pos(lst[x]) - pos(lst[y])) < 0.45 * med:
                    return True
        return False

    # candidate substituents: the smaller side of an acyclic single bond that
    # contains a ring or ≥3 atoms (Ph, CO2Me, Bn ...), smallest first
    cands: list[tuple[set[int], int, int]] = []
    for bd in mol.GetBonds():
        if bd.IsInRing() or bd.GetBondType() != Chem.BondType.SINGLE:
            continue
        for flip in (False, True):
            i, j = bd.GetBeginAtomIdx(), bd.GetEndAtomIdx()
            if flip:
                i, j = j, i
            side = side_of(bd) if not flip else (set(range(n)) - side_of(bd))
            attach = j if j in side else i
            outside = i if attach == j else j
            if len(side) < 3 or len(side) > 14 or len(side) >= n - 1 or side & in_group:
                continue
            cands.append((side, attach, outside))

    def known(c) -> bool:  # side is a recognisable group such as Ph / CO2Me
        side, attach, outside = c
        rw = Chem.RWMol(mol)
        keep = side | {outside}
        for k in sorted(set(range(n)) - keep, reverse=True):
            rw.RemoveAtom(k)
        idx = sorted(keep).index(outside)
        rw.GetAtomWithIdx(idx).SetAtomicNum(0)
        try:
            return abbr.label_for_fragment(Chem.MolToSmiles(rw, isomericSmiles=False)) is not None
        except Exception:
            return False

    cands.sort(key=lambda c: (not known(c), len(c[0])))
    comps: list[set[int]] = []
    done: set[int] = set()
    bounds_map: dict[int, tuple[int, int]] = {}
    for side, attach, outside in cands:
        if side & done or not distorted(side | {outside}):
            continue
        comps.append(side)
        bounds_map[id(side)] = (attach, outside)
        done |= side
    if not comps:
        return mol, []

    mol = Chem.Mol(mol)
    conf = mol.GetConformer()
    new_groups: list[AbbrevGroup] = []
    fixed_any = False
    for comp in comps:
        attach, outside = bounds_map[id(comp)]
        # substituent alone, with the outside atom as the attachment dummy
        keep = sorted(comp | {outside})
        sub = Chem.RWMol(Chem.PathToSubmol(mol, [
            b.GetIdx() for b in mol.GetBonds() if b.GetBeginAtomIdx() in keep and b.GetEndAtomIdx() in keep
        ], atomMap=(amap := {})))
        inv = {v: k for k, v in amap.items()}  # sub idx -> mol idx
        sub_out = amap[outside]
        sub.GetAtomWithIdx(sub_out).SetAtomicNum(0)
        sub.GetAtomWithIdx(sub_out).SetFormalCharge(0)
        sub.GetAtomWithIdx(sub_out).SetNoImplicit(True)
        sub.GetAtomWithIdx(sub_out).SetNumExplicitHs(0)
        smi = Chem.MolToSmiles(sub, isomericSmiles=False)
        label = abbr.label_for_fragment(smi)
        frag = _fragment_with_coords(smi)
        if frag is None:
            continue
        # map fragment atoms back via substructure match
        match = frag.GetSubstructMatch(sub, useChirality=False)
        if not match:
            continue
        fc = np.array([[frag.GetConformer().GetAtomPosition(k).x, frag.GetConformer().GetAtomPosition(k).y]
                       for k in range(frag.GetNumAtoms())])
        centre = np.mean([pos(a) for a in comp], axis=0)
        placed = _rotate_place(fc, match[amap[attach]], match[sub_out], centre, pos(outside))
        for sub_idx, frag_idx in enumerate(match):
            orig = inv[sub_idx]
            if orig in comp:
                conf.SetAtomPosition(orig, Point3D(float(placed[frag_idx][0]), float(placed[frag_idx][1]), 0.0))
        fixed_any = True
        if label:
            new_groups.append(AbbrevGroup(label, sorted(comp), attach, outside, (float(centre[0]), float(centre[1]))))
    if not fixed_any:
        return mol, []
    return mol, new_groups


def _fix_gem_diols(mol: Chem.Mol) -> tuple[Chem.Mol, list[str]]:
    """A carbon carrying two terminal OH and one carbon neighbour is almost
    always a CO2H/HO2C label that was split into atoms; restore the C=O."""
    rw = Chem.RWMol(mol)
    fixed = 0
    for a in rw.GetAtoms():
        if a.GetSymbol() != "C" or a.GetFormalCharge() or a.GetIsAromatic():
            continue
        bonds = list(a.GetBonds())
        oh = [
            b for b in bonds
            if b.GetBondType() == Chem.BondType.SINGLE
            and b.GetOtherAtom(a).GetSymbol() == "O"
            and b.GetOtherAtom(a).GetDegree() == 1
            and not b.GetOtherAtom(a).GetFormalCharge()
        ]
        others = [b for b in bonds if b not in oh]
        if len(oh) == 2 and len(others) == 1 and others[0].GetBondType() == Chem.BondType.SINGLE \
                and others[0].GetOtherAtom(a).GetSymbol() == "C":
            oh[0].SetBondType(Chem.BondType.DOUBLE)
            fixed += 1
    if not fixed:
        return mol, []
    return rw.GetMol(), ["Đã sửa C(OH)₂ thành COOH (nhãn HO₂C bị đọc tách) — hãy kiểm tra"]


def _drop_stray_atoms(symbols, coords, edges):
    """Remove tiny disconnected pieces made only of bare element symbols (a
    stray 'N' or ',' from neighbouring text caught in the crop)."""
    n = len(symbols)
    if n < 6:
        return symbols, coords, edges, []
    seen = [-1] * n
    comps: list[list[int]] = []
    for s0 in range(n):
        if seen[s0] >= 0:
            continue
        stack, comp = [s0], []
        seen[s0] = len(comps)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in range(n):
                if edges[u][v] and seen[v] < 0:
                    seen[v] = len(comps)
                    stack.append(v)
        comps.append(comp)
    if len(comps) == 1 or max(len(c) for c in comps) < 5:
        return symbols, coords, edges, []
    drop: list[int] = []
    for comp in comps:
        if len(comp) > 2:
            continue
        labels = [_strip_brackets(symbols[i]) for i in comp]
        if len(comp) == 1 and labels[0] in ("Cl", "Br", "I", "F"):
            continue  # a lone halide is a counter-ion, not stray text
        if all(re.fullmatch(r"[A-Z][a-z]?|[a-z]|[^A-Za-z0-9]+", l) and "+" not in l and "-" not in l for l in labels):
            drop += comp
    if not drop:
        return symbols, coords, edges, []
    keep = [i for i in range(n) if i not in set(drop)]
    return (
        [symbols[i] for i in keep],
        [coords[i] for i in keep],
        [[edges[i][j] for j in keep] for i in keep],
        [_strip_brackets(symbols[i]) for i in drop],
    )


# --------------------------------------------------------------------------- sanitize / stereo


def _assign_onium_charges(rw: Chem.RWMol) -> bool:
    """Charges drawn as a separate ⊕/⊖ are often missed: a neutral N/P with four
    bonds or O/S with three is an onium ion; a lone halide balances it."""
    changed = False
    cations = 0
    for a in rw.GetAtoms():
        if a.GetFormalCharge() or a.GetNumRadicalElectrons():
            continue
        valence = sum(b.GetBondTypeAsDouble() for b in a.GetBonds()) + a.GetNumExplicitHs()
        sym = a.GetSymbol()
        if (sym in ("N", "P", "As") and round(valence) == 4) or (sym in ("O", "S") and round(valence) == 3):
            a.SetFormalCharge(1)
            a.SetNoImplicit(True)
            cations += 1
            changed = True
    for a in rw.GetAtoms():
        if cations and a.GetSymbol() in ("Cl", "Br", "I", "F") and a.GetDegree() == 0 and not a.GetFormalCharge():
            a.SetFormalCharge(-1)
            cations -= 1
            changed = True
    return changed


def _sanitize(mol: Chem.Mol) -> tuple[Chem.Mol, list[str]]:
    rw = Chem.RWMol(mol)
    rw.UpdatePropertyCache(strict=False)
    if any(p.GetType() == "AtomValenceException" for p in Chem.DetectChemistryProblems(rw)):
        trial = Chem.RWMol(rw)
        if _assign_onium_charges(trial) and not any(
            p.GetType() == "AtomValenceException" for p in Chem.DetectChemistryProblems(trial)
        ):
            trial.SetProp("_oniumFixed", "1")
            rw = trial
    # drawn H counts matter for aromatic heteroatoms (pyrrole NH)
    for a in rw.GetAtoms():
        if a.HasProp("_drawnH") and a.GetIsAromatic():
            a.SetNumExplicitHs(a.GetIntProp("_drawnH"))
    problems = Chem.DetectChemistryProblems(rw)
    if not problems:
        res = Chem.SanitizeMol(rw, catchErrors=True)
        if res == Chem.SanitizeFlags.SANITIZE_NONE:
            return rw.GetMol(), []
    # try fixing aromatic N without H (kekulization failures)
    if any(p.GetType() == "KekulizeException" for p in problems):
        cand = [
            a.GetIdx() for a in rw.GetAtoms()
            if a.GetIsAromatic() and a.GetSymbol() == "N" and a.GetTotalNumHs() == 0 and a.GetDegree() == 2
        ]
        for idx in cand:
            trial = Chem.RWMol(rw)
            trial.GetAtomWithIdx(idx).SetNumExplicitHs(1)
            if not Chem.DetectChemistryProblems(trial):
                Chem.SanitizeMol(trial)
                return trial.GetMol(), []
    msgs = []
    for p in problems:
        msgs.append(_problem_message(p))
    if not msgs:
        msgs.append("Cấu trúc không hợp lệ về mặt hóa học")
    out = rw.GetMol()
    out.UpdatePropertyCache(strict=False)
    try:
        Chem.SanitizeMol(
            out,
            Chem.SanitizeFlags.SANITIZE_ALL
            ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES
            ^ Chem.SanitizeFlags.SANITIZE_KEKULIZE,
            catchErrors=True,
        )
    except Exception:
        pass
    return out, msgs


def _problem_message(p) -> str:
    t = p.GetType()
    if t == "AtomValenceException":
        a = p.GetAtomIdx()
        return f"Sai hóa trị tại nguyên tử #{a + 1}"
    if t == "KekulizeException":
        return "Vòng thơm không hợp lệ (không Kekulé hóa được)"
    return p.Message()


def _assign_stereo(mol: Chem.Mol, wedge_candidates: list[tuple[int, int, int]]) -> Chem.Mol:
    """E/Z from 2D coordinates, R/S from wedge/hash bonds."""
    conf = mol.GetConformer()
    # potential stereocentres
    try:
        centers = {
            si.centeredOn
            for si in Chem.FindPotentialStereo(mol)
            if si.type == Chem.StereoType.Atom_Tetrahedral
        }
    except Exception:
        centers = {
            idx for idx, _ in Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False)
        }

    for b in mol.GetBonds():
        if b.GetBondType() == Chem.BondType.SINGLE:
            b.SetBondDir(Chem.BondDir.NONE)

    # MolScribe: edges[i][j]==5 means "solid wedge narrow at i" or equivalently
    # "hashed wedge narrow at j"; 6 is the reverse. Pick the end that is a stereocentre.
    rw = Chem.RWMol(mol)
    for i, j, code in wedge_candidates:
        if i in centers:
            begin, end, direction = i, j, (Chem.BondDir.BEGINWEDGE if code == 5 else Chem.BondDir.BEGINDASH)
        elif j in centers:
            begin, end, direction = j, i, (Chem.BondDir.BEGINDASH if code == 5 else Chem.BondDir.BEGINWEDGE)
        else:
            continue
        bond = rw.GetBondBetweenAtoms(begin, end)
        if bond.GetBeginAtomIdx() != begin:
            rw.RemoveBond(begin, end)
            rw.AddBond(begin, end, Chem.BondType.SINGLE)
            bond = rw.GetBondBetweenAtoms(begin, end)
        bond.SetBondDir(direction)
    m2 = rw.GetMol()
    Chem.SanitizeMol(m2)
    if m2.GetNumConformers() == 0:
        m2.AddConformer(conf, assignId=True)
    Chem.AssignChiralTypesFromBondDirs(m2)
    # clear wedge dirs before double-bond perception (they conflict with ENDUP/DOWN)
    for b in m2.GetBonds():
        if b.GetBondDir() in (Chem.BondDir.BEGINWEDGE, Chem.BondDir.BEGINDASH):
            b.SetBondDir(Chem.BondDir.NONE)
    Chem.DetectBondStereochemistry(m2)
    Chem.AssignStereochemistry(m2, cleanIt=True, force=True)
    return m2
