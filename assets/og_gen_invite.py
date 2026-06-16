#!/usr/bin/env python3
"""
Regenerate the referral-invite OpenGraph preview (assets/og-invite.png, 1200x630).

This is the card iMessage / Slack show when someone shares their invite link
(invite.html?ref=CODE) — the most-shared asset in the referral loop, so keep it
on-brand: Mango, light theme, "keep 90%", the "you both get $10" CTA, and the
live /mango URL.

Requires Pillow and macOS system fonts. Run:  python3 assets/og_gen_invite.py
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent
W, H = 1200, 630

BG=(253,248,242); BG_WARM=(252,239,224)
INK=(32,36,44); MUTED=(138,131,120); HI=(90,83,71)
ACCENT=(245,115,26); ACCENT_D=(224,89,10); ACCENT_2=(255,154,60)


def hn(size, bold=False):
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


def mono(size):
    return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size, index=0)


# ── canvas + warm glow ──
img = Image.new("RGB", (W, H), BG)
glow = Image.new("L", (W, H), 0); gd = ImageDraw.Draw(glow)
cx, cy, maxr = W // 2, -40, 560
for r in range(maxr, 0, -4):
    gd.ellipse([cx - r, cy - int(r * 0.78), cx + r, cy + int(r * 0.78)], fill=int(150 * (1 - r / maxr) ** 1.6))
img = Image.composite(Image.new("RGB", (W, H), BG_WARM), img, glow)
d = ImageDraw.Draw(img)
PAD = 80

# ── brand row ──
logo = Image.open(ASSETS / "mangologo.jpg").convert("RGB").resize((58, 58), Image.LANCZOS)
mask = Image.new("L", (58, 58), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, 57, 57], radius=15, fill=255)
img.paste(logo, (PAD, 56), mask)
d = ImageDraw.Draw(img)
d.text((PAD + 74, 68), "Mango", font=hn(31, bold=True), fill=INK)
# small invite eyebrow
d.text((PAD, 150), "YOU'RE INVITED", font=hn(20, bold=True), fill=ACCENT_D)

# ── headline: "Get paid to " ink + "code." gradient ──
hfont = hn(82, bold=True)
hy = 188
d.text((PAD, hy), "Get paid to ", font=hfont, fill=INK)
pre_w = d.textlength("Get paid to ", font=hfont)
word = "code."
bb = d.textbbox((0, 0), word, font=hfont); tw, th = bb[2] - bb[0], bb[3] - bb[1]
tmask = Image.new("L", (tw + 20, th + 40), 0)
ImageDraw.Draw(tmask).text((-bb[0], -bb[1]), word, font=hfont, fill=255)
grad = Image.new("RGB", (tw + 20, th + 40)); gp = grad.load()
for x in range(grad.width):
    t = x / max(1, grad.width - 1)
    c = ([ACCENT_D[i] + (ACCENT[i]-ACCENT_D[i])*(t/0.45) for i in range(3)] if t < 0.45
         else [ACCENT[i] + (ACCENT_2[i]-ACCENT[i])*((t-0.45)/0.55) for i in range(3)])
    col = tuple(int(v) for v in c)
    for yy in range(grad.height):
        gp[x, yy] = col
img.paste(grad, (PAD + int(pre_w), hy + (th + 40 - (bb[3]-bb[1]))//2 - 20 + 8), tmask)
d = ImageDraw.Draw(img)

# ── subhead ──
sf = hn(29)
sub = ("Your terminal already runs sponsored messages while Claude works — "
       "now you keep 90% of every one.")
def wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines
ys = 318
for ln in wrap(sub, sf, 980)[:2]:
    d.text((PAD, ys), ln, font=sf, fill=HI); ys += 41

# ── mango CTA pill (arrow drawn, not a glyph, so it renders in any font) ──
left, right = "Invite a friend", "you both get $10"
pf = hn(28, bold=True)
FG = (255, 250, 244)
lw = d.textlength(left, font=pf); rw = d.textlength(right, font=pf)
arrow_gap = 60
px0, py0 = PAD, 440
pw, ph = int(lw + arrow_gap + rw) + 64, 74
grad2 = Image.new("RGB", (pw, ph)); g2 = grad2.load()
for x in range(pw):
    t = x / max(1, pw - 1)
    col = tuple(int(ACCENT_D[i] + (ACCENT_2[i]-ACCENT_D[i])*t) for i in range(3))
    for yy in range(ph): g2[x, yy] = col
pmask = Image.new("L", (pw, ph), 0)
ImageDraw.Draw(pmask).rounded_rectangle([0, 0, pw-1, ph-1], radius=ph//2, fill=255)
img.paste(grad2, (px0, py0), pmask)
d = ImageDraw.Draw(img)
asc, desc = pf.getmetrics()
ty = py0 + (ph - (asc + desc)) // 2
tx = px0 + 32
d.text((tx, ty), left, font=pf, fill=FG)
ax0 = tx + lw + 20; ay = py0 + ph // 2; ax1 = ax0 + 26
d.line([(ax0, ay), (ax1, ay)], fill=FG, width=4)
d.polygon([(ax1 - 1, ay - 8), (ax1 + 11, ay), (ax1 - 1, ay + 8)], fill=FG)
d.text((ax1 + 22, ty), right, font=pf, fill=FG)

# ── footer url ──
d.text((PAD, 558), "bggprogramming.github.io/mango", font=mono(22), fill=MUTED)

out = ASSETS / "og-invite.png"
img.save(out, "PNG")
print("wrote", out, img.size)
