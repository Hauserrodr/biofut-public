"""List stats for the transparency page: who signs up, who drops out, how often BioFut flakes.

Reads the chat (BIOFUT_CHAT/out/biofut_messages.jsonl) with lista.py's parser (the chat miner's, vendored) and diffs every repost of a game's list.
  sign-up   a name shows up on a game's list (players, goalies or waiting) in any version
  drop-out  a name that was on the list is gone from the last version before the game
  last-minute: gone in a version posted on game day
  timing:   every add and drop is stamped with the time of the repost that shows it, in hours before kickoff
             (the hour in the list header, else 18h); per person: median lead of sign-ups and of final drop-outs
  cancelled: not in the recorded games (biofut.json) and no teams were posted, and the chat says "cancelado" on game day
             or the day before (nobody says "descancelado"), or the list never got 8 names
Writes data/listas.json (outside git). Phone numbers are never read here; names go through people.json aliases.
Usage: python listas.py [--send] [--selftest]   (--send: queue it on /admin via submit.py; live after approval or 6 h)
"""
import collections, datetime as dt, json, os, re, sys

from lista import RESET, parse_list, fold

HERE = os.environ.get('BIOFUT_CHAT', 'D:/dev/BDSMA/whatsapp')

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'listas.json')
CANCEL = re.compile(r'\b(cancelad[oa]|cancelamos|cancelei|n[aã]o vai ter (jogo|biofut|futebol))\b', re.I)
KICK = re.compile(r'\b(1[0-9]|2[0-3]|[89])\s*(?:h|:\d\d)', re.I)  # "18h", "18:30" in the header: kickoff hour


NOISE = re.compile(r'mensagem editada|mensagem apagada|mensagem foi apagada|<|>', re.I)  # export artifacts glued to a slot


def on_list(v):
    return {n for n in (fold(NOISE.sub('', e['name'])) for k in ('goalies', 'players', 'waiting') for e in v[k]) if len(n) > 1}


def kickoff(date, text):
    """Kickoff timestamp: the hour in the list's first lines, else 18h (94% of headers say 18h)."""
    h = KICK.search('\n'.join(text.splitlines()[:6]))
    return dt.datetime.fromisoformat(date).replace(hour=int(h.group(1)) if h else 18).timestamp()


def game_stats(versions):
    """versions of one game's list, sorted by time -> (signed, dropped, late, events) with folded names.
    events: (ts, name, '+'|'-') for every add and removal, comebacks included; a reset repost adds none."""
    signed, base, late, events = set(), None, set(), []
    for v in versions:
        names = on_list(v)
        if base is not None and len(base - names) > RESET:
            continue  # reset repost: keep the previous version as the baseline
        if base is not None and v['_late']:
            late |= base - names
        events += [(v['_ts'], n, '+') for n in sorted(names - (base or set()))]
        events += [(v['_ts'], n, '-') for n in sorted((base or set()) - names)]
        signed |= names
        base = names
    final = base or set()
    return signed, signed - final, (late - final), events


def leads(events, kick, dropped):
    """-> ({name: hours before kickoff of the first add}, {dropped name: hours before kickoff of the last removal})."""
    add, drop = {}, {}
    for ts, n, op in events:
        if op == '+':
            add.setdefault(n, (kick - ts) / 3600)
        elif n in dropped:
            drop[n] = (kick - ts) / 3600
    return add, drop


BUCKETS = (('mais de 2 dias antes', 48), ('1 a 2 dias antes', 24), ('6 a 24 h antes', 6), ('menos de 6 h antes', 0),
           ('depois do horário do jogo', -1e9))


def bucket(h):
    return next(b for b, lo in BUCKETS if h >= lo)


def canon_names(people):
    """folded alias -> display name, from people.json (db_player or first alias)."""
    out = {}
    for p in people:
        show = p.get('db_player') or (p['aliases'][0].title() if p['aliases'] else None)
        for a in p['aliases'] + ([p['db_player']] if p.get('db_player') else []):
            if show:
                out.setdefault(fold(a), show)
    return out


def build(msgs, canon, recorded=()):
    by_date, chat = collections.defaultdict(list), collections.defaultdict(str)
    for m in msgs:
        t = m.get('text') or ''
        day = dt.date.fromtimestamp(m['ts'])
        chat[day.isoformat()] += t + '\n'
        if t.count('\n') < 6 or (m.get('sender_name') or '') == 'Meta AI':
            continue
        v = parse_list(t, m['ts'])
        if v and on_list(v):
            v['_late'] = day.isoformat() == v['date']
            v['_ts'], v['_teams'], v['_kick'] = m['ts'], bool(v['teams']), kickoff(v['date'], t)
            by_date[v['date']].append(v)
    who = lambda n: canon.get(n) or n.title()
    P = collections.defaultdict(lambda: collections.Counter())
    lead_add, lead_drop, when_drop = collections.defaultdict(list), collections.defaultdict(list), collections.Counter()
    games = []
    for date, vs in sorted(by_date.items()):
        end = dt.datetime.fromisoformat(date).replace(hour=23, minute=59).timestamp()
        vs = sorted((v for v in vs if v['_ts'] <= end), key=lambda v: v['_ts'])
        if not vs:
            continue
        signed, dropped, late, events = game_stats(vs)
        kick = vs[0]['_kick']
        add, drop = leads(events, kick, dropped)
        prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
        talk = chat.get(prev, '') + chat.get(date, '')
        happened = date in recorded or any(v['_teams'] for v in vs)
        cancelled = not happened and (bool(CANCEL.search(talk)) and 'descancel' not in talk.lower() or len(signed) < 8)
        games.append({'date': date, 'kickoff': dt.datetime.fromtimestamp(kick).strftime('%H:%M'), 'signed': len(signed),
                      'dropped': len(dropped), 'versions': len(vs), 'cancelled': cancelled,
                      'eventos': [[int(ts), who(n), op] for ts, n, op in events]})  # members only: the server strips it
        if not cancelled:  # timing of games that happened; a cancelled game's "drops" are the whole list leaving
            for n, h in add.items():
                lead_add[who(n)].append(h)
            for n, h in drop.items():
                lead_drop[who(n)].append(h)
                when_drop[bucket(h)] += 1
        for field, ns in (('inscricoes', signed), ('desistencias', dropped), ('em_cima_da_hora', late)):
            for n in {who(n) for n in ns}:  # two spellings of one person count once
                P[n][field] += 1
    people = [{'name': k, **v} for k, v in P.items() if v['inscricoes'] >= 3]
    med = lambda xs: round(sorted(xs)[len(xs) // 2], 1) if xs else None
    for p in people:
        p['taxa'] = round(p.get('desistencias', 0) / p['inscricoes'], 3)
        p['inscreve_h'], p['desiste_h'] = med(lead_add[p['name']]), med(lead_drop[p['name']])
    top = lambda f, n=5, pool=people: [{'name': p['name'], 'n': p.get(f, 0)} for p in sorted(pool, key=lambda p: -p.get(f, 0))[:n] if p.get(f)]
    regular = [p for p in people if p['inscricoes'] >= 20]
    canc = sum(g['cancelled'] for g in games)
    hrs = lambda h: f"{h:.0f} h antes" if h < 48 else f"{h / 24:.1f} dias antes"
    early = [p for p in regular if p['inscreve_h'] is not None]
    quitters = [p for p in people if len(lead_drop[p['name']]) >= 5]
    return {'built': dt.datetime.now().isoformat(timespec='minutes'), 'games': games, 'people': sorted(people, key=lambda p: -p['inscricoes']),
            'flake': {'games': len(games), 'cancelled': canc, 'rate': round(canc / max(1, len(games)), 3)},
            'quando_desistem': [{'faixa': b, 'n': when_drop[b]} for b, _ in BUCKETS],
            'trophies': {
                'Assinatura Compulsiva (mais inscrições)': top('inscricoes'),
                'Rei do Arrego (mais desistências)': top('desistencias'),
                'Ghosting Profissional (desistiu no dia do jogo)': top('em_cima_da_hora'),
                'Taxa de Flake Individual (desistências / inscrições, 20+ listas)': [
                    {'name': p['name'], 'n': f"{p['taxa']:.0%}"} for p in sorted(regular, key=lambda p: -p['taxa'])[:5]],
                'Palavra de Honra (menor taxa de desistência, 20+ listas)': [
                    {'name': p['name'], 'n': f"{p['taxa']:.0%}"} for p in sorted(regular, key=lambda p: (p['taxa'], -p['inscricoes']))[:5]],
                'Madrugador (se inscreve mais cedo, mediana, 20+ listas)': [
                    {'name': p['name'], 'n': hrs(p['inscreve_h'])} for p in sorted(early, key=lambda p: -p['inscreve_h'])[:5]],
                'Arrego Cronometrado (desiste mais perto do jogo, mediana, 5+ desistências)': [
                    {'name': p['name'], 'n': hrs(p['desiste_h'])} for p in sorted(quitters, key=lambda p: p['desiste_h'])[:5]],
            }}


def selftest():
    def v(names, late=False):
        return {'goalies': [], 'waiting': [], 'players': [{'name': n} for n in names], '_late': late}
    def vt(names, ts, late=False):
        return {**v(names, late), '_ts': ts}
    full = ['ana', 'cid', 'edu', 'fer', 'gil']
    s, d, l, e = game_stats([vt(['ana', 'bob'], 1), vt(full + ['bob'], 2), vt(full, 3, late=True), vt(['zeca'], 4), vt(full + ['dan'], 5)])
    assert s == set(full) | {'bob', 'dan'} and d == {'bob'} and l == {'bob'}, (s, d, l)  # ['zeca'] is a reset: ignored
    assert (1, 'ana', '+') in e and (3, 'bob', '-') in e and (5, 'dan', '+') in e and not any(n == 'zeca' for _, n, _ in e), e
    s, d, l, e = game_stats([vt(['aa', 'bb'], 0), vt(['aa'], 3600, late=True), vt(['aa', 'bb'], 7200, late=True)])
    assert d == set() and l == set()  # left and came back: not a drop
    assert [x for x in e if x[1] == 'bb'] == [(0, 'bb', '+'), (3600, 'bb', '-'), (7200, 'bb', '+')]
    add, drop = leads([(0, 'aa', '+'), (0, 'bb', '+'), (3600, 'bb', '-'), (7200, 'bb', '+'), (9000, 'bb', '-')], 10800, {'bb'})
    assert add == {'aa': 3.0, 'bb': 3.0} and drop == {'bb': 0.5}, (add, drop)  # first add, last removal
    k = lambda s: dt.datetime.fromtimestamp(kickoff('2026-10-01', s)).hour
    assert k('*BioFut 01/10 - 19h*\nquadra 2') == 19 and k('BioFut 01/10 18:30') == 18 and k('BioFut 01/10\n1 - x') == 18
    assert bucket(50) == BUCKETS[0][0] and bucket(3) == BUCKETS[3][0] and bucket(-1) == BUCKETS[4][0]
    assert canon_names([{'aliases': ['rafa', 'rafo'], 'db_player': 'Rafo'}]) == {'rafa': 'Rafo', 'rafo': 'Rafo'}
    print('selftest ok')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
    else:
        people = json.load(open(os.path.join(HERE, 'derived', 'people.json'), encoding='utf-8'))['people']
        msgs = [json.loads(l) for l in open(os.path.join(HERE, 'out', 'biofut_messages.jsonl'), encoding='utf-8')]
        site = os.environ.get('BIOFUT_DATA', 'D:/dev/BDSMA/site/biofut.json')
        recorded = {g['date'] for g in json.load(open(site, encoding='utf-8'))['games'] if g.get('date')} if os.path.exists(site) else set()
        r = build(msgs, canon_names(people), recorded)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        json.dump(r, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(r['flake'], len(r['people']), 'people ->', OUT)
        for k, v in r['trophies'].items():
            print(k, v[:3])
        if '--send' in sys.argv:
            from submit import send
            send('listas', f"Listas: {len(r['people'])} pessoas, flake index {r['flake']['rate']:.0%}", r)
