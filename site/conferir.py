"""
conferir.py - the two pictures the group checks a game against its súmula photo after it reaches the sheet
(server.py conferir): the game as the site shows it, and the rows as the sheet now has them. JPEG bytes, made with
Pillow on the server (apt python3-pil, fonts-dejavu-core); without Pillow the server posts the text and the poll only.
"""
import io

BG, CARD, LINE, TXT, DIM, ACC = "#0f0f10", "#18181b", "#2a2a2e", "#f4f4f5", "#a1a1aa", "#ff4f7b"
FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf", "C:/Windows/Fonts/arial{}.ttf")


def font(size, bold=False):
    from PIL import ImageFont
    for f in FONTS:
        try:
            return ImageFont.truetype(f.format(("-Bold" if "dejavu" in f else "bd") if bold else ""), size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def grid(title, head, rows, sub=""):
    """A dark table: title, optional subtitle, header row, one line per row. -> JPEG bytes."""
    from PIL import Image, ImageDraw
    f, fb, ft = font(26), font(26, True), font(36, True)
    rows = [[str(c) for c in r] for r in rows]
    cell = lambda t, fo: int(fo.getlength(t))
    w = [max([cell(h, fb)] + [cell(r[i], f) for r in rows]) + 36 for i, h in enumerate(head)]
    W, top, lh = max(sum(w) + 60, cell(title, ft) + 60, 720), 110 if sub else 80, 44
    im = Image.new("RGB", (W, top + lh * (len(rows) + 1) + 40), BG)
    d = ImageDraw.Draw(im)
    d.text((30, 24), title, fill=TXT, font=ft)
    if sub:
        d.text((30, 70), sub, fill=DIM, font=f)
    d.rectangle((20, top - 8, W - 20, top + lh * (len(rows) + 1) + 8), fill=CARD)
    for j, r in enumerate([head] + rows):
        y, x = top + lh * j, 30
        if j:
            d.line((24, y, W - 24, y), fill=LINE)
        for i, c in enumerate(r):
            d.text((x, y + 8), c, fill=ACC if not j else TXT, font=fb if not j else f)
            x += w[i]
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


def site(g, line):
    """The game as the site has it: [team, name, goals, assists, own goals, captain] per player."""
    pl = lambda p: (list(p) + [0] * 5)[:5]  # an old game's player can be just [name, goals]
    rows = [[t["name"], n, gl or "", a or "", o or "", "C" if c else ""] for t in g["teams"] for n, gl, a, o, c in map(pl, t["players"])]
    return grid("No site", ["Time", "Jogador", "Gols", "Assist.", "Gol contra", "Capitão"], rows, line)


def sheet_rows(rows, jogo):
    """The sheet's rows for that game: [row number, Data, Time, Nome, Gol, Assistência, Gol Contra, Capitão]."""
    return grid("Na planilha", ["Linha", "Data", "Time", "Nome", "Gol", "Assist.", "Gol contra", "Capitão"], rows,
                f"Aba DATABASE, jogo {jogo}")


if __name__ == "__main__":
    g = {"teams": [{"name": "Pavões", "players": [["Zé", 2, 0, 0, 1], ["Rui", 0, 1, 0, 0]]},
                   {"name": "Bagres", "players": [["Ana", 1, 0, 1, 0]]}]}
    a, b = site(g, "#1001 2026-10-22 Pavões 2x1 Bagres"), sheet_rows([[4899, "22/10/26", "Pavões", "Zé", 2, "", "", 1]], 301)
    assert a[:2] == b[:2] == b"\xff\xd8" and len(a) > 5000, len(a)
    print("conferir ok", len(a), len(b))
