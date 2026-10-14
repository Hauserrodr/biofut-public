"""Phone -> name registry for the login, /transparencia "Quem é você?" and the people review in /admin. No phone numbers.

Every number in the chat (and every saved-contact sender of Gab's export, which shows names, not numbers) gets the name
it plays under on the tabela:
  nome        its WhatsApp name fits a tabela name past the first name ("Leonardo Saul" -> Leo Saul, "Lucas Adriano
              Pachla" -> Pachla). Push names come read-only from the ingest DB (BIOFUT_WADB), contact names from the export;
  lista       else the tabela name it signs itself up as (a list repost adding exactly one name is a vote, as in
              mine_lists), else the chat miner's pick (derived/people.json);
  nome        else a first-name fit on its WhatsApp name ("Daniel Campos" -> Dan);
  frequencia  else the miner's guess from sign-up dates (Jaccard);
  contato     numbers no list knows: a contact card someone shared in the group, as before.
Keeps only a salted PBKDF2 hash of each number's last 8 digits, a fresh salt every build. Also writes, for the site:
  me        the export owner's tabela name (Gab: his own messages carry no number; the server gives it to BIOFUT_ADMIN_PHONE);
  alias     other spellings -> the main one: same letters ("GUih"), or one number signing up as one name on a day the
            tabela wrote another ("felipe" -> Felipe on 2024-06-06 -> Felipe P.). Never two names that played together;
  suggest   maybe one person, for the staff to confirm in /admin: a lone surname (Fischer 2019-20, Lucas Fischer 2022-);
  switches  one person, two numbers: name, last 4 digits, date (the group's "mudou de número" notice when there is one);
  dubious   a name someone else put on a list that could be several people, or nobody we know (a guest goes as "Sombra"):
            {id, date, name, wrote, by, options}; the one who added it answers on /#/eu, the staff on /admin.
Also derived/senders.json in the chat folder (export sender -> name, for the wiki) and data/mensagens.json: each member's own texts in the group (no sign-up lists, no media), which the site shows only
to that member on #/eu. Both are gitignored; deploy.ps1 uploads them.
Usage: python phones.py [--selftest]   (imports server.py for the hash: set BIOFUT_DATA if ./biofut.json is missing)
"""
import collections, datetime as dt, glob, json, os, re, secrets, sqlite3, sys, unicodedata, urllib.request, zipfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from server import phone_key  # noqa: E402  same hash on both ends

CHAT = os.environ.get('BIOFUT_CHAT', 'D:/dev/BDSMA/whatsapp')
WADB = os.environ.get('BIOFUT_WADB', os.path.expanduser('~/.whatsapp-secrets/whatsapp.db'))  # opened read-only; optional
SITE = os.environ.get('BIOFUT_SITE', 'https://biofut.h-brain.org')  # its /api/data: the approved tabela
OUT = os.path.join(HERE, 'data', 'phones.json')
MSGS = os.path.join(HERE, 'data', 'mensagens.json')
SENDERS = os.path.join(CHAT, 'derived', 'senders.json')  # export sender -> name, for wiki.names(); chat data stays out of git
FIX = os.path.join(CHAT, 'derived', 'ident_fix.json')  # {key: tabela name}: numbers the list votes get wrong, checked by hand
HIDDEN = re.compile(r'^(<[^>]*>|\[\w+\]|\.|null|mensagem apagada|esta mensagem foi apagada|voc[eê] apagou esta mensagem)$|arquivo anexado\)$', re.I)
GUEST = 'Sombra'  # the tabela's own word for a guest from outside the group: plays, never counts
SMALLCAPS = {c: n[-1].lower() for c in range(0x10000)  # "Gᴀʙʀɪᴇʟ": NFKD leaves small capitals alone
             if (n := unicodedata.name(chr(c), '')).startswith('LATIN LETTER SMALL CAPITAL ') and len(n) == 28}


def fold(s):
    s = unicodedata.normalize('NFKD', (s or '').translate(SMALLCAPS)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def fit(x, n, loose=True):
    """How well tabela word x fits name word n: 4 same, 3 prefix (leo/leonardo), 2 same first 3 letters (gabi/gabriel;
    only when loose, which place() allows on first names only: Silas is not "Fernando Silveira"), 1 initial (p/poletti)."""
    if n == x:
        return 4
    if len(x) >= 3 and n.startswith(x):
        return 3
    if loose and len(x) >= 3 and len(n) >= 3 and x[:3] == n[:3]:
        return 2
    return 1 if len(x) == 1 and n[0] == x else 0


def place(name, names, loose=True):
    """-> (the tabela name someone called `name` plays as, whether it fit past their first name), or (None, False) when
    nothing fits or two fit equally. Every word of a tabela name must fit a word of the name; then more real words (not
    initials) win, then the surname, then the closer spelling: "Lucas Adriano Pachla" is Pachla, not Lucas P."""
    w = fold(name).split()
    ranked = []
    for t in set(names):
        fits = [max((fit(x, n, loose and not i), i) for i, n in enumerate(w)) for x in fold(t).split()] if w else []
        if fits and all(f for f, _ in fits):
            score = (sum(f > 1 for f, _ in fits), any(f > 1 and i == len(w) - 1 for f, i in fits), sum(f for f, _ in fits))
            ranked.append((score, any(i for _, i in fits), t))
    ranked.sort(reverse=True)
    if not ranked or len(ranked) > 1 and ranked[1][0] == ranked[0][0]:
        return None, False
    return ranked[0][2], ranked[0][1]


def on_roster(n, roster):
    """The tabela name a list name stands for on that day: one that fits it, else the only one it fits into
    ("fischer" -> Lucas Fischer), and not just loosely ("andriel" is not Andrei; "rafa" with Rafael M and Rafo -> None)."""
    t = place(n, roster, loose=False)[0]
    if t:
        return t
    inside = [r for r in roster if place(r, [n])[0]]
    return inside[0] if len(inside) == 1 and place(inside[0], [n], loose=False)[0] else None


def who(push, own, miner, guessed, tab):
    """One sender -> (tabela name, how), in the order of the docstring."""
    t, past_first = place(push, tab)
    if past_first:
        return t, 'nome'
    if own:
        return own, 'lista'
    if miner in tab and not guessed:
        return miner, 'lista'
    if t:
        return t, 'nome'
    return (miner, 'frequencia' if guessed else 'lista') if miner else (None, None)


def own_name(c):
    """The tabela name a sender signs themself up as: c counts what their list adds stood for on that day's tabela
    ("marcelo" -> Marcelo RP in 2023, Marcelo Prof. in 2026); the top one, if 2+ times and 20%+."""
    t, k = (c.most_common(1) or [(None, 0)])[0]
    return t if k >= 2 and k >= 0.2 * sum(c.values()) else None


def list_adds(msgs, parse_list, names):
    """(date, sender, list name) for each list repost that adds exactly one name and drops none, up to game day: the chat
    miner's identity votes (mine_lists.mine), kept with their date."""
    by = collections.defaultdict(list)
    for m in msgs:
        t = m.get('text') or ''
        p = t.count('\n') >= 6 and m.get('sender_name') != 'Meta AI' and parse_list(t, m['ts'])
        if p:
            by[p['date']].append((m['ts'], m.get('sender_name') or m.get('sender') or '?', names(p)))
    out = []
    for date, vs in sorted(by.items()):
        end = dt.datetime.fromisoformat(date).replace(hour=23, minute=59).timestamp()
        vs = sorted((v for v in vs if v[0] <= end), key=lambda v: v[0])
        for (_, _, a), (_, s, b) in zip(vs, vs[1:]):
            new = b - a
            if len(new) == 1 and not a - b:
                n = next(iter(new))
                if 'sombra' not in n and len(n) > 1:
                    out.append((date, s, n))
    return out


def resolve(games, adds, push, miner):
    """games: the tabela ([{date, teams: [{players: [[name, ...]]}]}]); adds: [(date, key, list name)], senders already
    keyed (last 8 digits, 'me' or a contact name); push: {key: WhatsApp name}; miner: {key: (name, guessed)}.
    -> {ident: {key: (name, how)}, alias, suggest, dubious, known: {folded name: tabela name}}"""
    roster, count = collections.defaultdict(set), collections.Counter()
    for g in games:
        ns = [p[0] for t in g['teams'] for p in t['players']]
        roster[g.get('date')].update(ns)
        count.update(ns)
    byfold = {}
    for t in sorted(count, key=lambda t: (-count[t], t)):
        byfold.setdefault(fold(t), t)  # same letters: the most used spelling
    alias = {t: byfold[fold(t)] for t in count if byfold[fold(t)] != t}
    tab = set(byfold.values())
    canon = lambda t: alias.get(t, t)
    together, dates = collections.defaultdict(set), collections.defaultdict(set)

    def played_together():
        together.clear(), dates.clear()
        for g in games:
            ns = {canon(p[0]) for t in g['teams'] for p in t['players']}
            for n in ns:
                together[n] |= ns - {n}
                dates[n].add(g.get('date')) if g.get('date') else None
    played_together()

    def near(t, d, before=365, after=365):  # someone played as t from `before` days before d to `after` days after
        ds, day = dates.get(t), dt.date.fromisoformat(d)
        return bool(ds) and min(ds) <= str(day + dt.timedelta(after)) and max(ds) >= str(day - dt.timedelta(before))
    hits = [(d, k, n, on_roster(n, roster[d])) for d, k, n in adds]  # the tabela name each list add stood for that day
    votes, own = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for d, k, n, t in hits:
        votes[k][n] += 1
        t = byfold[fold(t)] if t else byfold.get(fold(n))  # not on that day's tabela: the name itself, if played that year
        if t and near(t, d):
            own[k][t] += 1
    ident = {}
    for k in set(push) | set(miner) | set(votes):
        m, guessed = miner.get(k, (None, False))
        ident[k] = who(push.get(k) or ('' if k.isdigit() else k), own_name(own[k]), byfold.get(fold(m), m), guessed, tab)
    idents = {a for a, _ in ident.values()}
    seen = collections.defaultdict(lambda: collections.defaultdict(set))
    for d, k, n, t in hits:
        if t and votes[k][n] >= 3 and votes[k][n] >= 0.1 * sum(votes[k].values()):
            seen[k][canon(t)].add(d)
    for k, ts in seen.items():  # one number, one person: the names it signed itself up as are spellings of its name
        a = ident[k][0]
        for t, ds in ts.items() if a in ts else ():  # that explain half of that name's games, not one day of it,
            if t != a and t not in idents | set(alias) and a not in together[t] and 2 * len(ds) >= len(dates[t]):
                alias[t] = a  # and that no other number plays as
    for t in list(alias):
        for _ in range(5):  # ponytail: follow short chains; a cycle just stops
            alias[t] = alias.get(alias[t], alias[t])
    played_together()
    tab = {t for t in tab if t not in alias}
    ident = {k: (canon(n) if n else n, h) for k, (n, h) in ident.items()}

    suggest = sorted([a, b] for a in tab for b in tab  # a lone surname and a full name that never played together
                     if len(fold(a).split()) == 1 and len(fold(a)) >= 4 and len(fold(b).split()) > 1
                     and fold(b).split()[-1] == fold(a) and b not in together[a])
    names = collections.defaultdict(set)  # tabela name -> the WhatsApp names of whoever plays as it
    for k, (a, _) in ident.items():
        if a:
            names[a].add(push.get(k) or a)
    dubious = {}
    for d, k, n, r in hits:
        by = ident[k][0]
        if not by or not r or canon(r) == by or 'sombra' in fold(r):
            continue
        r, here = canon(r), {canon(x) for x in roster[d]}
        options = {t for t in tab if t not in here and near(t, d, after=30)
                   and any(place(x, [n])[0] for x in names.get(t, set()) | {t})} | {r}
        if place(by, [n], loose=False)[0]:  # "fabricio" by Fabricio: maybe themself, as the tabela spelled it that day
            options.add(by)
            if r not in names and by not in together[r] and [r, by] not in suggest:
                suggest.append([r, by])  # no number plays as r: one person, two spellings? (the staff decides)
        elif votes[k][n] < 3 or votes[k][n] < 0.1 * sum(votes[k].values()):
            options.discard(by)  # the adder, only if it is a name they sign themself up as ("bruno" by "bruney": a friend)
        if len(options) > 1 or r not in names:
            iid = f'{d}:{fold(r)}'
            dubious.setdefault(iid, {'id': iid, 'date': d, 'name': r, 'wrote': n, 'by': by, 'options': [r] + sorted(options - {r}) + [GUEST]})
    known = {fold(t): t for t in tab}
    for k, (a, _) in ident.items():
        if a and push.get(k):
            known.setdefault(fold(push[k]), a)
    return {'ident': ident, 'alias': alias, 'suggest': suggest, 'known': known,
            'dubious': sorted(dubious.values(), key=lambda x: (x['date'], x['name']), reverse=True)}


def contacts(ident, push, keys):
    """A saved contact (Gab's export names senders since 2026-08-20) whose name is some number's WhatsApp name is that
    number: "Gabriel Simões" is 8991's Perdigao, not a first-name fit to Gabriel. Changes ident in place."""
    by_push = {v: k for k, v in push.items() if k.isdigit() and (ident.get(k) or (None,))[0]}
    for k in keys:
        if not k.isdigit() and k != 'me' and k in by_push:
            ident[k] = (ident[by_push[k]][0], 'nome')


def switches(ident, spans, notices=None):
    """One person, two numbers in a row -> [{name, old, new, date, at_once}], last 4 digits only. at_once: both numbers
    wrote for 30+ days at the same time, so maybe two people under one name."""
    by = collections.defaultdict(list)
    for k, (n, _) in ident.items():
        if n and k.isdigit() and k in spans:
            by[n].append(k)
    out = []
    for n, ks in sorted(by.items()):
        ks.sort(key=lambda k: spans[k][0])
        for a, b in zip(ks, ks[1:]):
            day = (notices or {}).get(a) or dt.date.fromtimestamp(spans[b][0]).isoformat()
            out.append({'name': n, 'old': a[-4:], 'new': b[-4:], 'date': day,
                        'at_once': a not in (notices or {}) and spans[a][1] - spans[b][0] > 30 * 86400})
    return out


def cards(vcfs):
    """vCard texts -> {phone digits: card name}, dropping names that several numbers share."""
    out, owners = {}, collections.defaultdict(set)
    for s in vcfs:
        fn = re.search(r'^FN:(.*)$', s, re.M)
        for w in re.findall(r'waid=(\d+)', s):
            if fn and re.search(r'[^\W\d_]{2}', fn.group(1)):  # a name, not "972"
                out.setdefault(w, fn.group(1).strip())
                owners[fold(fn.group(1))].add(w)
    return {w: n for w, n in out.items() if len(owners[fold(n)]) == 1}


def build(ident, salt, known, card_map=None, posted=()):
    """-> ({hash: name}, {hash: how}, count of cards nobody vouches for)."""
    names, how = {}, {}
    for k, (n, h) in ident.items():
        hk = phone_key(k, salt) if k.isdigit() else None
        if n and hk:
            names[hk], how[hk] = n, h
    skipped = 0
    for w, fn in (card_map or {}).items():
        k = phone_key(w, salt)
        if not k or k in names:
            continue  # the lists already speak for this number
        words = {known[t] for t in fold(fn).split() if len(t) >= 4 and t in known}
        n = known.get(fold(fn)) or (words.pop() if len(words) == 1 else None) or (fn if w in posted else None)
        if n:
            names[k], how[k] = n, 'contato'
        else:
            skipped += 1
    return names, how, skipped


def selftest():
    tab = ['Pachla', 'Lucas P.', 'Felipe', 'Felipe P.', 'Gabi Steinhaus', 'Gabriel', 'Leo Saul', 'Leonardo', 'Matte', 'Dan',
           'Bruno', 'Bruno M', 'Marcelo', 'Marcel', 'Felps', 'Guih', 'Guilherme', 'Victor', 'Victor Hugo']
    for name, want in [('Lucas Adriano Pachla', ('Pachla', True)), ('Lucas Poletti', ('Lucas P.', True)),
                       ('Felipe Poletti', ('Felipe P.', True)), ('Gᴀʙʀɪᴇʟ Sᴛᴇɪɴʜᴀᴜsᴇʀ', ('Gabi Steinhaus', True)),
                       ('Leonardo Saul', ('Leo Saul', True)), ('Gabriel Matte', ('Matte', True)), ('Daniel Campos', ('Dan', False)),
                       ('Bruno Maschmann', ('Bruno M', True)), ('Fillipe Silva', (None, False)), ('Marcelo', ('Marcelo', False)),
                       ('Victor Hugo Bartosiak', ('Victor Hugo', True)), ('Guilherme Rodrigues', ('Guilherme', False))]:
        assert place(name, tab) == want, (name, place(name, tab))
    assert on_roster('fischer', ['Lucas Fischer', 'Dan']) == 'Lucas Fischer' and on_roster('gab', ['Gabriel', 'Gabi Steinhaus']) is None
    assert on_roster('rafa', ['Rafael M', 'Rafo']) is None and on_roster('andriel', ['Andrei']) is None
    assert who('Guilherme Rodrigues', 'Guih', None, False, set(tab)) == ('Guih', 'lista')  # first name only: the lists win
    assert who('Daniel Campos', None, 'Barp', True, set(tab) | {'Barp'}) == ('Dan', 'nome')  # beats a date guess
    assert who('Leonardo Saul', 'Victor', 'Victor', False, set(tab)) == ('Leo Saul', 'nome')  # adds his friend Victor a lot
    assert own_name(collections.Counter(Felps=28, Gabriel=3)) == 'Felps' and own_name(collections.Counter(Pedro=1)) is None
    assert own_name(collections.Counter(dict.fromkeys(['Victor', 'Andrei', 'Matte', 'Dan', 'Edu', 'Rafo'], 3))) is None  # adds friends

    G = lambda d, *ns: {'date': d, 'teams': [{'players': [[n, 0, 0] for n in ns]}]}
    games = [G('2019-05-27', 'Fischer', 'Bruno'), G('2019-06-03', 'Fabricio'), G('2022-01-31', 'Lucas Fischer', 'Guih', 'Guih'),
             G('2024-06-06', 'Felipe', 'Victor', 'Leo Saul', 'Gabi Steinhaus'), G('2024-08-15', 'Felipe P.', 'Victor', 'Leo Saul', 'Gabriel', 'Hanauer'),
             G('2024-08-22', 'Felipe P.', 'GUih', 'Matte', 'Hanauer', 'Jesus Cristo', 'Fabricio Santos'), G(None, 'Sombra')]
    push = {'11110000': 'Felipe Poletti', '22220000': 'Leonardo Saul', '33330000': 'Victor Vianna', '44440000': 'Arthur Hanauer',
            '55550000': 'Gabriel Matte', 'me': 'Gᴀʙʀɪᴇʟ Sᴛᴇɪɴʜᴀᴜsᴇʀ', '66660000': 'Victor V', '77770000': 'Fabricio'}
    adds = [(d, '11110000', 'felipe') for d in ('2024-06-06', '2024-08-15', '2024-08-22')] + \
           [(d, '22220000', 'victor') for d in ('2024-06-06', '2024-08-15', '2024-08-15')] + \
           [('2024-08-15', '44440000', 'gabriel'), ('2024-08-22', '44440000', 'jesus cristo'), ('2024-08-22', '44440000', 'hanauer'),
            ('2024-08-22', '77770000', 'fabricio')]
    r = resolve(games, adds, push, {'me': ('Gabi Steinhaus', True)})
    assert r['ident']['11110000'] == ('Felipe P.', 'nome') and r['ident']['me'] == ('Gabi Steinhaus', 'nome'), r['ident']
    assert r['alias'] == {'GUih': 'Guih', 'Felipe': 'Felipe P.'}, r['alias']  # Leo Saul adding Victor merges nothing
    assert r['suggest'] == [['Fischer', 'Lucas Fischer'], ['Fabricio Santos', 'Fabricio']], r['suggest']  # 2nd: his own add
    gab = next(x for x in r['dubious'] if x['name'] == 'Gabriel')  # Hanauer put "gabriel": Gab and Matte also go by Gabriel
    assert gab['by'] == 'Hanauer' and gab['options'] == ['Gabriel', 'Gabi Steinhaus', 'Matte', GUEST], gab
    assert [x['name'] for x in r['dubious']] == ['Jesus Cristo', 'Fabricio Santos', 'Gabriel']  # nobody plays as Jesus Cristo: a guest?
    fab = next(x for x in r['dubious'] if x['by'] == 'Fabricio')  # he put "fabricio" once, the tabela wrote Fabricio Santos
    assert fab['options'] == ['Fabricio Santos', 'Fabricio', GUEST], fab
    ident = {'88880000': ('Perdigao', 'lista'), 'Gabriel Simões': ('Gabriel', 'nome'), '12340000': (None, None)}
    contacts(ident, {'88880000': 'Gabriel Simões', '12340000': 'Zé'}, ['Gabriel Simões', 'Zé', 'me'])
    assert ident['Gabriel Simões'] == ('Perdigao', 'nome') and 'Zé' not in ident, ident
    sw = switches(r['ident'], {'33330000': (0, 86400 * 100), '66660000': (86400 * 101, 86400 * 300)}, {'33330000': '1970-04-10'})
    assert sw == [{'name': 'Victor', 'old': '0000', 'new': '0000', 'date': '1970-04-10', 'at_once': False}], sw

    c = cards(['FN:Rafa\nTEL;waid=555199990000:+55', 'FN:Leonardo Saul\nTEL;waid=555177770000:+55',
               'FN:Clinica\nTEL;waid=555166660000:+55', 'FN:Vito\nTEL;waid=555155550000:+55', 'FN:Vito\nTEL;waid=555144440000:+55',
               'FN:Zé Novo\nTEL;waid=555133330000:+55', 'FN:972\nTEL;waid=555122220000:+55'])
    assert set(c) == {'555199990000', '555177770000', '555166660000', '555133330000'}, c  # "Vito" names two numbers: dropped
    salt = '00' * 16
    names, how, skipped = build({'99990000': ('Rafo', 'lista'), 'me': ('Gab', 'nome')}, salt, {'leonardo saul': 'Leo Saul'},
                                c, posted={'555133330000'})
    get = lambda ph: (names.get(phone_key(ph, salt)), how.get(phone_key(ph, salt)))
    assert get('555199990000') == ('Rafo', 'lista') and len(names) == 3  # the lists win over the card; 'me' has no number
    assert get('555177770000') == ('Leo Saul', 'contato') and get('555133330000') == ('Zé Novo', 'contato')
    assert get('555166660000') == (None, None) and skipped == 1
    print('selftest ok')


def main():
    sys.path.insert(0, CHAT)
    from identity import phone  # noqa: E402  the chat miner's sender -> digits
    from mine_lists import parse_list, names  # noqa: E402
    lid = dict(re.match(r'(\d+) "(\d+)"', l).groups() for l in open(os.path.join(CHAT, 'derived', 'lid_phone.txt')) if l.strip())
    msgs = [json.loads(l) for l in open(os.path.join(CHAT, 'out', 'biofut_messages.jsonl'), encoding='utf-8')]
    mine = {m['sender_name'] for m in msgs if str(m.get('from_me')) == '1' and m.get('sender_name')}  # the export's owner

    def key(s):
        p = phone(s, lid)
        return 'me' if s == 'me' or s in mine else p[-8:] if p else s

    spans, push = {}, {'me': min(mine, default='')}
    for m in msgs:
        k = key(m.get('sender_name') or m.get('sender') or '')
        if k.isdigit():
            a, b = spans.get(k, (m['ts'], m['ts']))
            spans[k] = (min(a, m['ts']), max(b, m['ts']))
    if os.path.exists(WADB):
        db = sqlite3.connect(Path(WADB).as_uri() + '?mode=ro', uri=True)
        for l, p in lid.items():
            row = db.execute("select push_name from contacts where id=? and push_name!=''", (l + '@lid',)).fetchone()
            if row:
                push[p[-8:]] = row[0]
    people = json.load(open(os.path.join(CHAT, 'derived', 'people.json'), encoding='utf-8'))['people']
    miner = {}
    for p in people:
        n = p.get('db_player') or (p['aliases'][0].title() if p.get('aliases') else None)
        k = p['phone'][-8:] if p.get('phone') else key(p['senders'][0])
        if n:
            miner[k] = (n, (p.get('how') or '').startswith('jaccard'))
    vcfs, notices = [], {}
    for z in glob.glob(os.path.join(CHAT, 'export', '*.zip')):
        with zipfile.ZipFile(z) as f:
            for n in f.namelist():
                t = f.read(n).decode('utf-8', 'replace')
                if n.lower().endswith('.vcf'):
                    vcfs.append(t)
                elif n.endswith('.txt'):  # "28/01/2024 23:56 - +55 51 9xxxx-xxxx mudou de número de telefone."
                    for d, mo, y, who_ in re.findall(r'^(\d\d)/(\d\d)/(\d{4}) [\d:]+ - \W*(\+[\d\s-]+?) mudou de número', t, re.M):
                        notices[key(who_)] = f'{y}-{mo}-{d}'
    adds = [(d, key(s), n) for d, s, n in list_adds(msgs, parse_list, names)]
    games = json.load(urllib.request.urlopen(urllib.request.Request(SITE + '/api/data', headers={'User-Agent': 'biofut-phones'}), timeout=30))['games']
    r = resolve(games, adds, push, miner)
    if os.path.exists(FIX):
        r['ident'].update({k: (n, 'lista') for k, n in json.load(open(FIX, encoding='utf-8')).items()})
    senders = {m.get('sender_name') or m.get('sender') or '' for m in msgs}
    contacts(r['ident'], push, {key(s) for s in senders})
    wiki_names = {s: r['alias'].get(n, n) for s in senders if (n := (r['ident'].get(key(s)) or (None,))[0])}
    json.dump(wiki_names, open(SENDERS, 'w', encoding='utf-8'), ensure_ascii=False)
    posted = {phone(m.get('sender_name') or m.get('sender') or '', lid) for m in msgs} - {None}
    salt = secrets.token_hex(16)
    m, how, skipped = build(r['ident'], salt, r['known'], cards(vcfs), posted)
    sw = switches(r['ident'], spans, notices)
    out = {'salt': salt, 'map': m, 'how': how, 'me': r['ident'].get('me', (None,))[0], 'alias': r['alias'],
           'suggest': r['suggest'], 'switches': sw, 'dubious': r['dubious']}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    texts = collections.defaultdict(list)  # same sender -> name as the login, so a member reads what their number wrote
    for x in msgs:
        k, t = key(x.get('sender_name') or x.get('sender') or ''), (x.get('text') or '').replace('<Esta mensagem foi editada>', '').strip()
        if k in r['ident'] and t and x['type'] in ('export', 'conversation', 'extendedText', 'image', 'video') \
                and not HIDDEN.search(t) and not parse_list(t, x['ts']):
            n = r['ident'][k][0]
            texts[r['alias'].get(n, n)].append([x['ts'], t[:1000]])
    for v in texts.values():
        v.sort()
    json.dump(texts, open(MSGS, 'w', encoding='utf-8'), ensure_ascii=False)
    print(sum(map(len, texts.values())), 'messages of', len(texts), 'members ->', MSGS)
    print(len(m), 'numbers ->', OUT, dict(collections.Counter(how.values())), f'({skipped} contact cards nobody vouches for skipped)')
    print('me:', out['me'], '| alias:', r['alias'], '| suggest:', r['suggest'])
    for s in sw:
        print(f"switch: {s['name']} ...{s['old']} -> ...{s['new']} {s['date']}" + (' (both numbers at once)' if s['at_once'] else ''))
    print(len(r['dubious']), 'dubious adds, by year:', dict(collections.Counter(x['date'][:4] for x in r['dubious'])))
    canon = lambda t: r['alias'].get(t, t)
    y26 = {canon(p[0]) for g in games if (g.get('date') or '') >= '2026' for t in g['teams'] for p in t['players']} - {'Sombra'}
    with_phone = {n for k, (n, _) in r['ident'].items() if k.isdigit() or k == 'me'}  # 'me': BIOFUT_ADMIN_PHONE
    print(f'2026 players with a known number: {len(y26 & with_phone)}/{len(y26)}; without:', sorted(y26 - with_phone))


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
        sys.exit()
    main()
