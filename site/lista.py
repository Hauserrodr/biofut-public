"""The group's weekly sign-up list as text -> {date, goalies, players, waiting, ...}. The server reads every list the bot
forwards (Jogo da semana fills itself); listas.py reads the whole chat history with it.

Vendored from the chat miner (BDSMA/whatsapp/mine_lists.py: fold, parse_entry, parse_list) so the server needs no chat
checkout. Usage: python lista.py  (selftest)
"""
import datetime as dt, re, unicodedata

RESET = 3  # a repost that drops more names than this at once is a reset or a truncated copy, not drop-outs
HEADER = re.compile(r'\[\s*(?:QUINTA|SEGUNDA|TER[ÇC]A|QUARTA|SEXTA|S[ÁA]BADO|DOMINGO)?[^\]\d]{0,12}(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?[^\]]*\]', re.I)
SLOT = re.compile(r'^\s*\*?(goleiro\s*\d|gk\s*\d|\d{1,2})\s*\*?\s*[-–.:)]\s*(.*)$', re.I)
TICK = re.compile(r'[✅✔☑️✔️🟢👍]+')
CAPTAIN = re.compile(r'\(\s*c\s*\)|\bcap(?:it[ãa]o)?\b', re.I)
TEAM = re.compile(r'^\W*time\b\s*(.*)$', re.I)  # 'Time Regio', '*TIME DROP SHADOW RAFA* ⚫'
STATS = re.compile(r'\b(\d{1,2})\s*(gc|g|a)\b', re.I)  # '2G 1A', '1 GC' (gol contra)
SECTION = {'supl': 'waiting', 'corneta': 'corneta', 'sombra': 'guests', 'convidad': 'guests'}


def fold(s):
    """Key for comparing names: no accents, lowercase, single spaces."""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 .]', ' ', s)).strip()


def parse_entry(raw):
    """'Daniel (C) ✅' -> {'name': 'Daniel', 'captain': True, 'confirmed': True, 'note': ''}"""
    s = raw.strip().strip('*_~ ')
    confirmed = bool(TICK.search(s))
    s = TICK.sub('', s)
    captain = bool(CAPTAIN.search(s))
    s = CAPTAIN.sub('', s)
    notes = re.findall(r'\(([^)]*)\)', s)
    s = re.sub(r'\([^)]*\)', '', s)
    stats = {k.lower(): int(n) for n, k in STATS.findall(s)}  # post-game teams: 'Kalu: 3G 2A'
    s = STATS.sub('', s)
    s = re.sub(r'[^\w\s.\'-]', '', s).strip(' .-')  # emoji and stray symbols
    if not s or len(s) > 30:
        return None
    e = {'name': s, 'captain': captain, 'confirmed': confirmed, 'note': '; '.join(n.strip() for n in notes if n.strip())}
    if stats:
        e.update(goals=stats.get('g', 0), assists=stats.get('a', 0), own_goals=stats.get('gc', 0))
    return e


def parse_list(text, ts):
    """Return a parsed list or None if the message isn't a sign-up list."""
    h = HEADER.search(text[:200])
    lines = text.splitlines()
    if not h or (sum(1 for l in lines if SLOT.match(l)) < 6 and sum(1 for l in lines if TEAM.match(l)) < 2):
        return None
    d, mo, y = int(h.group(1)), int(h.group(2)), h.group(3)
    sent = dt.datetime.fromtimestamp(ts)
    if y:
        year = int(y) + (2000 if len(y) == 2 else 0)
    else:  # lists are posted days before the game; around New Year the game is next year
        year = sent.year + (1 if mo < sent.month - 6 else 0) - (1 if mo > sent.month + 6 else 0)
    try:
        date = dt.date(year, mo, d)
    except ValueError:
        return None
    hm = re.search(r'(\d{1,2})\s*[:h]\s*(\d{2})', text[h.end(3) if y else h.end(2):h.end()])
    out = {'date': date.isoformat(), 'goalies': [], 'players': [], 'waiting': [], 'guests': [], 'corneta': [], 'teams': [],
           'season': '', 'price': '', 'court': '',
           'hora': f'{int(hm.group(1)):02d}:{hm.group(2)}' if hm and int(hm.group(1)) < 24 and int(hm.group(2)) < 60 else ''}
    for l in text.splitlines()[:12]:
        if '🏆' in l: out['season'] = re.sub(r'[*🏆]', '', l).strip()
        if '💰' in l: out['price'] = re.sub(r'[*💰]', '', l).strip()
        if re.match(r'^\s*quadra\s*\d', l, re.I): out['court'] = l.strip()
    section = 'players'
    for l in text.splitlines():
        low = fold(l)
        t = TEAM.match(l)
        if t and not SLOT.match(l):
            section, bare = 'team', True  # 22/10: bare names under 'Time MK', up to the first blank line after them
            out['teams'].append({'name': re.sub(r"[^\w\s.'-]", '', t.group(1)).strip(), 'players': []})
            continue
        hit = next((v for k, v in SECTION.items() if low.startswith(k) or low.startswith('* ' + k)), None)
        if hit and not SLOT.match(l):
            section = hit
            rest = l.split(':', 1)[1] if ':' in l else ''
            e = parse_entry(rest) if rest.strip() else None
            if e: out[section].append(e)
            continue
        m = SLOT.match(l)
        if m:
            e = parse_entry(m.group(2))
            if e and section == 'team':
                out['teams'][-1]['players'].append(e)
            elif e:
                (out['goalies'] if re.match(r'goleiro|gk', m.group(1), re.I) else out[section]).append(e)
        elif section == 'team' and (re.match(r'^\s*[-•]\s*\S', l) or bare and low not in ('', 'x', 'vs')):
            e = parse_entry(re.sub(r'^\s*[-•]', '', l))
            if e: out['teams'][-1]['players'].append(e)
        elif section == 'team' and not l.strip() and out['teams'][-1]['players']:
            bare = False  # the team is over: a closing 'bom jogo' is not a player
        elif section in ('waiting', 'corneta', 'guests') and re.match(r'^\s*[-•]\s*\S', l):
            e = parse_entry(l.strip()[1:])
            if e: out[section].append(e)
    out['teams'] = [t for t in out['teams'] if t['players']]
    return out


def selftest():  # made-up names
    t = ('🚨 [QUINTA - 19/03 18:30]🚨\n🌍 Quadra Central\n💰 12 pilas\n🏆 Temporada 26/1\n\nQuadra 4\n\n'
         'Goleiro 1 - Zeca\nGoleiro 2 -\n\n1 - Tito ✅\n2 - Beto (a principio)\n3 - Juca (c)\n4 - Lalo\n'
         '5 - Nino\n6 - Otto\n7 -\n\nSuplência:\n - Vavá\n -\n\nCorneta:\n- Dodô\n')
    p = parse_list(t, dt.datetime(2026, 3, 16, 20, 50).timestamp())
    assert p['date'] == '2026-03-19', p['date']
    assert [e['name'] for e in p['goalies']] == ['Zeca']
    assert [e['name'] for e in p['players']] == ['Tito', 'Beto', 'Juca', 'Lalo', 'Nino', 'Otto'], p['players']
    assert p['players'][0]['confirmed'] and p['players'][2]['captain'] and p['players'][1]['note'] == 'a principio'
    assert parse_entry('⁠Kiko: 3G 2A') == {'name': 'Kiko', 'captain': False, 'confirmed': False, 'note': '',
                                         'goals': 3, 'assists': 2, 'own_goals': 0}
    assert [e['name'] for e in p['waiting']] == ['Vavá'] and [e['name'] for e in p['corneta']] == ['Dodô']
    assert p['season'] == 'Temporada 26/1' and p['court'] == 'Quadra 4'
    assert parse_list(t.replace('19/03', '02/01'), dt.datetime(2025, 12, 30).timestamp())['date'] == '2026-01-02'  # New Year
    k = parse_list('[QUINTA - 22/10 18:30]\nTime MK\nTuca\nBino (C) ✅\n- Caco\nx\nTime Nego Dei ⚫\nDuda\nFefo (c)\n\nBom jogo a todos',
                   dt.datetime(2026, 10, 21).timestamp())  # 22/10: bare names under the team headers
    assert [(g['name'], [e['name'] for e in g['players']]) for g in k['teams']] == [
        ('MK', ['Tuca', 'Bino', 'Caco']), ('Nego Dei', ['Duda', 'Fefo'])], k['teams']
    assert k['teams'][0]['players'][1]['captain'] and k['teams'][1]['players'][1]['captain'] and not k['players']
    o = parse_list(t + '\nTime Azul\n- Tito\n- Zeca\nTime Verde\n- Lalo\n- Otto: 2G\n', dt.datetime(2026, 3, 16).timestamp())
    assert [[e['name'] for e in g['players']] for g in o['teams']] == [['Tito', 'Zeca'], ['Lalo', 'Otto']] and o['players'] == p['players']
    assert parse_list('oi\n1 - a\n2 - b', 0) is None and fold(' Vavá  Jr ') == 'vava jr'
    print('selftest ok')


if __name__ == '__main__':
    selftest()
