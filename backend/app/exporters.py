"""Document -> files (CDXML, MOL, SDF, RXN, SMILES) and 'open in ChemDraw'."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdChemReactions

from .chem import io as chem_io
from .chem.cdxml import document_to_cdxml
from .chem.structure import BuiltMolecule
from .schemas import Document, Molecule


def built_map(doc: Document) -> dict[str, BuiltMolecule]:
    out: dict[str, BuiltMolecule] = {}
    for m in doc.molecules:
        if not m.molfile:
            continue
        absolute = bool(m.bond_px) and m.source in ("image", "region")
        try:
            out[m.id] = chem_io.from_molfile(m.molfile, normalise=not absolute)
        except ValueError:
            continue
    return out


def _plain_molfile(b: BuiltMolecule) -> str:
    return chem_io.to_molfile(BuiltMolecule(mol=b.mol))


def export(doc: Document, fmt: str, molecule_id: str | None = None,
           reaction_id: str | None = None, contract_labels: bool = True) -> tuple[bytes, str, str]:
    """Return (content, media_type, filename)."""
    built = built_map(doc)
    stem = _stem(doc, molecule_id)
    if fmt == "cdxml":
        xml = document_to_cdxml(doc, built, contract_labels=contract_labels, only_molecule=molecule_id)
        return xml.encode("utf-8"), "chemical/x-cdxml", f"{stem}.cdxml"
    if fmt == "mol":
        mid = molecule_id or (doc.molecules[0].id if doc.molecules else None)
        if mid is None or mid not in built:
            raise ValueError("Không có phân tử để xuất")
        b = built[mid]
        text = chem_io.to_molfile(b) if contract_labels else _plain_molfile(b)
        return text.encode(), "chemical/x-mdl-molfile", f"{stem}.mol"
    if fmt == "sdf":
        return _sdf(doc, built).encode(), "chemical/x-mdl-sdfile", f"{stem}.sdf"
    if fmt == "rxn":
        rx = next((r for r in doc.reactions if r.id == reaction_id), None) if reaction_id else (
            doc.reactions[0] if doc.reactions else None)
        if rx is None:
            raise ValueError("Ảnh không có phản ứng để xuất RXN")
        rxn = rdChemReactions.ChemicalReaction()
        for mid in rx.reactants:
            if mid in built:
                rxn.AddReactantTemplate(built[mid].mol)
        for mid in rx.products:
            if mid in built:
                rxn.AddProductTemplate(built[mid].mol)
        for mid in rx.agents:
            if mid in built:
                rxn.AddAgentTemplate(built[mid].mol)
        return rdChemReactions.ReactionToRxnBlock(rxn).encode(), "chemical/x-mdl-rxnfile", f"{stem}-{rx.id}.rxn"
    if fmt == "smiles":
        lines = []
        if molecule_id:
            lines = [m.smiles for m in doc.molecules if m.id == molecule_id]
        else:
            lines += [r.reaction_smiles for r in doc.reactions]
            in_rx = {i for r in doc.reactions for i in r.reactants + r.products + r.agents}
            lines += [m.smiles for m in doc.molecules if m.id not in in_rx]
        return ("\n".join(lines) + "\n").encode(), "text/plain", f"{stem}.smi"
    raise ValueError(f"Định dạng không hỗ trợ: {fmt}")


def _sdf(doc: Document, built: dict[str, BuiltMolecule]) -> str:
    role: dict[str, str] = {}
    for r in doc.reactions:
        for i in r.reactants:
            role.setdefault(i, f"reactant ({r.id})")
        for i in r.products:
            role.setdefault(i, f"product ({r.id})")
        for i in r.agents:
            role.setdefault(i, f"reagent ({r.id})")
    parts = []
    for m in doc.molecules:
        if m.id not in built:
            continue
        mb = chem_io.to_molfile(built[m.id])
        mb = m.id + mb[mb.index("\n"):] if "\n" in mb else mb
        props = {
            "ID": m.id, "SMILES": m.smiles, "FORMULA": m.formula, "MW": f"{m.mol_weight:.3f}",
            "INCHIKEY": m.inchikey, "ROLE": role.get(m.id, ""),
        }
        body = "".join(f">  <{k}>\n{v}\n\n" for k, v in props.items() if v)
        parts.append(mb.rstrip("\n") + "\n" + body + "$$$$\n")
    return "".join(parts)


def _stem(doc: Document, molecule_id: str | None) -> str:
    base = f"chem-{doc.id[:8]}" if doc.id else "chem"
    if molecule_id:
        base += f"-{molecule_id}"
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


# ----------------------------------------------------------------------------- ChemDraw


@lru_cache(maxsize=1)
def find_chemdraw() -> str | None:
    """Path of an installed ChemDraw .app (macOS), or None."""
    if sys.platform != "darwin":
        return None
    candidates: list[Path] = []
    for root in (Path("/Applications"), Path.home() / "Applications"):
        if root.exists():
            candidates += sorted(root.glob("ChemDraw*.app"), reverse=True)
            candidates += sorted(root.glob("*/ChemDraw*.app"), reverse=True)
    if candidates:
        return str(candidates[0])
    if shutil.which("mdfind"):
        try:
            res = subprocess.run(
                ["mdfind", "kMDItemContentType == 'com.apple.application-bundle' && kMDItemFSName == 'ChemDraw*'"],
                capture_output=True, text=True, timeout=5,
            )
            for line in res.stdout.splitlines():
                if line.endswith(".app"):
                    return line
        except Exception:
            pass
    return None


def save_and_open(content: bytes, filename: str, export_dir: Path) -> dict:
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = export_dir / f"{Path(filename).stem}-{stamp}{Path(filename).suffix}"
    path.write_bytes(content)
    app = find_chemdraw()
    opened_with = None
    if sys.platform == "darwin":
        cmd = ["open", "-a", app, str(path)] if app else ["open", str(path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            opened_with = Path(app).stem if app else "ứng dụng mặc định"
    return {"path": str(path), "chemdraw": app, "opened_with": opened_with}
