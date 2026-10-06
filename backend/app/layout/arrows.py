"""Locate the reaction arrow between reactants and products with OpenCV."""
from __future__ import annotations

import cv2
import numpy as np

Box = tuple[float, float, float, float]


def _union(boxes: list[Box]) -> Box:
    return (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )


def find_arrow(
    gray: np.ndarray,
    reactants: list[Box],
    products: list[Box],
    conditions: list[Box],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return (tail, head) in pixels. Falls back to a straight line between the
    reactant and product groups when no arrow-like stroke is found."""
    h, w = gray.shape[:2]
    r = _union(reactants) if reactants else None
    p = _union(products) if products else None
    everything = [b for b in (r, p) if b] + list(conditions)
    region_box = _union(everything) if everything else (0, 0, w, h)

    found: list[tuple[float, tuple, tuple]] = []
    if r and p:
        rc = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        pc = ((p[0] + p[2]) / 2, (p[1] + p[3]) / 2)
        y0 = int(max(0, region_box[1]))
        y1 = int(min(h, region_box[3]))
        # arrow in the horizontal gap (products right or left of reactants)
        if p[0] > r[2] - 5 or r[0] > p[2] - 5:
            gx0, gx1 = (r[2], p[0]) if p[0] > r[2] - 5 else (p[2], r[0])
            hit = _longest_stroke(gray, int(max(0, gx0 - 4)), y0, int(min(w, gx1 + 4)), y1, horizontal=True)
            if hit:
                found.append((float(np.hypot(hit[1][0] - hit[0][0], hit[1][1] - hit[0][1])), *hit))
        # vertical step: arrow between the molecules or beside them (also elbows)
        if p[1] > r[3] - 5 or r[1] > p[3] - 5:
            vx0 = int(max(0, min(r[0], p[0]) - 30))
            vx1 = int(min(w, max(r[2], p[2]) + 30))
            hit = _longest_stroke(gray, vx0, int(max(0, min(r[1], p[1]))), vx1,
                                  int(min(h, max(r[3], p[3]))), horizontal=False,
                                  exclude=list(reactants) + list(products))
            if hit:
                found.append((float(np.hypot(hit[1][0] - hit[0][0], hit[1][1] - hit[0][1])), *hit))
        if found:
            _, tail, head = max(found, key=lambda t: t[0])
            # always point from reactants to products
            if (head[0] - tail[0]) * (pc[0] - rc[0]) + (head[1] - tail[1]) * (pc[1] - rc[1]) < 0:
                tail, head = head, tail
            return tail, head

    # fallback: centre-to-centre between the facing edges
    if r and p:
        rc = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        pc = ((p[0] + p[2]) / 2, (p[1] + p[3]) / 2)
        if abs(pc[0] - rc[0]) >= abs(pc[1] - rc[1]):
            y = (rc[1] + pc[1]) / 2
            if conditions:
                cb = _union(conditions)
                y = (cb[1] + cb[3]) / 2
            if pc[0] > rc[0]:
                return (r[2] + 10, y), (p[0] - 10, y)
            return (r[0] - 10, y), (p[2] + 10, y)
        x = (rc[0] + pc[0]) / 2
        if pc[1] > rc[1]:
            return (x, r[3] + 10), (x, p[1] - 10)
        return (x, r[1] - 10), (x, p[3] + 10)
    y = h / 2
    return (w * 0.4, y), (w * 0.6, y)


def _longest_stroke(gray: np.ndarray, x0: int, y0: int, x1: int, y1: int, horizontal: bool,
                    exclude: list[Box] | None = None):
    """Find the arrow in a region: the largest thin ink component (straight or
    elbow-shaped) that is not part of a molecule. Returns (tail, head) snapped
    to the requested orientation, with head at the arrowhead."""
    if x1 - x0 < 10 or y1 - y0 < 4:
        return None
    roi = gray[y0:y1, x0:x1]
    _, bw = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    span = (x1 - x0) if horizontal else (y1 - y0)
    best, best_len = None, 0
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        length = cw if horizontal else ch
        thick = ch if horizontal else cw
        straight = length >= 3 * thick
        elbow = max(cw, ch) >= 20 and area / float(cw * ch) < 0.18  # thin L / U shapes
        if not (straight or elbow):
            continue
        if length < (20 if exclude else max(30, 0.25 * span)):
            continue
        if exclude:
            # ink of a molecule often pokes a little outside its box: count the
            # component's pixels that fall inside slightly enlarged boxes
            comp = labels[y:y + ch, x:x + cw] == i
            yy, xx = np.nonzero(comp)
            gx, gy = xx + x0 + x, yy + y0 + y
            inside = np.zeros(len(gx), dtype=bool)
            for b in exclude:
                pad = 0.08 * max(b[2] - b[0], b[3] - b[1])
                inside |= (gx >= b[0] - pad) & (gx <= b[2] + pad) & (gy >= b[1] - pad) & (gy <= b[3] + pad)
            if inside.mean() > 0.35:
                continue
        if length > best_len:
            best_len, best = length, (x, y, cw, ch, i)
    if best is None:
        return None
    x, y, cw, ch, i = best
    mask = (labels[y:y + ch, x:x + cw] == i).astype(np.uint8)
    ys, xs = np.nonzero(mask)
    # arrowhead = densest small window of ink
    k = max(5, min(cw, ch, 15) if min(cw, ch) >= 5 else 5)
    dens = cv2.boxFilter(mask.astype(np.float32), -1, (k, k), normalize=False)
    hy, hx = np.unravel_index(int(np.argmax(dens)), dens.shape)

    def run(line: np.ndarray, c: int) -> tuple[int, int]:
        lo = hi = c
        while lo > 0 and line[lo - 1]:
            lo -= 1
        while hi < len(line) - 1 and line[hi + 1]:
            hi += 1
        return lo, hi

    # the shaft leaving the arrowhead decides the direction (handles elbows)
    # shaft row / column: the fullest line within one window of the head
    r0, r1 = max(0, hy - k), min(mask.shape[0], hy + k + 1)
    c0, c1 = max(0, hx - k), min(mask.shape[1], hx + k + 1)
    srow = r0 + int(np.argmax(mask[r0:r1].sum(axis=1)))
    scol = c0 + int(np.argmax(mask[:, c0:c1].sum(axis=0)))
    rows = mask[max(0, srow - 1):srow + 2, :].any(axis=0)
    cols = mask[:, max(0, scol - 1):scol + 2].any(axis=1)
    lh, rh = run(rows, min(max(hx, 0), len(rows) - 1))
    lv, rv = run(cols, min(max(hy, 0), len(cols) - 1))
    if rh - lh >= rv - lv:
        head_x, tail_x = (lh, rh) if hx - lh < rh - hx else (rh, lh)
        yy = float(y0 + y + srow)
        return (float(x0 + x + tail_x), yy), (float(x0 + x + head_x), yy)
    head_y, tail_y = (lv, rv) if hy - lv < rv - hy else (rv, lv)
    xx = float(x0 + x + scol)
    return (xx, float(y0 + y + tail_y)), (xx, float(y0 + y + head_y))
