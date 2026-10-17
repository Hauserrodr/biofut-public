"""Link preview of /copa: one 1200x630 JPEG per day left (og/copa-<days>.jpg), so a pasted link shows today's countdown.

    python og_copa.py      # deploy.ps1 runs it; needs Pillow on this PC, not on the server

Same look as og.png: near-black, Bahnschrift condensed, white + BioFut pink, the 4-colour stripe at the bottom.
ponytail: pre-rendered per day because the server has no Pillow; a day after the last image /copa falls back to og.png.
"""
import functools
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

COPA = datetime(2026, 11, 21, 8, 30, tzinfo=timezone(timedelta(hours=-3)))  # same as COPA_DAY in index.html and server.py
HERE = Path(__file__).parent
OUT = HERE / "og"
S = 2  # drawn at 2x, then scaled down: smooth edges
W, H = 1200, 630
BG, PANEL, LINE = (12, 13, 12), (20, 22, 20), (44, 47, 44)
INK, MUT, PINK, YEL = (242, 242, 238), (163, 166, 159), (255, 74, 110), (242, 194, 48)
STRIPE = [(255, 74, 110), (240, 96, 96), (242, 194, 48), (72, 0, 120)]  # og.png's


@functools.cache
def font(size, style="Bold Condensed"):
    f = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", size * S)
    f.set_variation_by_name(style)
    return f


def days_left(now=None):
    return max(0, math.ceil(((COPA - (now or datetime.now(timezone.utc))).total_seconds()) / 86400))


def spaced(d, xy, text, f, fill, track, anchor="l"):
    """Letter-spaced caps (track in px); anchor l / m / r on x, baseline on y."""
    w = sum(d.textlength(c, font=f) for c in text) + track * S * (len(text) - 1)
    x = xy[0] * S - {"l": 0, "m": w / 2, "r": w}[anchor]
    for c in text:
        d.text((x, xy[1] * S), c, font=f, fill=fill, anchor="ls")
        x += d.textlength(c, font=f) + track * S


@functools.cache
def base():
    img = Image.new("RGB", (W * S, H * S), BG)
    glow = Image.new("L", img.size)
    ImageDraw.Draw(glow).ellipse([700 * S, -40 * S, 1190 * S, 660 * S], fill=255)
    img = Image.composite(Image.new("RGB", img.size, (70, 14, 32)), img, glow.filter(ImageFilter.GaussianBlur(110 * S)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([772 * S, 64 * S, 1128 * S, 548 * S], 22 * S, fill=PANEL, outline=LINE, width=2 * S)
    d.rounded_rectangle([900 * S, 64 * S, 1000 * S, 70 * S], 3 * S, fill=PINK)  # accent on the countdown card
    for i, c in enumerate(STRIPE):
        d.rectangle([i * 300 * S, 616 * S, (i + 1) * 300 * S, H * S], fill=c)
    logo = Image.open(HERE / "logo.png").convert("RGBA")
    logo = logo.resize((round(logo.width * 72 * S / logo.height), 72 * S), Image.LANCZOS)
    img.paste(logo, (72 * S, 58 * S), logo)
    d.text((140 * S, 112 * S), "BIO", font=font(44), fill=INK, anchor="ls")
    d.text((140 * S + d.textlength("BIO", font=font(44)), 112 * S), "FUT", font=font(44), fill=PINK, anchor="ls")
    spaced(d, (72, 214), "5ª COPA BIOFUT", font(28, "SemiBold Condensed"), YEL, 5)
    d.text((68 * S, 334 * S), "SUPERCOPA", font=font(124), fill=INK, anchor="ls")
    d.text((68 * S, 452 * S), "2026", font=font(124), fill=PINK, anchor="ls")
    d.text((72 * S, 506 * S), "Sábado, 21 de novembro · 8:30 às 14:30", font=font(32, "SemiBold Condensed"), fill=INK, anchor="ls")
    d.text((72 * S, 548 * S), "Quem jogar a Copa ganha 50 moedas no site", font=font(28, "SemiBold Condensed"), fill=YEL, anchor="ls")
    d.text((1128 * S, 590 * S), "biofut.h-brain.org/copa", font=font(22, "SemiBold Condensed"), fill=MUT, anchor="rs")
    return img


def render(n):
    img = base().copy()
    d = ImageDraw.Draw(img)
    cx = 950
    if n:
        spaced(d, (cx, 140), "FALTAM", font(30, "SemiBold Condensed"), MUT, 8, "m")
        d.text((cx * S, 300 * S), str(n), font=font(250 if n < 100 else 190), fill=INK, anchor="mm")
        spaced(d, (cx, 500), "DIA" if n == 1 else "DIAS", font(46), PINK, 10, "m")
    else:
        spaced(d, (cx, 140), "A COPA É", font(30, "SemiBold Condensed"), MUT, 8, "m")
        d.text((cx * S, 300 * S), "HOJE", font=font(170), fill=PINK, anchor="mm")
        spaced(d, (cx, 500), "8:30", font(46), INK, 6, "m")
    return img.resize((W, H), Image.LANCZOS)


if __name__ == "__main__":
    assert days_left(COPA) == 0 and days_left(COPA - timedelta(hours=1)) == 1 and days_left(COPA - timedelta(days=2)) == 2
    OUT.mkdir(exist_ok=True)
    for n in range(days_left() + 1):
        render(n).save(OUT / f"copa-{n}.jpg", quality=88, optimize=True)
    print(f"og: {days_left() + 1} images in {OUT}")
