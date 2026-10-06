"""Text recognition for reaction conditions using the macOS Vision framework
(fully local). Includes chemistry-aware clean-up: Vision tends to read
subscript digits as '½', '¿', 'z', ',' ... (e.g. 'Rh½(OAc)4' -> 'Rh2(OAc)4')."""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

from PIL import Image

log = logging.getLogger(__name__)


@dataclass
class TextLine:
    text: str
    bbox: tuple[float, float, float, float]  # pixels x0, y0, x1, y1
    confidence: float


class OcrEngine:
    def __init__(self) -> None:
        try:
            import Vision  # noqa: F401
            from Foundation import NSData  # noqa: F401

            self.available = True
        except Exception as exc:  # pragma: no cover - non-mac
            log.warning("OCR unavailable (macOS Vision not found): %s", exc)
            self.available = False

    def recognize(self, image: Image.Image) -> list[TextLine]:
        if not self.available:
            return []
        import Vision
        from Foundation import NSData

        w, h = image.size
        # small images: upscale so 5-8 px text becomes legible to Vision
        f = 3 if max(w, h) < 900 else (2 if max(w, h) < 1400 else 1)
        if f > 1:
            image = image.resize((w * f, h * f), Image.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        raw = buf.getvalue()
        data = NSData.dataWithBytes_length_(raw, len(raw))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(0)  # accurate
        req.setUsesLanguageCorrection_(True)
        req.setRecognitionLanguages_(["en-US"])
        ok, err = handler.performRequests_error_([req], None)
        if not ok:  # pragma: no cover
            log.warning("OCR failed: %s", err)
            return []
        lines: list[TextLine] = []
        for obs in req.results() or []:
            cands = obs.topCandidates_(1)
            if not cands:
                continue
            cand = cands[0]
            box = obs.boundingBox()
            x, y = box.origin.x, box.origin.y
            bw, bh = box.size.width, box.size.height
            # Vision: normalised, origin bottom-left
            bbox = (x * w, (1 - y - bh) * h, (x + bw) * w, (1 - y) * h)
            lines.append(TextLine(clean_text(str(cand.string())), bbox, float(cand.confidence())))
        return lines


# ----------------------------------------------------------------------------- clean-up

_HOMOGLYPHS = str.maketrans({
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K", "М": "M", "О": "O", "Р": "P",
    "Т": "T", "Х": "X", "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y",
    "º": "°", "˚": "°", "℃": "°C", "−": "-", "–": "-", "з": "3", "З": "3", "•": " ", "·": "·",
})
_SUB_GLYPHS = str.maketrans({
    "½": "2", "¿": "2", "ź": "2", "ż": "2", "²": "2", "₂": "2", "³": "3", "₃": "3",
    "⁴": "4", "₄": "4", "₅": "5", "⁵": "5", "₆": "6", "₁": "1", "¹": "1", "₀": "0",
})
_DEG = re.compile(r"(\d)\s*[o°]\s*C\b")
_CHEM_TOKEN = re.compile(r"[A-Z]")


def _fix_chem_token(tok: str) -> str:
    if not _CHEM_TOKEN.search(tok):
        return tok
    t = tok.translate(_SUB_GLYPHS)
    # 'z' standing in for a subscript 2: COzEt, Nz, CHzClz (but not Cbz / Bz)
    t = t.replace("Cbz", "\x00").replace("Bz", "\x01")
    t = re.sub(r"(?<=[A-Za-z)\]])z(?=[A-Z(]|$|[,;.])", "2", t)
    t = re.sub(r"(?<=H)Z(?=[A-Z(]|$)", "2", t)  # CHZ -> CH2
    t = t.replace("\x00", "Cbz").replace("\x01", "Bz")
    # 'CO,Me' -> 'CO2Me' (comma glued between capitals)
    t = re.sub(r"(?<=[A-Z]),(?=[A-Z])", "2", t)
    # subscript 2 read as a dot between element symbols: H.O -> H2O
    t = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", "2", t)
    # subscripts read as "_" or "s": CH_PPhs -> CH2PPh3
    t = re.sub(r"(?<=[A-Za-z])_(?=[A-Z])", "2", t)
    t = re.sub(r"(?<=Ph)s\b", "3", t)
    # capital I read for lower-case l in chlorine: TiCI4, CICOOEt, Pd(dppf)CI2
    t = re.sub(r"CI(?=$|[\d,;.)A-Z])", "Cl", t)
    return t


def clean_text(text: str) -> str:
    t = text.strip().translate(_HOMOGLYPHS)
    t = _DEG.sub(r"\1 °C", t)
    toks = [_fix_chem_token(tok) for tok in t.split(" ")]
    # a lone label on its own line (MgBr next to a drawn bond) is not a reagent typo
    from ..chem.abbreviations import lookup as _lookup_label

    if not (len(toks) == 1 and _lookup_label(toks[0].rstrip(",;.:")) is not None):
        toks = [_fix_reagent(tok) for tok in toks]
    t = " ".join(toks)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",{2,}", ",", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t


_FORMULA = re.compile(r"^[A-Z(\[][A-Za-z0-9()\[\]·•+\-]*\d[A-Za-z0-9()\[\]·•+\-]*[,;.]?$")


def looks_like_formula(token: str) -> bool:
    """True for tokens such as Rh2(OAc)4, CH2Cl2, K2CO3, Pd(PPh3)4 whose digits
    should be rendered as subscripts."""
    return bool(_FORMULA.match(token)) and not token[0].isdigit()


# Common reagents, catalysts and solvents used to snap misread tokens
# ("NaBHa" -> "NaBH4", "LIOH" -> "LiOH", "CICOOEt" -> "ClCOOEt").
REAGENTS = """
LiOH NaOH KOH CsOH LiHMDS NaHMDS KHMDS LDA LiAlH4 NaBH4 NaBH3CN NaBH(OAc)3 DIBAL DIBAL-H L-Selectride
BH3 9-BBN BH3·THF MeI EtI BnBr BnCl MeOTf Me2SO4 TMSCl TBSCl TBSOTf TBDPSCl TIPSCl TESCl Boc2O CbzCl
FmocCl Ac2O AcCl BzCl PivCl MsCl TsCl Tf2O TFA TFAA HCl HBr HI H2SO4 HNO3 H3PO4 AcOH HCO2H TsOH
PPTS CSA BF3·OEt2 TiCl4 SnCl4 AlCl3 ZnCl2 MgBr2 SiMe3 allylSiMe3 allylMgBr MeMgBr EtMgBr PhMgBr
MeLi nBuLi n-BuLi sBuLi tBuLi PhLi LiCl LiBr NaI KI CsF KF TBAF TBAI NaH KH CaH2 K2CO3 Na2CO3
Cs2CO3 NaHCO3 KHCO3 K3PO4 Et3N iPr2NEt DIPEA DBU DMAP DABCO pyridine imidazole NMM NMO TEMPO
DMP IBX PCC PDC MnO2 KMnO4 OsO4 NaIO4 mCPBA m-CPBA H2O2 O3 DDQ CAN Pd/C Pd(OAc)2 Pd(PPh3)4
Pd2(dba)3 Pd(dppf)Cl2 PdCl2 Pd(dba)2 Ni(cod)2 CuI CuBr CuCN CuSO4 Rh2(OAc)4 RuCl3 Grubbs AIBN
Bu3SnH SmI2 Zn Mg Li Na K H2 N2 Ar NH3 NH4Cl NH4OAc NaN3 DPPA HATU HBTU EDC EDCI DCC DIC HOBt
PPh3 AsPh3 P(o-tol)3 XPhos SPhos BINAP dppf dppp dppe DEAD DIAD CBr4 NBS NCS NIS I2 Br2 Cl2
SOCl2 POCl3 PCl5 (COCl)2 DMF DMSO THF Et2O DCM CH2Cl2 CHCl3 CCl4 MeCN MeOH EtOH iPrOH tBuOH
H2O toluene benzene hexane hexanes pentane heptane dioxane DME acetone EtOAc NMP HMPA DMPU
ClCOOEt ClCO2Et ClCO2Me ICH=CH-COOMe CH2PPh3 Ph3P=CH2 reflux rt
""".split()
_REAGENT_SET = set(REAGENTS)


def _fix_reagent(tok: str) -> str:
    core = tok.rstrip(",;.:")
    tail = tok[len(core):]
    if len(core) < 3 or core in _REAGENT_SET or not re.search(r"[A-Z]", core) or core.isdigit():
        return tok
    from ..chem.abbreviations import lookup as _lookup_label

    label_like = _lookup_label(core) is not None  # MeO, OTBS ... are labels, not typos
    if re.fullmatch(r"\d+[a-z]?\.?", core):  # step numbers "7a."
        return tok
    from ..chem.abbreviations import _distance

    limit = 1.0 if len(core) <= 5 else 1.6
    scored = sorted((_distance(core, r), r) for r in REAGENTS if abs(len(r) - len(core)) <= 2)
    if not scored or scored[0][0] > limit:
        return tok
    if len(scored) > 1 and scored[1][0] - scored[0][0] < 0.15 and scored[1][1] != scored[0][1]:
        return tok
    if label_like and re.sub(r"\d", "", scored[0][1]) != re.sub(r"\d", "", core):
        return tok  # only restore lost subscripts on a valid label (BocO -> Boc2O, not MeO -> MeI)
    return scored[0][1] + tail
