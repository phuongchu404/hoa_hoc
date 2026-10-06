"""Fast unit tests for the chemistry layer (no ML models needed)."""
from rdkit import Chem

from app.chem import abbreviations as abbr
from app.chem import io as chem_io
from app.chem.cdxml import attach_first_label, document_to_cdxml
from app.chem.structure import build_molecule
from app.engines.ocr import clean_text, looks_like_formula
from app.schemas import Document, Molecule


def canon(s: str) -> str:
    return Chem.CanonSmiles(s)


def chain(symbols, coords, bonds):
    n = len(symbols)
    edges = [[0] * n for _ in range(n)]
    for i, j, t in bonds:
        edges[i][j] = edges[j][i] = t
    return build_molecule(symbols, coords, edges)


# ----------------------------------------------------------------------------- abbreviations


def test_abbreviation_table_is_valid():
    for label in abbr.all_labels():
        ab = abbr.lookup(label)
        m = Chem.MolFromSmiles(ab.smiles)
        assert m is not None, label
        assert m.GetAtomWithIdx(0).GetAtomicNum() == 0, f"{label}: first atom must be the attachment *"


def test_lookup_aliases():
    assert abbr.lookup("EtO2C").label == "CO2Et"
    assert abbr.lookup("CO₂Me").label == "CO2Me"
    assert abbr.lookup("t-Bu").label == "tBu"
    assert abbr.lookup("Ac").label == "Ac"  # acetyl, not actinium


def test_attach_first_label():
    assert attach_first_label("EtO2C") == "CO2Et"
    assert attach_first_label("TBSO") == "OTBS"
    assert attach_first_label("MeO") == "OMe"
    assert attach_first_label("Me") == "Me"


# ----------------------------------------------------------------------------- graph -> molecule


def test_expands_label_on_left_with_e_alkene():
    # EtO2C-CH=CH-CH3 drawn as a trans zig-zag, label on the left
    b = chain(
        ["[EtO2C]", "C", "C", "C"],
        [(0, 0), (40, 20), (80, 0), (120, 20)],
        [(0, 1, 1), (1, 2, 2), (2, 3, 1)],
    )
    assert b.ok
    assert canon(Chem.MolToSmiles(b.mol)) == canon("CCOC(=O)/C=C/C")
    assert [g.label for g in b.groups] == ["EtO2C"]


def test_z_alkene_from_coordinates():
    b = chain(["C", "C", "C", "C"], [(0, 20), (30, 0), (70, 0), (100, 20)], [(0, 1, 1), (1, 2, 2), (2, 3, 1)])
    assert canon(Chem.MolToSmiles(b.mol)) == canon("C/C=C\\C")


def test_diazo_label_uses_double_bond():
    b = chain(["[N2]", "C", "C"], [(0, 0), (40, 0), (60, 30)], [(0, 1, 2), (1, 2, 1)])
    assert b.ok
    assert canon(Chem.MolToSmiles(b.mol)) == canon("CC=[N+]=[N-]")


def test_chiral_label_and_wedge():
    # (R/S) centre drawn with a wedge to the methyl: MolScribe writes [C@H]
    symbols = ["[C@H]", "C", "O", "C", "C"]
    coords = [(50, 50), (50, 10), (90, 70), (10, 70), (10, 110)]
    n = 5
    edges = [[0] * n for _ in range(n)]
    edges[0][1], edges[1][0] = 5, 6  # wedge, narrow end at atom 0
    edges[0][2] = edges[2][0] = 1
    edges[0][3] = edges[3][0] = 1
    edges[3][4] = edges[4][3] = 1
    b = build_molecule(symbols, coords, edges)
    assert b.ok
    # butan-2-ol has one stereocentre that must be assigned
    centers = Chem.FindMolChiralCenters(b.mol, useLegacyImplementation=False)
    assert len(centers) == 1 and centers[0][1] in ("R", "S")


def test_unknown_label_kept_as_rgroup():
    b = chain(["[R1]", "C", "C"], [(0, 0), (30, 0), (60, 0)], [(0, 1, 1), (1, 2, 1)])
    assert any(a.GetAtomicNum() == 0 for a in b.mol.GetAtoms())


def test_condensed_formula():
    b = chain(["C", "C", "[CH2OH]"], [(0, 0), (30, 0), (60, 0)], [(0, 1, 1), (1, 2, 1)])
    assert canon(Chem.MolToSmiles(b.mol)) == canon("CCCO")


# ----------------------------------------------------------------------------- I/O


def test_molfile_roundtrip_keeps_abbreviations():
    b = chain(["[Ph]", "C", "[CO2Me]"], [(0, 0), (40, 0), (80, 0)], [(0, 1, 1), (1, 2, 1)])
    mb = chem_io.to_molfile(b)
    assert "SUP" in mb and "CO2Me" in mb
    back = chem_io.from_molfile(mb)
    assert {g.label for g in back.groups} == {"Ph", "CO2Me"}
    assert canon(Chem.MolToSmiles(back.mol)) == canon("COC(=O)Cc1ccccc1")
    assert "<svg" in chem_io.to_svg(back)


def test_cdxml_is_readable_and_chemically_exact():
    b = chain(["[EtO2C]", "C", "C", "C"], [(0, 0), (40, 20), (80, 0), (120, 20)], [(0, 1, 1), (1, 2, 2), (2, 3, 1)])
    mol = Molecule(id="m1", molfile=chem_io.to_molfile(b), bond_px=b.bond_px, bbox=[0, 0, 120, 20])
    built = {"m1": chem_io.from_molfile(mol.molfile, normalise=False)}
    xml = document_to_cdxml(Document(molecules=[mol]), built)
    mols = Chem.MolsFromCDXML(xml)
    assert [canon(Chem.MolToSmiles(m)) for m in mols] == [canon("CCOC(=O)/C=C/C")]
    assert 'NodeType="Fragment"' in xml  # contracted as a ChemDraw nickname


# ----------------------------------------------------------------------------- OCR clean-up


def test_ocr_subscript_repair():
    assert clean_text("Rh½(OAc)4,") == "Rh2(OAc)4,"
    assert clean_text("COzEt") == "CO2Et"
    assert clean_text("CO,Me") == "CO2Me"
    assert clean_text("60 ºC to reflux") == "60 °C to reflux"
    assert clean_text("DBU, THF") == "DBU, THF"


def test_formula_detection():
    assert looks_like_formula("Rh2(OAc)4")
    assert looks_like_formula("CH2Cl2")
    assert not looks_like_formula("toluene")
    assert not looks_like_formula("60")


def test_fuzzy_labels_from_low_resolution():
    from app.chem.abbreviations import lookup_fuzzy

    assert lookup_fuzzy("boc")[0].label == "Boc"
    assert lookup_fuzzy("noc")[0].label == "Boc"
    assert lookup_fuzzy("BocHf")[1] == "BocHN"
    assert lookup_fuzzy("BocH")[1] == "BocHN"
    assert lookup_fuzzy("TMDPSO")[1] == "TBDPSO"
    assert lookup_fuzzy("Tocc") is None  # too far: stay unknown rather than guess


def test_misread_label_is_snapped_with_warning():
    b = chain(["[noc]", "N", "C"], [(0, 0), (30, 0), (60, 0)], [(0, 1, 1), (1, 2, 1)])
    assert canon(Chem.MolToSmiles(b.mol)) == canon("CNC(=O)OC(C)(C)C")
    assert b.fuzzy_labels == 1 and any("noc" in w for w in b.warnings)
    # a case-only difference is simply the same label
    b = chain(["[boc]", "N", "C"], [(0, 0), (30, 0), (60, 0)], [(0, 1, 1), (1, 2, 1)])
    assert canon(Chem.MolToSmiles(b.mol)) == canon("CNC(=O)OC(C)(C)C")


def test_rare_element_not_accepted_as_atom():
    from app.chem.structure import _parse_atom_label

    assert _parse_atom_label("Hf") is None and _parse_atom_label("Ar") is None
    assert _parse_atom_label("Pd") is not None


def test_gem_diol_restored_to_acid():
    b = chain(["C", "C", "O", "O"], [(0, 0), (30, 0), (45, -26), (45, 26)], [(0, 1, 1), (1, 2, 1), (1, 3, 1)])
    assert canon(Chem.MolToSmiles(b.mol)) == canon("CC(=O)O")


def test_stray_letters_dropped():
    syms = ["C", "C", "C", "C", "C", "C", "N"]
    coords = [(0, 0), (30, 0), (45, 26), (30, 52), (0, 52), (-15, 26), (200, 200)]
    n = len(syms)
    edges = [[0] * n for _ in range(n)]
    for i in range(6):
        j = (i + 1) % 6
        edges[i][j] = edges[j][i] = 1
    b = build_molecule(syms, coords, edges)
    assert canon(Chem.MolToSmiles(b.mol)) == canon("C1CCCCC1")


def test_reagent_ocr_repair():
    for raw, fixed in [("NaBHa", "NaBH4"), ("LIOH,", "LiOH,"), ("CICOOEt,", "ClCOOEt,"), ("Mel", "MeI"),
                       ("TICI,", "TiCl4,"), ("4. BocO, DMAP", "4. Boc2O, DMAP"), ("THF/H.O", "THF/H2O"), ("Pd(dppf)CI2,", "Pd(dppf)Cl2,")]:
        assert clean_text(raw) == fixed, raw


def test_condensed_labels():
    from app.chem.condensed import parse_label

    for label, rev, exp in [("COCO2CH3", False, "*C(=O)C(=O)OC"), ("CH2CO2CH3", False, "*CC(=O)OC"),
                            ("CO2CH2CCl3", False, "*C(=O)OCC(Cl)(Cl)Cl"), ("CO2R", False, "*C(=O)O[*]"),
                            ("H3CO2C", True, "*C(=O)OC"), ("CH2OCH3", False, "*COC")]:
        assert canon(parse_label(label, rev)) == canon(exp), label


def test_wedge_to_label_keeps_stereo():
    # CH(Me)(OH) with a wedge drawn to the "MeO" label
    symbols = ["C", "[MeO]", "C", "C", "C"]
    coords = [(50, 50), (50, 10), (90, 70), (10, 70), (10, 110)]
    n = 5
    edges = [[0] * n for _ in range(n)]
    edges[0][1], edges[1][0] = 5, 6
    edges[0][2] = edges[2][0] = 1
    edges[0][3] = edges[3][0] = 1
    edges[3][4] = edges[4][3] = 1
    b = build_molecule(symbols, coords, edges)
    assert "@" in Chem.MolToSmiles(b.mol)


def test_onium_charge_from_valence():
    # N with four bonds and a lone chloride -> ammonium chloride
    b = chain(["N", "C", "C", "C", "C", "Cl"], [(0, 0), (30, 0), (-30, 0), (0, 30), (0, -30), (200, 200)],
              [(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)])
    assert b.ok and canon(Chem.MolToSmiles(b.mol)) == canon("C[N+](C)(C)C.[Cl-]")
