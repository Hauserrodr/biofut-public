"""The SuperCopa countdown, one image per day left: og/copa-<days>.jpg (1200x630: /copa's link preview and the bot's noon
post in the group) and og/story-<days>.jpg (1080x1920 Instagram story).

    python og_copa.py      # deploy.ps1 runs it; needs Pillow on this PC, not on the server

Near-black, Bahnschrift condensed, white + BioFut pink, the 4-colour stripe at the bottom, the mascots' art (copa_art.jpg,
the Instagram's 18/10 post). Up to 05/11 the sign-up deadline, after it the four teams in their shirt colours.
ponytail: pre-rendered per day because the server has no Pillow; a day after the last image /copa falls back to og.png.
"""
import functools
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

COPA = datetime(2026, 11, 21, 8, 30, tzinfo=timezone(timedelta(hours=-3)))  # same as COPA_DAY in index.html and server.py
CLOSE_N = 16  # days left on 05/11, the form's last day (server.py COPA_CLOSE)
HERE = Path(__file__).parent
OUT = HERE / "og"
S = 2  # drawn at 2x, then scaled down: smooth edges
BG, PANEL, LINE = (12, 13, 12), (20, 22, 20), (44, 47, 44)
INK, MUT, PINK, YEL = (242, 242, 238), (163, 166, 159), (255, 74, 110), (242, 194, 48)
STRIPE = [(255, 74, 110), (240, 96, 96), (242, 194, 48), (72, 0, 120)]  # og.png's
TEAMS = [("Pavões", (176, 120, 255)), ("Bagres", (80, 200, 120)), ("Babuínos", INK), ("Axolotes", (255, 130, 190))]  # shirt colours (preta -> white on black)


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


def row(d, xy, parts, anchor="l"):
    """[(text, font, fill), ...] on one baseline, anchor l / m on x."""
    w = sum(d.textlength(t, font=f) for t, f, _ in parts)
    x = xy[0] * S - (w / 2 if anchor == "m" else 0)
    for t, f, c in parts:
        d.text((x, xy[1] * S), t, font=f, fill=c, anchor="ls")
        x += d.textlength(t, font=f)


def teams(d, xy, size, anchor="l"):
    dot = font(size, "SemiBold Condensed")
    parts = []
    for i, (t, c) in enumerate(TEAMS):
        parts += [(t, font(size), c)] + ([("  ·  ", dot, MUT)] if i < 3 else [])
    row(d, xy, parts, anchor)


def canvas(w, h, glow_box):
    img = Image.new("RGB", (w * S, h * S), BG)
    glow = Image.new("L", img.size)
    ImageDraw.Draw(glow).ellipse([v * S for v in glow_box], fill=255)
    img = Image.composite(Image.new("RGB", img.size, (70, 14, 32)), img, glow.filter(ImageFilter.GaussianBlur(110 * S)))
    d = ImageDraw.Draw(img)
    for i, c in enumerate(STRIPE):
        d.rectangle([i * w // 4 * S, (h - 14) * S, (i + 1) * w // 4 * S, h * S], fill=c)
    return img, d


def art(img, d, x, y, size):
    a = Image.open(HERE / "copa_art.jpg").convert("RGB").resize((size * S, size * S), Image.LANCZOS)
    mask = Image.new("L", a.size)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, a.width - 1, a.height - 1], 26 * S, fill=255)
    img.paste(a, (x * S, y * S), mask)
    d.rounded_rectangle([x * S, y * S, (x + size) * S, (y + size) * S], 26 * S, outline=LINE, width=2 * S)


def logo(img, d, x, y, h, anchor="l"):
    lg = Image.open(HERE / "logo.png").convert("RGBA")
    lg = lg.resize((round(lg.width * h * S / lg.height), h * S), Image.LANCZOS)
    f = font(round(h * 0.6))
    w = lg.width + 12 * S + d.textlength("BIOFUT", font=f)
    x0 = x * S - (w / 2 if anchor == "m" else 0)
    img.paste(lg, (round(x0), y * S), lg)
    tx, ty = x0 + lg.width + 12 * S, y * S + h * S * 0.76
    d.text((tx, ty), "BIO", font=f, fill=INK, anchor="ls")
    d.text((tx + d.textlength("BIO", font=f), ty), "FUT", font=f, fill=PINK, anchor="ls")


def render(n):
    """1200x630: the art on the left, the countdown on the right."""
    img, d = canvas(1200, 630, [640, -40, 1190, 660])
    art(img, d, 36, 36, 544)
    x = 628
    logo(img, d, x, 44, 52)
    spaced(d, (x, 146), "5ª COPA BIOFUT", font(26, "SemiBold Condensed"), YEL, 5)
    row(d, (x - 3, 236), [("SUPERCOPA ", font(84), INK), ("2026", font(84), PINK)])
    if n:
        big = font(200)
        d.text((x * S - 6 * S, 452 * S), str(n), font=big, fill=PINK, anchor="ls")
        nx = (x * S + d.textlength(str(n), font=big)) / S + 14
        spaced(d, (nx, 360), "FALTA" if n == 1 else "FALTAM", font(30, "SemiBold Condensed"), MUT, 8)
        d.text((nx * S, 446 * S), "DIA" if n == 1 else "DIAS", font=font(84), fill=INK, anchor="ls")
    else:
        spaced(d, (x, 320), "A COPA É", font(30, "SemiBold Condensed"), MUT, 8)
        d.text((x * S - 6 * S, 452 * S), "HOJE", font=font(150), fill=PINK, anchor="ls")
    d.text((x * S, 508 * S), "Sábado, 21/11 · 8:30 às 14:30", font=font(32, "SemiBold Condensed"), fill=INK, anchor="ls")
    if n >= CLOSE_N:
        d.text((x * S, 556 * S), f"Inscrição até 05/11{' · último dia!' if n == CLOSE_N else ''}", font=font(32), fill=YEL, anchor="ls")
    else:
        teams(d, (x, 556), 27)
    return img.resize((1200, 630), Image.LANCZOS)


def story(n):
    """1080x1920: title, art, countdown; the text kept out of the top and bottom 250 px Instagram covers."""
    img, d = canvas(1080, 1920, [-200, 1100, 1280, 2100])
    logo(img, d, 540, 236, 64, "m")
    spaced(d, (540, 380), "5ª COPA BIOFUT", font(38, "SemiBold Condensed"), YEL, 8, "m")
    row(d, (540, 520), [("SUPERCOPA ", font(132), INK), ("2026", font(132), PINK)], "m")
    art(img, d, 150, 580, 780)
    if n:
        row(d, (540, 1590), [("FALTA  " if n == 1 else "FALTAM  ", font(56, "SemiBold Condensed"), MUT), (str(n), font(230), PINK),
                             (" DIA" if n == 1 else " DIAS", font(96), INK)], "m")
    else:
        row(d, (540, 1590), [("A COPA É ", font(70, "SemiBold Condensed"), MUT), ("HOJE", font(200), PINK)], "m")
    d.text((540 * S, 1662 * S), "Sábado, 21/11 · 8:30 às 14:30", font=font(48, "SemiBold Condensed"), fill=INK, anchor="ms")
    if n >= CLOSE_N:
        d.text((540 * S, 1730 * S), f"Inscrição até 05/11{' · último dia' if n == CLOSE_N else ''} · link na bio", font=font(46), fill=YEL, anchor="ms")
    else:
        teams(d, (540, 1730), 44, "m")
    return img.resize((1080, 1920), Image.LANCZOS)


if __name__ == "__main__":
    assert days_left(COPA) == 0 and days_left(COPA - timedelta(hours=1)) == 1 and days_left(COPA - timedelta(days=2)) == 2
    assert days_left(datetime(2026, 11, 5, 12, tzinfo=timezone(timedelta(hours=-3)))) == CLOSE_N
    OUT.mkdir(exist_ok=True)
    for n in range(days_left() + 1):
        render(n).save(OUT / f"copa-{n}.jpg", quality=88, optimize=True)
        story(n).save(OUT / f"story-{n}.jpg", quality=90, optimize=True)
    print(f"og: {days_left() + 1} days x 2 images in {OUT}")
