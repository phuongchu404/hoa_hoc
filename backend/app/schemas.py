from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BBox = list[float]  # [x0, y0, x1, y1] in image pixels
Point = list[float]  # [x, y] in image pixels


class Molecule(BaseModel):
    id: str
    bbox: BBox | None = None
    molfile: str
    smiles: str = ""
    formula: str = ""
    mol_weight: float = 0.0
    exact_mass: float = 0.0
    inchi: str = ""
    inchikey: str = ""
    svg: str = ""
    confidence: float | None = None
    status: Literal["ok", "warning", "error"] = "ok"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    source: Literal["image", "region", "edited", "smiles"] = "image"
    alternatives: list[str] = Field(default_factory=list)
    # pixels per bond in the source image; when set, molfile coordinates are
    # absolute image positions (x_px = x * bond_px / 1.5, y_px = -y * bond_px / 1.5)
    bond_px: float | None = None


class TextBlock(BaseModel):
    id: str
    bbox: BBox
    text: str


class Arrow(BaseModel):
    id: str
    tail: Point
    head: Point


class Reaction(BaseModel):
    id: str
    reactants: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)  # reagents/catalysts drawn as structures at the arrow
    conditions_above: list[str] = Field(default_factory=list)
    conditions_below: list[str] = Field(default_factory=list)
    arrow: str | None = None
    reaction_smiles: str = ""


class Document(BaseModel):
    id: str = ""
    image_width: int = 0
    image_height: int = 0
    molecules: list[Molecule] = Field(default_factory=list)
    texts: list[TextBlock] = Field(default_factory=list)
    arrows: list[Arrow] = Field(default_factory=list)
    reactions: list[Reaction] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    notices: list[str] = Field(default_factory=list)  # document-level hints for the user


class MolfileIn(BaseModel):
    molfile: str
    id: str | None = None
    bbox: BBox | None = None


class SmilesIn(BaseModel):
    smiles: str
    id: str | None = None
    bbox: BBox | None = None


ExportFormat = Literal["cdxml", "rxn", "sdf", "smiles", "mol"]


class ExportIn(BaseModel):
    document: Document
    format: ExportFormat = "cdxml"
    molecule_id: str | None = None  # export a single molecule
    reaction_id: str | None = None  # RXN export: which reaction (default: first)
    contract_labels: bool = True


class OpenInChemDrawIn(BaseModel):
    document: Document
    molecule_id: str | None = None
    contract_labels: bool = True
