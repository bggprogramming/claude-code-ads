#!/usr/bin/env python3
"""
Regenerate the homepage OpenGraph preview (assets/og-index.png, 1200x630).

This is the image iMessage / Slack / Twitter show when someone shares
https://bggprogramming.github.io/mango/. Keep it in sync with the live brand
(Mango, light theme, mango-orange accent) — it went stale once because there
was no generator and the rebrand only updated the HTML.

Requires Pillow and macOS system fonts (Helvetica Neue / Menlo). Run:
    python3 assets/og_gen.py
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ASSETS = Path(__file__).parent
W, H = 1200, 630

# ── Mango light theme (mirrors index.html :root) ──
BG=(253,248,242); BG_WARM=(252,239,224); SURF=(255,255,255)
INK=(32,36,44); MUTED=(138,131,120); HI=(90,83,71); BORDER=(236,228,216)
ACCENT=(245,115,26); ACCENT_D=(224,89,10); ACCENT_2=(255,154,60)


def hn(size, bold=False):
    """Helvetica Neue; pick a Bold face when asked, else fall back to Arial Bold."""
    if bold:
        try:
            for i in range(0, 14):
                f = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", size, index=i)
                n = " ".join(f.getname()).lower()
                if "bold" in n and "cond" not in n and "italic" not in n:
                    return f
        except Exception:
            pass
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)
    return ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", size, index=0)


def mono(size, bold=False):
    if bold:
        for i in range(0, 8):
            try:
                f = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size, index=i)
                if "bold" in " ".join(f.getname()).lower():
                    return f
            except Exception:
                pass
    return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size, index=0)


# ── canvas + warm radial glow ──
img = Image.new("RGB", (W, H), BG)
glow = Image.new("L", (W, H), 0); gd = ImageDraw.Draw(glow)
cx, cy, maxr = W // 2, -40, 560
for r in range(maxr, 0, -4):
    a = int(150 * (1 - r / maxr) ** 1.6)
    gd.ellipse([cx - r, cy - int(r * 0.78), cx + r, cy + int(r * 0.78)], fill=a)
img = Image.composite(Image.new("RGB", (W, H), BG_WARM), img, glow)
d = ImageDraw.Draw(img)

PAD = 80

# ── brand row: mango mark + wordmark ──
logo = Image.open(ASSETS / "mangologo.jpg").convert("RGB").resize((58, 58), Image.LANCZOS)
mask = Image.new("L", (58, 58), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, 57, 57], radius=15, fill=255)
img.paste(logo, (PAD, 60), mask)
d = ImageDraw.Draw(img)
d.text((PAD + 74, 72), "Mango", font=hn(31, bold=True), fill=INK)

# ── headline: line 1 ink, line 2 mango gradient ──
hfont = hn(84, bold=True)
y1 = 150
d.text((PAD, y1), "Get paid", font=hfont, fill=INK)
line2 = "while you code."
bb = d.textbbox((0, 0), line2, font=hfont); tw, th = bb[2] - bb[0], bb[3] - bb[1]
tmask = Image.new("L", (tw + 20, th + 40), 0)
ImageDraw.Draw(tmask).text((-bb[0], -bb[1]), line2, font=hfont, fill=255)
grad = Image.new("RGB", (tw + 20, th + 40)); gp = grad.load()
for x in range(grad.width):
    t = x / max(1, grad.width - 1)
    if t < 0.45:
        c = [ACCENT_D[i] + (ACCENT[i] - ACCENT_D[i]) * (t / 0.45) for i in range(3)]
    else:
        c = [ACCENT[i] + (ACCENT_2[i] - ACCENT[i]) * ((t - 0.45) / 0.55) for i in range(3)]
    col = tuple(int(v) for v in c)
    for yy in range(grad.height):
        gp[x, yy] = col
y2 = y1 + 108
img.paste(grad, (PAD, y2 - 20), tmask)
d = ImageDraw.Draw(img)

# ── subhead (wrapped, max 2 lines) ──
sf = hn(30)
sub = ("The sponsor line your AI terminal already shows while it thinks — "
       "now it pays you. Keep 90% of every dollar.")


def wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


ys = y2 + 118
for ln in wrap(sub, sf, 1000)[:2]:
    d.text((PAD, ys), ln, font=sf, fill=HI); ys += 42

# ── sponsor-line card (light surface, soft shadow) ──
cx0, cy0, cw, ch = PAD, 470, W - 2 * PAD, 108
sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle([cx0, cy0 + 6, cx0 + cw, cy0 + ch + 6], radius=18, fill=(160, 120, 70, 46))
sh = sh.filter(ImageFilter.GaussianBlur(9))
img = Image.alpha_composite(img.convert("RGBA"), sh).convert("RGB")
d = ImageDraw.Draw(img)
d.rounded_rectangle([cx0, cy0, cx0 + cw, cy0 + ch], radius=18, fill=SURF, outline=BORDER, width=2)
dotx, doty = cx0 + 34, cy0 + 34
for col in [(255, 95, 86), (255, 189, 46), (39, 201, 63)]:
    d.ellipse([dotx, doty, dotx + 13, doty + 13], fill=col); dotx += 22
mf, mfm = mono(25, bold=True), mono(21)
tx, ty = cx0 + 118, cy0 + 26
d.text((tx, ty), "⚡ ", font=mf, fill=ACCENT)
wlx = tx + d.textlength("⚡ ", font=mf)
d.text((wlx, ty), "Warp — searchable command history ", font=mf, fill=INK)
ax = wlx + d.textlength("Warp — searchable command history ", font=mf)
d.text((ax, ty), "↗", font=mf, fill=ACCENT)
d.text((tx, ty + 38), "[mango]", font=mfm, fill=ACCENT_D)
ex = tx + d.textlength("[mango]", font=mfm)
d.text((ex, ty + 38), "  $0.42 today · $7.11 total", font=mfm, fill=MUTED)

out = ASSETS / "og-index.png"
img.save(out, "PNG")
print("wrote", out, img.size)
