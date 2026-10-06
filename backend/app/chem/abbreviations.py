"""Superatom (abbreviation) dictionary.

Every entry maps a drawn label to a SMILES fragment whose first atom is a dummy
``*`` marking the attachment point. The bond between ``*`` and its neighbour gives
the attachment bond order (e.g. diazo ``N2`` attaches through a double bond).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from rdkit import Chem


@dataclass(frozen=True)
class Abbreviation:
    label: str
    smiles: str  # starts with "*"


_PH = "c1ccccc1"

# canonical label -> (fragment smiles, aliases)
_TABLE: dict[str, tuple[str, tuple[str, ...]]] = {
    # alkyl
    "Me": ("*C", ("CH3", "H3C")),
    "Et": ("*CC", ("C2H5", "H5C2", "CH2CH3", "H3CH2C")),
    "Pr": ("*CCC", ("nPr", "n-Pr", "C3H7", "CH2CH2CH3")),
    "iPr": ("*C(C)C", ("i-Pr", "iPr", "CH(CH3)2", "(H3C)2HC", "Me2CH")),
    "Bu": ("*CCCC", ("nBu", "n-Bu", "C4H9")),
    "iBu": ("*CC(C)C", ("i-Bu",)),
    "sBu": ("*C(C)CC", ("s-Bu", "sec-Bu")),
    "tBu": ("*C(C)(C)C", ("t-Bu", "But", "tert-Bu", "C(CH3)3", "(H3C)3C", "Me3C", "CMe3")),
    "Cy": ("*C1CCCCC1", ("Chx", "c-Hex", "cHex")),
    "cPr": ("*C1CC1", ("c-Pr",)),
    "Allyl": ("*CC=C", ("allyl", "All")),
    "Vinyl": ("*C=C", ("vinyl", "CH=CH2", "H2C=HC")),
    # aryl / benzyl
    "Ph": ("*" + _PH, ("C6H5", "H5C6")),
    "Bn": ("*C" + _PH, ("CH2Ph", "PhCH2", "PhH2C")),
    "Tol": ("*c1ccc(C)cc1", ("p-Tol", "pTol", "4-MeC6H4", "p-MeC6H4", "p-Tolyl", "pTolyl", "Tolyl", "p-tolyl", "4-Tol")),
    "Mes": ("*c1c(C)cc(C)cc1C", ()),
    "Py": ("*c1ccccn1", ("2-Py",)),
    "PMP": ("*c1ccc(OC)cc1", ("4-MeOC6H4", "p-MeOC6H4")),
    "PMB": ("*Cc1ccc(OC)cc1", ()),
    "Tr": ("*C(c1ccccc1)(c1ccccc1)c1ccccc1", ("Trt", "CPh3", "Ph3C")),
    # carbonyl groups
    "CHO": ("*C=O", ("OHC", "COH")),
    "Ac": ("*C(C)=O", ("COMe", "MeCO", "COCH3", "H3COC", "MeOC")),
    "Bz": ("*C(=O)" + _PH, ("COPh", "PhCO", "PhOC")),
    "Piv": ("*C(=O)C(C)(C)C", ("Pv",)),
    "CO2H": ("*C(=O)O", ("COOH", "HO2C", "HOOC")),
    "CO2Me": ("*C(=O)OC", ("COOMe", "MeO2C", "MeOOC", "CO2CH3", "COOCH3", "H3CO2C", "H3COOC")),
    "CO2Et": ("*C(=O)OCC", ("COOEt", "EtO2C", "EtOOC", "CO2C2H5", "COOC2H5")),
    "CO2iPr": ("*C(=O)OC(C)C", ("iPrO2C",)),
    "CO2tBu": ("*C(=O)OC(C)(C)C", ("COOtBu", "tBuO2C", "tBuOOC", "CO2t-Bu", "t-BuO2C")),
    "CO2Bn": ("*C(=O)OC" + _PH, ("COOBn", "BnO2C", "BnOOC")),
    "CO2Ph": ("*C(=O)O" + _PH, ("PhO2C",)),
    "CO2R": ("*C(=O)O[*]", ("RO2C", "COOR", "ROOC")),
    "COR": ("*C(=O)[*]", ("ROC",)),
    "CONH2": ("*C(N)=O", ("H2NOC", "C(O)NH2")),
    "CONMe2": ("*C(=O)N(C)C", ("Me2NOC",)),
    "COCl": ("*C(=O)Cl", ("ClOC",)),
    # protecting groups
    "Boc": ("*C(=O)OC(C)(C)C", ("BOC", "t-Boc", "tBoc")),
    "Cbz": ("*C(=O)OC" + _PH, ("CBz",)),
    "Fmoc": ("*C(=O)OCC1c2ccccc2-c2ccccc21", ()),
    "Alloc": ("*C(=O)OCC=C", ()),
    "Troc": ("*C(=O)OCC(Cl)(Cl)Cl", ()),
    "Ts": ("*S(=O)(=O)c1ccc(C)cc1", ("Tos", "SO2Tol", "TolSO2")),
    "Ms": ("*S(C)(=O)=O", ("SO2Me", "MeSO2", "SO2CH3")),
    "Tf": ("*S(=O)(=O)C(F)(F)F", ("SO2CF3", "CF3SO2")),
    "Ns": ("*S(=O)(=O)c1ccc([N+](=O)[O-])cc1", ("Nos",)),
    "SO2Ph": ("*S(=O)(=O)" + _PH, ("PhSO2", "PhO2S")),
    "TMS": ("*[Si](C)(C)C", ("SiMe3", "Me3Si")),
    "TES": ("*[Si](CC)(CC)CC", ("SiEt3", "Et3Si")),
    "TBS": ("*[Si](C)(C)C(C)(C)C", ("TBDMS", "SiMe2tBu", "tBuMe2Si")),
    "TIPS": ("*[Si](C(C)C)(C(C)C)C(C)C", ("Si(iPr)3", "(iPr)3Si", "iPr3Si")),
    "TBDPS": ("*[Si](c1ccccc1)(c1ccccc1)C(C)(C)C", ("TBPS", "tBuPh2Si")),
    "THP": ("*C1CCCCO1", ()),
    "MOM": ("*COC", ()),
    "SEM": ("*COCC[Si](C)(C)C", ()),
    "Bpin": ("*B1OC(C)(C)C(C)(C)O1", ("BPin", "pinB", "PinB")),
    # hetero substituents
    "OH": ("*O", ("HO",)),
    "SH": ("*S", ("HS",)),
    "NH2": ("*N", ("H2N",)),
    "NHMe": ("*NC", ("MeHN", "MeNH")),
    "NMe2": ("*N(C)C", ("Me2N", "N(CH3)2", "(H3C)2N")),
    "NEt2": ("*N(CC)CC", ("Et2N",)),
    "NHAc": ("*NC(C)=O", ("AcHN", "AcNH")),
    "NHBoc": ("*NC(=O)OC(C)(C)C", ("BocHN", "BocNH")),
    "NHCbz": ("*NC(=O)OC" + _PH, ("CbzHN", "CbzNH")),
    "NHTs": ("*NS(=O)(=O)c1ccc(C)cc1", ("TsHN", "TsNH")),
    "NHPh": ("*N" + _PH, ("PhHN", "PhNH")),
    "OMe": ("*OC", ("MeO", "OCH3", "H3CO")),
    "OEt": ("*OCC", ("EtO", "OC2H5", "C2H5O")),
    "OiPr": ("*OC(C)C", ("iPrO",)),
    "OtBu": ("*OC(C)(C)C", ("tBuO", "Ot-Bu", "t-BuO")),
    "OPh": ("*O" + _PH, ("PhO",)),
    "OBn": ("*OC" + _PH, ("BnO",)),
    "OAc": ("*OC(C)=O", ("AcO", "OCOCH3")),
    "OBz": ("*OC(=O)" + _PH, ("BzO",)),
    "OPiv": ("*OC(=O)C(C)(C)C", ("PivO",)),
    "OBoc": ("*OC(=O)OC(C)(C)C", ("BocO",)),
    "OTs": ("*OS(=O)(=O)c1ccc(C)cc1", ("TsO",)),
    "OMs": ("*OS(C)(=O)=O", ("MsO",)),
    "OTf": ("*OS(=O)(=O)C(F)(F)F", ("TfO",)),
    "OTMS": ("*O[Si](C)(C)C", ("TMSO", "OSiMe3", "Me3SiO")),
    "OTES": ("*O[Si](CC)(CC)CC", ("TESO",)),
    "OTBS": ("*O[Si](C)(C)C(C)(C)C", ("TBSO", "OTBDMS", "TBDMSO")),
    "OTIPS": ("*O[Si](C(C)C)(C(C)C)C(C)C", ("TIPSO",)),
    "OTBDPS": ("*O[Si](c1ccccc1)(c1ccccc1)C(C)(C)C", ("TBDPSO",)),
    "OPMB": ("*OCc1ccc(OC)cc1", ("PMBO",)),
    "OMOM": ("*OCOC", ("MOMO", "OCH2OMe", "MeOCH2O")),
    "OTHP": ("*OC1CCCCO1", ("THPO",)),
    "OCF3": ("*OC(F)(F)F", ("F3CO",)),
    "SMe": ("*SC", ("MeS",)),
    "SPh": ("*S" + _PH, ("PhS",)),
    "SO3H": ("*S(=O)(=O)O", ("HO3S",)),
    "CN": ("*C#N", ("NC",)),
    "NCO": ("*N=C=O", ("OCN",)),
    "NCS": ("*N=C=S", ("SCN",)),
    "NO2": ("*[N+](=O)[O-]", ("O2N",)),
    "NO": ("*N=O", ("ON",)),
    "N3": ("*N=[N+]=[N-]", ()),
    "N2": ("*=[N+]=[N-]", ()),  # diazo
    "N2+": ("*[N+]#N", ()),  # diazonium
    "CF3": ("*C(F)(F)F", ("F3C",)),
    "CCl3": ("*C(Cl)(Cl)Cl", ("Cl3C",)),
    "CHF2": ("*C(F)F", ("F2HC",)),
    "C6F5": ("*c1c(F)c(F)c(F)c(F)c1F", ("F5C6",)),
    "CH2OH": ("*CO", ("HOH2C", "HOCH2")),
    "CH2Cl": ("*CCl", ("ClH2C", "ClCH2")),
    "CH2Br": ("*CBr", ("BrH2C", "BrCH2")),
    "CH2NH2": ("*CN", ("H2NH2C",)),
    "PO(OEt)2": ("*P(=O)(OCC)OCC", ("(EtO)2OP", "(EtO)2P(O)", "P(O)(OEt)2")),
    "PPh2": ("*P(c1ccccc1)c1ccccc1", ("Ph2P",)),
    "PPh3": ("*[P+](c1ccccc1)(c1ccccc1)c1ccccc1", ("Ph3P",)),
    "SnBu3": ("*[Sn](CCCC)(CCCC)CCCC", ("Bu3Sn", "n-Bu3Sn")),
    "SnMe3": ("*[Sn](C)(C)C", ("Me3Sn",)),
    "MgBr": ("*[Mg]Br", ("BrMg",)),
    "MgCl": ("*[Mg]Cl", ("ClMg",)),
    "MgI": ("*[Mg]I", ("IMg",)),
    "ZnBr": ("*[Zn]Br", ("BrZn",)),
    "ZnCl": ("*[Zn]Cl", ("ClZn",)),
    "ZnI": ("*[Zn]I", ("IZn",)),
    "Li": ("*[Li]", ()),
    "SiH3": ("*[SiH3]", ("H3Si",)),
    "B(OH)2": ("*B(O)O", ("(HO)2B",)),
}


# R-group style labels that must stay as dummy atoms.
RGROUP_LABELS = {
    "R", "R'", "R''", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10",
    "Ra", "Rb", "Rc", "Rd", "Rx", "X", "Y", "Z", "Q", "A", "E", "G", "L", "M",
    "Ar", "Ar1", "Ar2", "Ar'", "Het", "Hal", "Nu", "EWG", "EDG", "PG", "LG", "Pg",
}


def _build_index() -> dict[str, Abbreviation]:
    index: dict[str, Abbreviation] = {}
    for label, (smi, aliases) in _TABLE.items():
        ab = Abbreviation(label, smi)
        for key in (label, *aliases):
            index.setdefault(key, ab)
    return index


_INDEX = _build_index()


def _normalize(label: str) -> str:
    return (
        label.strip()
        .replace("−", "-")
        .replace("–", "-")
        .replace("₂", "2")
        .replace("₃", "3")
        .replace("₄", "4")
        .replace("₅", "5")
        .replace("₆", "6")
        .replace(" ", "")
    )


def _lower_index() -> dict[str, Abbreviation | None]:
    out: dict[str, Abbreviation | None] = {}
    for key, ab in _INDEX.items():
        k = key.lower().replace("-", "")
        out[k] = ab if out.get(k, ab) is ab else None  # None marks an ambiguous spelling
    return out


_LOWER = _lower_index()


def lookup(label: str) -> Abbreviation | None:
    """Find an abbreviation by its drawn label (exact, then normalized, then
    case-insensitively when that is unambiguous: 'P-Tolyl', 'OTbs')."""
    if label in _INDEX:
        return _INDEX[label]
    norm = _normalize(label)
    if norm in _INDEX:
        return _INDEX[norm]
    # "n-Bu" vs "nBu", "t-Bu" vs "tBu"
    nodash = norm.replace("-", "")
    if nodash in _INDEX:
        return _INDEX[nodash]
    if len(nodash) >= 3:
        return _LOWER.get(nodash.lower())
    return None


# Glyph pairs that low-resolution recognition commonly swaps (cost 0.5).
_CONFUSABLE = {
    frozenset(p) for p in [
        ("B", "8"), ("O", "0"), ("o", "0"), ("l", "1"), ("I", "1"), ("I", "l"), ("S", "5"),
        ("Z", "2"), ("z", "2"), ("N", "H"), ("H", "f"), ("n", "h"), ("b", "h"), ("B", "R"),
        ("D", "O"), ("C", "G"), ("c", "e"), ("rn", "m"), ("M", "B"), ("t", "f"), ("P", "R"),
        ("4", "a"), ("3", "y"), ("I", "L"), ("i", "I"), ("l", "L"), ("O", "Q"),
    ]
}
_INDEL = 1.2  # inserting/deleting a glyph is less likely than misreading one


def _sub_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if a.lower() == b.lower():
        return 0.3
    if frozenset((a, b)) in _CONFUSABLE:
        return 0.5
    return 1.0


def _distance(a: str, b: str) -> float:
    prev = [j * _INDEL for j in range(len(b) + 1)]
    for i in range(1, len(a) + 1):
        cur = [i * _INDEL] + [0.0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(
                prev[j] + _INDEL,
                # a missing digit is usually a lost subscript (BocO for Boc2O)
                cur[j - 1] + (0.5 if b[j - 1].isdigit() else _INDEL),
                prev[j - 1] + _sub_cost(a[i - 1], b[j - 1]),
            )
        prev = cur
    return prev[-1]


def lookup_fuzzy(label: str) -> tuple[Abbreviation, str, float] | None:
    """Closest known label for a misread one ('boc' -> Boc, 'BocHf' -> BocHN,
    'TMDPSO' -> TBDPSO). Returns (abbreviation, matched spelling, distance) only
    when the best match is close enough and clearly better than the runner-up."""
    norm = _normalize(label)
    if len(norm) < 2:
        return None
    limit = 0.6 if len(norm) == 2 else (1.0 if len(norm) <= 4 else 1.6)
    def dist(key: str) -> float:
        d = _distance(norm, key)
        if len(key) > len(norm):  # label cut off at the end ("BocH" for "BocHN")
            d = min(d, _distance(norm, key[: len(norm)]) + 0.7 * (len(key) - len(norm)))
        return d

    scored = sorted(
        ((dist(key), key) for key in _INDEX if abs(len(key) - len(norm)) <= 2),
        key=lambda t: t[0],
    )
    if not scored or scored[0][0] > limit:
        return None
    best_d, best_key = scored[0]
    best = _INDEX[best_key]
    for d, key in scored[1:]:
        if d - best_d >= 0.15:
            break
        if _INDEX[key] is not best:  # two different groups equally plausible
            return None
    return best, best_key, best_d


@lru_cache(maxsize=1)
def _by_fragment() -> dict[str, str]:
    out: dict[str, str] = {}
    for label, (smi, _) in _TABLE.items():
        m = Chem.MolFromSmiles(smi)
        if m is not None:
            out.setdefault(Chem.MolToSmiles(m), label)
    return out


def label_for_fragment(smiles_with_dummy: str) -> str | None:
    """'*c1ccccc1' -> 'Ph', '*C(=O)OC' -> 'CO2Me' (None if not a known group)."""
    m = Chem.MolFromSmiles(smiles_with_dummy)
    return _by_fragment().get(Chem.MolToSmiles(m)) if m is not None else None


def is_rgroup(label: str) -> bool:
    norm = _normalize(label)
    return norm in RGROUP_LABELS or (norm.startswith("R") and norm[1:].isdigit())


@lru_cache(maxsize=None)
def fragment_mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:  # pragma: no cover - table is static and tested
        raise ValueError(f"bad abbreviation smiles {smiles}")
    return mol


def all_labels() -> list[str]:
    return sorted(_INDEX)
