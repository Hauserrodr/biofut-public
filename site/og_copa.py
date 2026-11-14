"""The SuperCopa countdown, one image per day left: og/copa-<days>.jpg (1200x630: /copa's link preview and the bot's noon
post in the group) and og/story-<days>.jpg (1080x1920 Instagram story).

    python og_copa.py      # deploy.ps1 runs it; needs Pillow on this PC, not on the server

The event's own look, same as the #/copa page (.sc26 in index.html): white ground, Matte's ribbons and logo
(copa_rib_*.webp, copa_logo.webp; the story frame copa_story_ribbons.webp is cut 1:1 from his vertical poster),
Holtwood One SC for the small spaced labels, Saira Semi Condensed for the countdown, dates and team names (fonts/, OFL).
Up to 05/11 the sign-up deadline, after it the four teams in their shirt colours.
ponytail: pre-rendered per day because the server has no Pillow; a day after the last image /copa falls back to og.png.
"""
import functools
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COPA = datetime(2026, 11, 21, 8, 30, tzinfo=timezone(timedelta(hours=-3)))  # same as COPA_DAY in index.html and server.py
CLOSE_N = 16  # days left on 05/11, the form's last day (server.py COPA_CLOSE)
HERE = Path(__file__).parent
OUT = HERE / "og"
FONTS = HERE / "fonts"
S = 2  # drawn at 2x, then scaled down: smooth edges
BG, INK, DIM, LINE = (255, 255, 255), (10, 10, 10), (118, 113, 113), (214, 210, 210)  # .sc26 --bg --ink --dim --line2
INDIGO = (32, 32, 112)
TEAMS = [("Pavões", (34, 38, 118)), ("Bagres", (0, 155, 60)), ("Babuínos", (5, 44, 65)), ("Axolotes", (221, 2, 140))]  # .sc-team gradients' mid stop
WHEN, HOURS = "SÁBADO, 21.11.2026", "8:30 ÀS 14:30"


@functools.cache
def font(size, kind="sai800"):
    """sai600 / sai700 / sai800 = Saira Semi Condensed, eng = Holtwood One SC; Bahnschrift if fonts/ lacks the file."""
    name = {"sai600": "SairaSemiCondensed-SemiBold", "sai700": "SairaSemiCondensed-Bold",
            "sai800": "SairaSemiCondensed-ExtraBold", "eng": "HoltwoodOneSC-Regular"}[kind]
    try:
        return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size * S)
    except OSError:
        f = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", size * S)
        f.set_variation_by_name("Bold Condensed" if kind != "sai600" else "SemiBold Condensed")
        return f


def days_left(now=None):
    return max(0, math.ceil(((COPA - (now or datetime.now(timezone.utc))).total_seconds()) / 86400))


def width(d, text, f, track=0):
    return sum(d.textlength(c, font=f) for c in text) + track * S * (len(text) - 1) if track else d.textlength(text, font=f)


def spaced(d, xy, text, f, fill, track=0, anchor="l"):
    """Text on a baseline (track = letter spacing in px); anchor l / m / r on x."""
    w = width(d, text, f, track)
    x = xy[0] * S - {"l": 0, "m": w / 2, "r": w}[anchor]
    if not track:
        d.text((x, xy[1] * S), text, font=f, fill=fill, anchor="ls")
        return
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
    f, dot = font(size, "sai800"), font(size, "sai600")
    parts = []
    for i, (t, c) in enumerate(TEAMS):
        parts += [(t.upper(), f, c)] + ([("  ·  ", dot, LINE)] if i < 3 else [])
    row(d, xy, parts, anchor)


def paste(img, name, x, y, h=None, w=None, flip=False):
    """One of Matte's cuts at height h (or width w), top-left at (x, y); only ever scaled down."""
    a = Image.open(HERE / name).convert("RGBA")
    k = (h / a.height) if h else (w / a.width)
    assert k <= 1.001, f"{name} would be upscaled"
    a = a.resize((round(a.width * k * S), round(a.height * k * S)), Image.LANCZOS)
    if flip:
        a = a.transpose(Image.FLIP_LEFT_RIGHT)
    img.paste(a, (round(x * S), round(y * S)), a)
    return a.width / S, a.height / S


def countdown(d, x, base, n, big, unit, label, anchor="l"):
    """FALTAM (engraved) over the day number and DIAS; HOJE on the day. Returns the block's width."""
    if n:
        num, word = str(n), "DIA" if n == 1 else "DIAS"
        fb, fu = font(round(big * (0.86 if n > 9 else 1))), font(unit)  # two digits a bit smaller: the row keeps its width
        gap = big * 0.06 * S
        w = d.textlength(num, font=fb) + gap + d.textlength(word, font=fu)
        x0 = x * S - (w / 2 if anchor == "m" else 0)
        d.text((x0, base * S), num, font=fb, fill=INK, anchor="ls")
        ux = x0 + d.textlength(num, font=fb) + gap
        d.text((ux, base * S), word, font=fu, fill=INK, anchor="ls")
        spaced(d, (ux / S + 2, base - unit * 0.98), "FALTA" if n == 1 else "FALTAM", font(label, "eng"), DIM, label * 0.22)
    else:
        f = font(round(big * 0.62))
        w = d.textlength("HOJE", font=f)
        x0 = x * S - (w / 2 if anchor == "m" else 0)
        spaced(d, (x if anchor == "m" else x0 / S + 4, base - big * 0.62 * 0.74 - label * 0.9), "A COPA É", font(label, "eng"), DIM,
               label * 0.22, anchor)
        d.text((x0, base * S), "HOJE", font=f, fill=INK, anchor="ls")
    return w / S


def render(n):
    """1200x630: Matte's logo on the left, the countdown on the right, his ribbons in the corners."""
    img = Image.new("RGB", (1200 * S, 630 * S), BG)
    d = ImageDraw.Draw(img)
    paste(img, "copa_rib_teal.webp", 0, 0, h=200)
    paste(img, "copa_rib_indigo.webp", 0, 630 - 96, h=96)
    paste(img, "copa_rib_magenta.webp", 1200 - 132, -40, h=300)
    paste(img, "copa_rib_green.webp", 1200 - 175, 630 - 146, h=146)
    paste(img, "copa_logo.webp", 150, 104, h=440)
    x = 588
    d.line([(x - 40) * S, 150 * S, (x - 40) * S, 500 * S], fill=LINE, width=2 * S)
    countdown(d, x, 392, n, 300, 120, 24)
    spaced(d, (x + 2, 452), WHEN, font(40, "sai800"), INK, 0.5)
    spaced(d, (x + 2, 492), HOURS, font(30, "sai700"), DIM, 1.2)
    if n >= CLOSE_N:
        spaced(d, (x + 2, 552), f"INSCRIÇÃO ATÉ 05/11{' · ÚLTIMO DIA!' if n == CLOSE_N else ''}", font(30, "sai800"), INDIGO, 0.6)
    else:
        teams(d, (x + 2, 552), 27)
    return img.resize((1200, 630), Image.LANCZOS)


def story(n):
    """1080x1920 after Matte's vertical poster: countdown on top, the logo, then the teams; text kept out of the top and
    bottom 250 px Instagram covers."""
    img = Image.new("RGB", (1080 * S, 1920 * S), BG)
    img.paste(Image.open(HERE / "copa_story_ribbons.webp").convert("RGB").resize(img.size, Image.LANCZOS))
    d = ImageDraw.Draw(img)
    countdown(d, 540, 640, n, 400, 150, 34, "m")
    spaced(d, (540, 742), WHEN, font(64, "sai800"), INK, 1, "m")
    spaced(d, (540, 800), HOURS, font(44, "sai700"), DIM, 2, "m")
    paste(img, "copa_logo.webp", 540 - 210, 880, h=500)
    if n >= CLOSE_N:
        spaced(d, (540, 1560), "INSCRIÇÃO ATÉ 05/11", font(66, "sai800"), INK, 1, "m")
        spaced(d, (540, 1622), "ÚLTIMO DIA · LINK NA BIO" if n == CLOSE_N else "LINK NA BIO", font(44, "sai700"), DIM, 2, "m")
    else:
        for i, (t, c) in enumerate(TEAMS):
            spaced(d, (510 + 60 * (i % 2), 1540 + 96 * (i // 2)), t.upper(), font(70, "sai800"), c, 1, "rl"[i % 2])
    return img.resize((1080, 1920), Image.LANCZOS)


if __name__ == "__main__":
    assert days_left(COPA) == 0 and days_left(COPA - timedelta(hours=1)) == 1 and days_left(COPA - timedelta(days=2)) == 2
    assert days_left(datetime(2026, 11, 5, 12, tzinfo=timezone(timedelta(hours=-3)))) == CLOSE_N
    OUT.mkdir(exist_ok=True)
    for n in range(days_left() + 1):
        render(n).save(OUT / f"copa-{n}.jpg", quality=88, optimize=True)
        story(n).save(OUT / f"story-{n}.jpg", quality=90, optimize=True)
    print(f"og: {days_left() + 1} days x 2 images in {OUT}")
