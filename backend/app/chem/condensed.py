"""Parser for condensed-formula labels such as CO2CH2CCl3, COCO2CH3, CH2CO2Me,
CH2OCH3, CO2R, H3CO2C.

A label is read as a chain of units (atom + hydrogens + multiplier). Carbon
valence decides between a carbonyl and a chain bond, the way a chemist reads
it: "CO" with no H on the carbon is C=O, "CO2" is an ester/acid carbon,
"CH2O" is an ether, trailing halogens (CCl3, CF3) hang off the last carbon.
The result is a SMILES fragment starting with the attachment dummy "*".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rdkit import Chem

from . import abbreviations as abbr

# groups that may appear inside a condensed label, longest first
_GROUPS = ["TBDPS", "TIPS", "TBS", "TMS", "TES", "PMB", "MOM", "Boc", "Cbz", "Piv",
           "tBu", "iPr", "nPr", "nBu", "iBu", "Me", "Et", "Pr", "Bu", "Ph", "Bn", "Bz",
           "Ac", "Ts", "Ms", "Tf"]
_TOKEN = re.compile(
    r"(R\d*'*)|(" + "|".join(_GROUPS) + r")|(Cl|Br|Si|Sn|C|O|N|S|P|B|F|I|H)(\d*)|(\()|(\))(\d*)"
)
_VALENCE = {"C": 4, "Si": 4, "Sn": 4, "N": 3, "P": 3, "B": 3, "O": 2, "S": 2,
            "F": 1, "Cl": 1, "Br": 1, "I": 1}
_HALOGEN = {"F", "Cl", "Br", "I"}


@dataclass
class _Unit:
    kind: str  # "atom" | "group" | "r"
    sym: str
    h: int = 0
    n: int = 1


def _units(label: str) -> list[_Unit] | None:
    pos, out = 0, []
    pending_h = 0  # leading H (H3C...) belongs to the next heavy atom
    while pos < len(label):
        m = _TOKEN.match(label, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        if m.group(1):
            out.append(_Unit("r", m.group(1)))
        elif m.group(2):
            out.append(_Unit("group", m.group(2)))
        elif m.group(3):
            sym, cnt = m.group(3), int(m.group(4) or 1)
            if sym == "H":
                if out and out[-1].kind == "atom" and out[-1].sym not in _HALOGEN:
                    out[-1].h += cnt
                elif out:
                    return None  # H after a group/halogen: not a condensed formula
                else:
                    pending_h += cnt
                continue
            u = _Unit("atom", sym, h=pending_h, n=cnt)
            pending_h = 0
            out.append(u)
        else:
            return None  # parentheses: leave to the generic parser
    if pending_h:
        return None  # a dangling H (truncated label such as "BocH") is not a formula
    return out or None


def _expand(units: list[_Unit]) -> list[_Unit]:
    """O2 after a carbon stays as one unit (ester); other multipliers on heavy
    chain atoms are spelled out (C2H5 -> C, C)."""
    out: list[_Unit] = []
    for u in units:
        if u.kind == "atom" and u.n > 1 and u.sym not in _HALOGEN and not (u.sym == "O" and u.n == 2):
            per_h = u.h // u.n
            for k in range(u.n):
                out.append(_Unit("atom", u.sym, h=per_h + (u.h - per_h * u.n if k == u.n - 1 else 0)))
        else:
            out.append(u)
    return out


def parse(label: str, reverse: bool = False) -> str | None:
    """Return '*'-anchored SMILES for a condensed label, or None. With
    reverse=True the label is read from its right end (label drawn left of
    the bond, e.g. H3CO2C-)."""
    units = _units(label)
    if not units:
        return None
    if reverse:
        units = list(reversed(units))
    units = _expand(units)
    smi = "*"
    free = 1  # bonds still available on the current chain end (the dummy)
    i = 0
    while i < len(units):
        u = units[i]
        nxt = units[i + 1] if i + 1 < len(units) else None
        if u.kind == "r":
            iso = u.sym[1:].rstrip("'")
            smi += f"[{iso}*]" if iso.isdigit() else "[*]"
            free = 0
            i += 1
            continue
        if u.kind == "group":
            ab = abbr.lookup(u.sym)
            if ab is None:
                return None
            smi += ab.smiles[1:]  # fragment without its own '*'
            free = 0
            i += 1
            continue
        sym = u.sym
        if sym in _HALOGEN:
            # halogens decorate the previous carbon
            return None if u.n > 1 else _finish(smi + sym)
        val = _VALENCE.get(sym)
        if val is None:
            return None
        rem = val - u.h - 1  # after the bond to the chain
        atom = sym if sym in ("C", "N", "O", "S", "P", "B", "F", "I") else f"[{sym}]"
        piece = atom
        # halogens on this atom: CCl3, CF3, CHCl2, CCl2CH3
        if nxt is not None and nxt.kind == "atom" and nxt.sym in _HALOGEN and nxt.n <= rem:
            smi += atom + "".join(f"({nxt.sym})" for _ in range(nxt.n))
            free = rem - nxt.n
            i += 2
            continue
        if sym == "C" and nxt is not None and nxt.kind == "atom" and nxt.sym == "O":
            if nxt.n == 2 and rem >= 3:  # CO2: ester / acid carbon
                piece = "C(=O)O"
                smi += piece
                i += 2
                free = 1
                continue
            if nxt.n == 1 and rem >= 3 and i + 2 < len(units):  # C(=O) inside a chain
                smi += "C(=O)"
                i += 2
                free = 1
                continue
            if nxt.n == 1 and rem == 2 and i + 2 == len(units):  # CHO
                smi += "C=O"
                i += 2
                free = 0
                continue
        smi += piece
        free = rem
        i += 1
    return _finish(smi)


def _finish(smi: str) -> str | None:
    m = Chem.MolFromSmiles(smi)
    if m is None:
        return None
    return smi


def parse_label(label: str, neighbour_on_right: bool) -> str | None:
    """Pick the reading direction from where the bond leaves the label."""
    first = parse(label, reverse=neighbour_on_right)
    if first is not None:
        return first
    return parse(label, reverse=not neighbour_on_right)
