"""Link preview of /copa: one 1200x630 JPEG per day left (og/copa-<days>.jpg), so a pasted link shows today's countdown.

    python og_copa.py      # deploy.ps1 runs it; needs Pillow on this PC, not on the server

ponytail: pre-rendered per day because the server has no Pillow; a day after the last image /copa falls back to og.png.
"""
import functools
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

COPA = datetime(2026, 11, 21, 8, 30, tzinfo=timezone(timedelta(hours=-3)))  # same as COPA_DAY in index.html and server.py
OUT = Path(__file__).with_name("og")
S = 2  # drawn at 2x, then scaled down: smooth edges
W, H = 1200, 630
FONTS = Path("C:/Windows/Fonts")
GOLD, GOLD_D, GOLD_L = (255, 196, 46), (196, 120, 18), (255, 232, 140)
INK = (24, 8, 46)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size * S)


def days_left(now=None):
    return max(0, math.ceil(((COPA - (now or datetime.now(timezone.utc))).total_seconds()) / 86400))


@functools.cache
def bg():
    col = Image.new("RGB", (1, 256))
    col.putdata([tuple(int(a + (b - a) * y / 255) for a, b in zip((44, 10, 92), (10, 30, 96))) for y in range(256)])  # deep purple -> blue, like the Copa posters
    img = col.resize((W * S, H * S))
    glow = Image.new("L", img.size)
    ImageDraw.Draw(glow).ellipse([(930 - 330) * S, (300 - 300) * S, (930 + 330) * S, (300 + 300) * S], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(120 * S))
    img = Image.composite(Image.new("RGB", img.size, (255, 120, 30)), img, glow.point(lambda v: v * 0.55))
    d = ImageDraw.Draw(img)
    rnd = random.Random(2026)
    for _ in range(70):  # confetti
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(3, 7)
        if 40 < x < 640 and 30 < y < 600:  # keep the text side clean
            continue
        col = rnd.choice([(155, 225, 93), (255, 154, 31), (255, 74, 110), (255, 210, 63), (90, 200, 255)])
        a = rnd.uniform(0, math.pi)
        pts = [((x + math.cos(a + k * math.pi / 2) * r * (2 if k % 2 else 1)) * S, (y + math.sin(a + k * math.pi / 2) * r * (2 if k % 2 else 1)) * S) for k in range(4)]
        d.polygon(pts, fill=col)
    return img


def trophy(d, cx=930):
    s = lambda *v: [c * S for c in v]
    d.arc(s(cx - 190, 140, cx - 80, 280), 90, 270, fill=GOLD_D, width=22 * S)  # handles
    d.arc(s(cx + 80, 140, cx + 190, 280), -90, 90, fill=GOLD_D, width=22 * S)
    d.pieslice(s(cx - 135, -30, cx + 135, 340), 0, 180, fill=GOLD)  # bowl
    d.pieslice(s(cx - 135, -30, cx + 60, 340), 90, 180, fill=GOLD_L)  # light side
    d.pieslice(s(cx - 120, -15, cx + 120, 325), 0, 180, outline=GOLD_D, width=4 * S)
    d.ellipse(s(cx - 135, 135, cx + 135, 175), fill=GOLD_D)  # rim
    d.ellipse(s(cx - 122, 142, cx + 122, 168), fill=(120, 60, 10))
    fx, fy = cx, 245  # a fish on the cup: the group's mascots are fish (Bagres, Traíras, Piranhas)
    d.ellipse(s(fx - 55, fy - 24, fx + 35, fy + 24), fill=GOLD_D)
    d.polygon(s(fx + 25, fy, fx + 70, fy - 30, fx + 70, fy + 30), fill=GOLD_D)
    d.ellipse(s(fx - 38, fy - 9, fx - 24, fy + 5), fill=GOLD_L)
    d.polygon(s(cx - 22, 330, cx + 22, 330, cx + 36, 410, cx - 36, 410), fill=GOLD_D)  # stem
    d.ellipse(s(cx - 60, 398, cx + 60, 428), fill=GOLD)
    d.rounded_rectangle(s(cx - 95, 425, cx + 95, 480), 8 * S, fill=(70, 30, 20))  # base
    d.rounded_rectangle(s(cx - 70, 437, cx + 70, 468), 5 * S, fill=GOLD)
    d.text((cx * S, 453 * S), "2026", font=font("impact.ttf", 26), fill=INK, anchor="mm")


def ball(d, cx=1075, cy=500, r=62):
    s = lambda *v: [c * S for c in v]
    d.ellipse(s(cx - r, cy - r, cx + r, cy + r), fill=(250, 250, 250), outline=(20, 20, 20), width=4 * S)
    pent = lambda x, y, k: [((x + math.cos(math.radians(90 + 72 * i)) * k) * S, (y - math.sin(math.radians(90 + 72 * i)) * k) * S) for i in range(5)]
    d.polygon(pent(cx, cy, r * 0.36), fill=(20, 20, 20))
    for i in range(5):  # the seams to the outer pentagons
        a = math.radians(90 + 72 * i)
        x1, y1 = cx + math.cos(a) * r * 0.36, cy - math.sin(a) * r * 0.36
        x2, y2 = cx + math.cos(a) * r * 0.8, cy - math.sin(a) * r * 0.8
        d.line(s(x1, y1, x2, y2), fill=(20, 20, 20), width=4 * S)
        d.polygon(pent(cx + math.cos(a) * r * 0.95, cy - math.sin(a) * r * 0.95, r * 0.22), fill=(20, 20, 20))
    d.ellipse(s(cx - r, cy - r, cx + r, cy + r), outline=(20, 20, 20), width=4 * S)


def poster_text(d, xy, text, size, fill):
    x, y = xy
    f = font("impact.ttf", size)
    d.text(((x + 6) * S, (y + 7) * S), text, font=f, fill=(8, 2, 20))  # drop shadow
    d.text((x * S, y * S), text, font=f, fill=fill, stroke_width=6 * S, stroke_fill=INK)


def render(n):
    img = bg().copy()
    d = ImageDraw.Draw(img)
    trophy(d)
    ball(d)
    d.text((62 * S, 44 * S), "SUPERCOPA 2026 · SÁBADO 21/11 · 8:30", font=font("bahnschrift.ttf", 26), fill=(235, 225, 255))
    poster_text(d, (56, 76), "COPA", 148, (155, 225, 93))
    poster_text(d, (56, 222), "BIOFUT", 148, (255, 154, 31))
    d.rounded_rectangle([60 * S, 398 * S, 600 * S, 512 * S], 18 * S, fill=(14, 6, 34), outline=(255, 210, 63), width=3 * S)
    x = 88 * S
    for text, size, fill in ([("FALTAM", 50, (235, 225, 255)), (str(n), 96, (255, 210, 63)), ("DIA" if n == 1 else "DIAS", 50, (235, 225, 255))]
                             if n else [("É HOJE!", 80, (255, 210, 63))]):
        f = font("impact.ttf", size)
        d.text((x, 490 * S), text, font=f, fill=fill, anchor="ls")  # one baseline
        x += d.textlength(text, font=f) + 18 * S
    d.rounded_rectangle([60 * S, 530 * S, 600 * S, 586 * S], 28 * S, fill=(255, 74, 110))
    d.ellipse([78 * S, 540 * S, 114 * S, 576 * S], fill=GOLD, outline=GOLD_D, width=3 * S)  # a coin
    d.text((96 * S, 558 * S), "$", font=font("impact.ttf", 24), fill=GOLD_D, anchor="mm")
    d.text((126 * S, 558 * S), "JOGOU A COPA? GANHA 50 MOEDAS", font=font("impact.ttf", 30), fill=(255, 255, 255), anchor="lm")
    d.text((930 * S, 600 * S), "biofut.h-brain.org/copa", font=font("bahnschrift.ttf", 24), fill=(235, 225, 255), anchor="mm")
    return img.resize((W, H), Image.LANCZOS)


if __name__ == "__main__":
    assert days_left(COPA) == 0 and days_left(COPA - timedelta(hours=1)) == 1 and days_left(COPA - timedelta(days=2)) == 2
    OUT.mkdir(exist_ok=True)
    for n in range(days_left() + 1):
        render(n).save(OUT / f"copa-{n}.jpg", quality=85, optimize=True)
    print(f"og: {days_left() + 1} images in {OUT}")
