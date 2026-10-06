"""Molecule serialisation and properties.

The molfile (V2000, SUP S-groups for abbreviations) is the canonical exchange
format between backend and frontend: the editor (Ketcher) reads/writes it and
every other output (SMILES, SVG, CDXML, RXN) is derived from it.
"""
from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import Descriptors, rdAbbreviations, rdDepictor, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

from .structure import AbbrevGroup, BOND_LENGTH, BuiltMolecule


@dataclass
class MolInfo:
    smiles: str
    formula: str
    mol_weight: float
    exact_mass: float
    inchi: str
    inchikey: str
    num_atoms: int


# ----------------------------------------------------------------------------- molfile


def to_molfile(built: BuiltMolecule) -> str:
    mol = Chem.Mol(built.mol)
    for g in built.groups:
        if not g.atoms:
            continue
        sg = Chem.CreateMolSubstanceGroup(mol, "SUP")
        sg.SetProp("LABEL", g.label)
        for a in g.atoms:
            sg.AddAtomWithIdx(a)
        if g.neighbor is not None:
            bond = mol.GetBondBetweenAtoms(g.attach_atom, g.neighbor)
            if bond is not None:
                sg.AddBondWithIdx(bond.GetIdx())
            sg.AddAttachPoint(g.attach_atom, g.neighbor, "Al")  # MDL 2-char id
    try:
        return Chem.MolToMolBlock(mol, kekulize=True)
    except Exception:
        return Chem.MolToMolBlock(mol, kekulize=False)


def from_molfile(molblock: str, normalise: bool = True) -> BuiltMolecule:
    """Parse a molfile (e.g. edited in Ketcher) back into a BuiltMolecule.
    normalise=False keeps coordinates untouched (absolute image positions)."""
    errors: list[str] = []
    mol = Chem.MolFromMolBlock(molblock, sanitize=True, removeHs=False, strictParsing=False)
    if mol is None:
        mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False, strictParsing=False)
        if mol is None:
            raise ValueError("Molfile không hợp lệ")
        mol.UpdatePropertyCache(strict=False)
        problems = Chem.DetectChemistryProblems(mol)
        errors = [p.Message() for p in problems] or ["Cấu trúc không hợp lệ"]
    if mol.GetNumConformers() == 0:
        rdDepictor.Compute2DCoords(mol)
    if normalise:
        _normalise_scale(mol)
    groups: list[AbbrevGroup] = []
    for sg in Chem.GetMolSubstanceGroups(mol):
        if sg.GetProp("TYPE") != "SUP":
            continue
        label = sg.GetProp("LABEL") if sg.HasProp("LABEL") else "?"
        atoms = list(sg.GetAtoms())
        attach, neighbor = None, None
        aps = sg.GetAttachPoints()
        if aps:
            attach = aps[0].aIdx
            neighbor = aps[0].lvIdx if aps[0].lvIdx >= 0 else None
        if attach is None:
            # derive from crossing bond
            inside = set(atoms)
            for b in mol.GetBonds():
                a1, a2 = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
                if (a1 in inside) != (a2 in inside):
                    attach, neighbor = (a1, a2) if a1 in inside else (a2, a1)
                    break
        if attach is None:
            attach = atoms[0] if atoms else 0
        if neighbor is None:
            inside = set(atoms)
            for nb in mol.GetAtomWithIdx(attach).GetNeighbors():
                if nb.GetIdx() not in inside:
                    neighbor = nb.GetIdx()
                    break
        p = mol.GetConformer().GetAtomPosition(attach)
        groups.append(AbbrevGroup(label, atoms, attach, neighbor, (p.x, p.y)))
    Chem.ClearMolSubstanceGroups(mol)
    return BuiltMolecule(mol=mol, groups=groups, errors=errors)


def from_smiles(smiles: str) -> BuiltMolecule:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("SMILES không hợp lệ")
    rdDepictor.Compute2DCoords(mol)
    return BuiltMolecule(mol=mol)


def _normalise_scale(mol: Chem.Mol) -> None:
    """Rescale coordinates so the median bond length is BOND_LENGTH."""
    if mol.GetNumBonds() == 0:
        return
    conf = mol.GetConformer()
    lengths = sorted(
        (conf.GetAtomPosition(b.GetBeginAtomIdx()) - conf.GetAtomPosition(b.GetEndAtomIdx())).Length()
        for b in mol.GetBonds()
    )
    med = lengths[len(lengths) // 2]
    if med < 1e-6 or abs(med - BOND_LENGTH) < 1e-3:
        return
    k = BOND_LENGTH / med
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (p.x * k, p.y * k, 0.0))


# ----------------------------------------------------------------------------- properties


def _no_h(mol: Chem.Mol) -> Chem.Mol:
    try:
        return Chem.RemoveHs(mol, sanitize=True)
    except Exception:
        return mol


def mol_info(built: BuiltMolecule) -> MolInfo:
    mol = built.mol
    try:
        smiles = Chem.MolToSmiles(_no_h(mol))
    except Exception:
        smiles = ""
    formula = mw = exact = None
    inchi = inchikey = ""
    try:
        formula = rdMolDescriptors.CalcMolFormula(mol)
        mw = Descriptors.MolWt(mol)
        exact = Descriptors.ExactMolWt(mol)
    except Exception:
        pass
    has_dummy = any(a.GetAtomicNum() == 0 for a in mol.GetAtoms())
    if built.ok and not has_dummy:
        try:
            inchi = Chem.MolToInchi(mol) or ""
            inchikey = Chem.InchiToInchiKey(inchi) if inchi else ""
        except Exception:
            pass
    return MolInfo(
        smiles=smiles,
        formula=formula or "",
        mol_weight=round(mw, 3) if mw else 0.0,
        exact_mass=round(exact, 4) if exact else 0.0,
        inchi=inchi,
        inchikey=inchikey or "",
        num_atoms=mol.GetNumHeavyAtoms(),
    )


# ----------------------------------------------------------------------------- drawing


def _contracted(built: BuiltMolecule) -> Chem.Mol:
    """Molecule with abbreviation groups collapsed into labelled atoms."""
    if not built.groups:
        return Chem.Mol(built.mol)
    mb = to_molfile(built)
    mol = Chem.MolFromMolBlock(mb, sanitize=False, removeHs=False)
    mol.UpdatePropertyCache(strict=False)
    try:
        return rdAbbreviations.CondenseAbbreviationSubstanceGroups(mol)
    except Exception:
        return Chem.Mol(built.mol)


def to_svg(built: BuiltMolecule, bond_px: int = 26) -> str:
    mol = _contracted(built)
    for a in mol.GetAtoms():
        if a.GetAtomicNum() == 0 and a.HasProp("dummyLabel") and not a.HasProp("atomLabel"):
            a.SetProp("atomLabel", a.GetProp("dummyLabel"))
    d = rdMolDraw2D.MolDraw2DSVG(-1, -1)  # flexicanvas: size follows the molecule
    opts = d.drawOptions()
    opts.clearBackground = False
    opts.padding = 0.08
    opts.bondLineWidth = 1.6
    opts.additionalAtomLabelPadding = 0.08
    opts.fixedBondLength = bond_px
    opts.baseFontSize = 0.75
    opts.minFontSize = 11
    try:
        rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=True, addChiralHs=False, wedgeBonds=True)
    except Exception:
        mol = rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=False, addChiralHs=False) or mol
    d.DrawMolecule(mol)
    d.FinishDrawing()
    return d.GetDrawingText()


def tidy_layout(built: BuiltMolecule) -> BuiltMolecule:
    """Recompute a clean 2D depiction (used on request, e.g. 'Chuẩn hóa bố cục')."""
    mol = Chem.Mol(built.mol)
    rdDepictor.Compute2DCoords(mol)
    for g in built.groups:
        p = mol.GetConformer().GetAtomPosition(g.attach_atom)
        g.position = (p.x, p.y)
    return BuiltMolecule(mol=mol, groups=built.groups, warnings=built.warnings, errors=built.errors)
