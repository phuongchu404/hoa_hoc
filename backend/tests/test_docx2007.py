"""Regression set: the 29 reaction images from 2007.docx.

expected.json holds the constitution (SMILES without stereo) of every
structure that was checked by eye against the drawing. Images 4, 27 and 29
contain structures the recogniser cannot read reliably (3D cage, crowded
bridged bicycles); for those only the verified molecules are required, and the
unreadable cage in image 4 must be reported as an error instead of a guess."""
import json
from pathlib import Path

import pytest
from rdkit import Chem

DIR = Path(__file__).parent / "fixtures" / "docx2007"
EXPECTED = json.loads((DIR / "expected.json").read_text())
PARTIAL = {"4", "27", "29"}

pytestmark = pytest.mark.slow


def _flat(s: str) -> str:
    m = Chem.MolFromSmiles(s)
    return Chem.MolToSmiles(m, isomericSmiles=False) if m else s


@pytest.fixture(scope="module")
def client():
    if not any(DIR.glob("image*.png")):
        pytest.skip("test images not present (kept out of git)")
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("n", sorted(EXPECTED, key=int))
def test_image(client, n):
    if not (DIR / f"image{n}.png").exists():
        pytest.skip("test image not present (kept out of git)")
    r = client.post("/api/recognize", files={"file": (f"{n}.png", (DIR / f"image{n}.png").read_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    doc = r.json()
    got = sorted(_flat(m["smiles"]) for m in doc["molecules"] if m["smiles"] and m["status"] != "error")
    exp = sorted(EXPECTED[n])
    if n in PARTIAL:
        missing = [s for s in exp if s not in got]
        assert not missing, f"image {n}: missing {missing}"
    else:
        assert got == exp, f"image {n}"
    if n == "4":
        assert any(m["status"] == "error" for m in doc["molecules"]), "cage product must be flagged"
