"""Generate PWA app icons for the Garmin dashboard (dark theme + green pulse)."""
from PIL import Image, ImageDraw
from pathlib import Path

BG = (10, 10, 14)        # --bg
PANEL = (17, 17, 22)     # --s1
GREEN = (5, 224, 122)    # --green
ICONS = Path("icons")
ICONS.mkdir(exist_ok=True)


def draw_icon(size: int, maskable: bool = False) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG + (255,))
    d = ImageDraw.Draw(img)
    # Rounded panel (smaller inset for maskable safe-zone)
    inset = int(size * 0.06) if maskable else int(size * 0.10)
    r = int(size * 0.22)
    d.rounded_rectangle([inset, inset, size - inset, size - inset],
                        radius=r, fill=PANEL)
    # Heart-rate pulse line across the middle
    cy = size / 2
    w = size - 2 * inset
    x0 = inset + w * 0.12
    span = w * 0.76
    amp = size * 0.16
    pts_rel = [(0.00, 0.0), (0.22, 0.0), (0.32, -0.4), (0.44, 1.0),
               (0.56, -1.6), (0.66, 0.5), (0.74, 0.0), (1.00, 0.0)]
    pts = [(x0 + span * fx, cy + amp * fy) for fx, fy in pts_rel]
    d.line(pts, fill=GREEN, width=max(3, int(size * 0.045)), joint="curve")
    # Accent dot
    d.ellipse([pts[4][0] - size*0.03, pts[4][1] - size*0.03,
               pts[4][0] + size*0.03, pts[4][1] + size*0.03], fill=GREEN)
    return img


for s in (192, 512):
    draw_icon(s).save(ICONS / f"icon-{s}.png")
draw_icon(512, maskable=True).save(ICONS / "icon-maskable-512.png")
draw_icon(180).save(ICONS / "apple-touch-icon.png")
print("icons written:", [p.name for p in ICONS.iterdir()])
