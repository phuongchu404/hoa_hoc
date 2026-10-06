"""End-to-end tests with the real models on the reference image
(tests/fixtures/reaction_scheme.png). Run: pytest -m slow"""
from pathlib import Path

import pytest
from rdkit import Chem

FIXTURE = Path(__file__).parent / "fixtures" / "reaction_scheme.png"

EXPECTED = {
    "m1": "C=CCSC(C)C#C/C=C/C(=O)OCC",
    "m2": "C=CCc1cc(CC(=O)OCC)sc1C",
    "m3": "COC(=O)C(/C=C/c1ccccc1)=[N+]=[N-]",
    "m4": "Cc1cc(C)on1",
    "m5": "COC(=O)c1cc(-c2ccccc2)c(C(C)=O)c(C)n1",
}

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not FIXTURE.exists(), reason="test image not present (kept out of git)"),
]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:  # runs lifespan: loads models + warm-up
        yield c


@pytest.fixture(scope="module")
def doc(client):
    r = client.post("/api/recognize", files={"file": ("scheme.png", FIXTURE.read_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    h = client.get("/api/health").json()
    assert h["ready"] is True


def test_molecules_exact(doc):
    got = {m["id"]: m["smiles"] for m in doc["molecules"]}
    assert set(got) == set(EXPECTED)
    for k, smi in EXPECTED.items():
        assert Chem.CanonSmiles(got[k]) == Chem.CanonSmiles(smi), k
    assert all(m["status"] == "ok" for m in doc["molecules"])


def test_reactions_and_conditions(doc):
    texts = {t["id"]: t["text"] for t in doc["texts"]}
    r1, r2 = doc["reactions"]
    assert (r1["reactants"], r1["products"]) == (["m1"], ["m2"])
    assert (sorted(r2["reactants"]), r2["products"]) == (["m3", "m4"], ["m5"])
    assert [texts[i] for i in r1["conditions_above"]] == ["DBU, THF"]
    assert [texts[i] for i in r1["conditions_below"]] == ["rt"]
    assert [texts[i] for i in r2["conditions_above"]] == ["Rh2(OAc)4,\ntoluene,\n60 °C to reflux"]
    assert [texts[i] for i in r2["conditions_below"]] == ["then DDQ"]


def test_speed(client):
    # cache disabled by changing one pixel
    from io import BytesIO

    from PIL import Image

    img = Image.open(FIXTURE).convert("RGB")
    img.putpixel((0, 0), (250, 250, 250))
    buf = BytesIO()
    img.save(buf, format="PNG")
    r = client.post("/api/recognize", files={"file": ("x.png", buf.getvalue(), "image/png")})
    assert r.json()["timings"]["total"] < 5.0


def test_cdxml_export_roundtrip(client, doc):
    r = client.post("/api/export", json={"document": doc, "format": "cdxml"})
    assert r.status_code == 200
    xml = r.text
    mols = Chem.MolsFromCDXML(xml)
    assert sorted(Chem.MolToSmiles(m) for m in mols) == sorted(Chem.CanonSmiles(s) for s in EXPECTED.values())
    assert xml.count("<arrow ") == 2 and "<scheme" in xml
    assert ">Rh2(OAc)4</s>" in xml  # formula face → subscripts in ChemDraw


@pytest.mark.parametrize("fmt", ["sdf", "rxn", "smiles", "mol"])
def test_other_exports(client, doc, fmt):
    r = client.post("/api/export", json={"document": doc, "format": fmt})
    assert r.status_code == 200 and len(r.content) > 20


def test_edit_roundtrip(client, doc):
    m3 = next(m for m in doc["molecules"] if m["id"] == "m3")
    r = client.post("/api/molecule/from-molfile", json={"molfile": m3["molfile"], "id": "m3", "bbox": m3["bbox"]})
    assert r.status_code == 200
    assert Chem.CanonSmiles(r.json()["smiles"]) == Chem.CanonSmiles(EXPECTED["m3"])


def test_region(client):
    r = client.post(
        "/api/recognize/region",
        files={"file": ("scheme.png", FIXTURE.read_bytes(), "image/png")},
        data={"x0": 1127, "y0": 476, "x1": 1624, "y1": 760},
    )
    assert r.status_code == 200
    assert Chem.CanonSmiles(r.json()["smiles"]) == Chem.CanonSmiles(EXPECTED["m5"])


def test_bad_upload(client):
    r = client.post("/api/recognize", files={"file": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 415


# ----------------------------------------------------------------------------- low-resolution multistep scheme

MULTI = Path(__file__).parent / "fixtures" / "multistep_scheme.png"
MULTI_CONSTITUTION = {
    "m1": "NC(CO)c1ccccc1",
    "m2": "O=C(O)CC1CCCC1=O",
    "m3": "O=C1CC2CCCC23OCC(c2ccccc2)N13",
    "m4": "C=CCC12CCCC1CC(=O)N2C(CO)c1ccccc1",
    "m5": "C=CCC12CCCC1CC(=O)N2C(=O)OC(C)(C)C",
    "m6": "C=CCC12CCCC1C(C)C(=O)N2C(=O)OC(C)(C)C",
    "m7": "C=CCC1(NC(=O)OC(C)(C)C)CCCC1C(C)C(=O)O",
    "m8": "C=CCC1(NC(=O)OC(C)(C)C)CCCC1C(C)O[Si](c1ccccc1)(c1ccccc1)C(C)(C)C",
    "m9": "COC(=O)C=CCCCC1(NC(=O)OC(C)(C)C)CCCC1C(C)O[Si](c1ccccc1)(c1ccccc1)C(C)(C)C",
    "m10": "COC(=O)CC1CCCC2(CCCC2C(C)O[Si](c2ccccc2)(c2ccccc2)C(C)(C)C)N1",
}


def _flat(s):
    return Chem.MolToSmiles(Chem.MolFromSmiles(s), isomericSmiles=False)


@pytest.fixture(scope="module")
def multi(client):
    if not MULTI.exists():
        pytest.skip("multistep test image not present (kept out of git)")
    r = client.post("/api/recognize", files={"file": ("m.png", MULTI.read_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()


def test_multistep_constitutions(multi):
    got = {m["id"]: m["smiles"] for m in multi["molecules"]}
    assert set(got) == set(MULTI_CONSTITUTION)
    for k, smi in MULTI_CONSTITUTION.items():
        assert _flat(got[k]) == _flat(smi), k
    # Z-alkene of the Suzuki product is kept
    assert "/C=C\\" in got["m9"] or "\\C=C/" in got["m9"]
    assert multi["notices"], "low-resolution notice expected"


def test_multistep_reaction_chain_and_arrows(multi):
    chain = [(r["reactants"], r["products"]) for r in multi["reactions"]]
    assert chain[0] == (["m1", "m2"], ["m3"])
    assert [p for _, p in chain[1:]] == [[f"m{i}"] for i in range(4, 11)]
    arrows = {a["id"]: a for a in multi["arrows"]}
    # elbow arrows: step 5 points down, step 9 points left
    a4, a7 = arrows["a4"], arrows["a7"]
    assert a4["head"][1] - a4["tail"][1] > 30 and abs(a4["head"][0] - a4["tail"][0]) < 3
    assert a7["tail"][0] - a7["head"][0] > 60 and abs(a7["head"][1] - a7["tail"][1]) < 3


def test_multistep_conditions_ocr(multi):
    texts = " | ".join(t["text"] for t in multi["texts"])
    for frag in ["TiCl4", "LiHMDS", "LiOH", "NaBH4", "ClCOOEt", "Pd(dppf)Cl2", "AsPh3", "Boc2O", "MeI"]:
        assert frag in texts, frag
    assert "BocHN" not in " ".join(t["text"] for t in multi["texts"] if "LiOH" in t["text"])


def test_multistep_cdxml(client, multi):
    r = client.post("/api/export", json={"document": multi, "format": "cdxml"})
    mols = Chem.MolsFromCDXML(r.text)
    assert sorted(_flat(Chem.MolToSmiles(m)) for m in mols) == sorted(_flat(s) for s in MULTI_CONSTITUTION.values())
    assert r.text.count("<arrow ") == 8
