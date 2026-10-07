"""Draw the app icon (hexagon ring + arrow) and write AppIcon.icns."""
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(s * 0.09)
    # rounded square with vertical gradient
    top, bottom = (54, 120, 235), (22, 64, 160)
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, s - pad, s - pad], radius=int(s * 0.2), fill=255)
    img.paste(grad, (0, 0), mask)
    # benzene-like hexagon with alternating double bonds
    cx, cy, r = s * 0.40, s * 0.52, s * 0.21
    pts = [(cx + r * math.cos(math.radians(90 + 60 * k)), cy - r * math.sin(math.radians(90 + 60 * k))) for k in range(6)]
    w = max(2, int(s * 0.035))
    d.line(pts + pts[:2], fill="white", width=w, joint="curve")
    for k in (0, 2, 4):
        a, b = pts[k], pts[(k + 1) % 6]
        ia = (cx + (a[0] - cx) * 0.72, cy + (a[1] - cy) * 0.72)
        ib = (cx + (b[0] - cx) * 0.72, cy + (b[1] - cy) * 0.72)
        d.line([ia, ib], fill="white", width=w)
    # arrow to the right
    y = cy
    x0, x1 = s * 0.66, s * 0.84
    d.line([(x0, y), (x1 - s * 0.02, y)], fill="white", width=w)
    h = s * 0.06
    d.polygon([(x1, y), (x1 - h * 1.4, y - h), (x1 - h * 1.4, y + h)], fill="white")
    return img


def main(out: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        base = draw(1024)
        for px in (16, 32, 64, 128, 256, 512, 1024):
            im = base.resize((px, px), Image.LANCZOS)
            if px <= 512:
                im.save(iconset / f"icon_{px}x{px}.png")
            if px >= 32:
                im.save(iconset / f"icon_{px // 2}x{px // 2}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", out], check=True)
        base.save(Path(out).with_suffix(".png"))


if __name__ == "__main__":
    main(sys.argv[1])
