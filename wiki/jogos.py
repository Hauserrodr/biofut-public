"""#34: the group's photos of each game night, for the open game on the site (members only: /api/jogos, /wiki/media).
A photo belongs to a night when it was posted from 16:00 that day to noon the next, on a date the site has a game, and
caption.py saw a súmula, a scoreboard, a team or a person in it. Súmulas first, at most 8 a night.
Out: data/wiki/jogos.json {date: [{file, kind, by, at}]} + resized copies in data/wiki/media; deploy.ps1 -Wiki uploads both.
Usage: python jogos.py [games json: url or file, default the live site]   (BIOFUT_CHAT and WIKI_OUT as wiki.py) | selftest
"""
import collections, datetime as dt, json, os, sys, urllib.request
import wiki

KINDS = ('match_summary', 'scoreboard', 'team_photo', 'person_photo')  # the order on the page
PER_NIGHT = 8


def night(ts):
    """The game night a photo was posted after (the export's local time), or None for a daytime photo."""
    w = dt.datetime.fromtimestamp(ts)
    return w.date().isoformat() if w.hour >= 16 else (w.date() - dt.timedelta(1)).isoformat() if w.hour < 12 else None


def build(src='https://biofut.h-brain.org/api/data'):
    games = json.load(urllib.request.urlopen(src, timeout=30) if src.startswith('http') else open(src, encoding='utf-8'))['games']
    dates = {g['date'] for g in games if g.get('date')}  # the live site: the sheet's games, newer than any local build
    kind = {x['file']: x['kind'] for x in map(json.loads, open(os.path.join(wiki.D, 'images_deepseek.jsonl'), encoding='utf-8'))}
    nm, out = wiki.names(), collections.defaultdict(list)
    for m in map(json.loads, open(wiki.MSGS, encoding='utf-8')):
        f = os.path.basename(m.get('media_path') or '')
        d = m.get('type') == 'image' and kind.get(f) in KINDS and night(m['ts'])
        if d in dates:
            wiki.SRC_IMG[f] = m['media_path'] if os.path.isabs(m['media_path']) else os.path.join(wiki.MEDIA_DIR, m['media_path'])
            out[d].append({'file': f, 'kind': kind[f], 'by': wiki.who(m, nm), 'at': dt.datetime.fromtimestamp(m['ts']).strftime('%d/%m %H:%M')})
    os.makedirs(os.path.join(wiki.OUT, 'media'), exist_ok=True)
    for d, xs in out.items():
        xs.sort(key=lambda x: KINDS.index(x['kind']))  # stable: the same kind keeps the chat's order
        out[d] = [x for x in xs[:PER_NIGHT] if wiki.photo(x['file'])]
    out = {d: xs for d, xs in sorted(out.items()) if xs}
    with open(os.path.join(wiki.OUT, 'jogos.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(len(out), 'game nights,', sum(map(len, out.values())), 'photos ->', os.path.join(wiki.OUT, 'jogos.json'))


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        t = lambda s: dt.datetime.fromisoformat(s).timestamp()
        assert night(t('2026-10-08T21:30')) == '2026-10-08' and night(t('2026-10-09T08:00')) == '2026-10-08'
        assert night(t('2026-10-09T14:00')) is None
        print('ok')
    else:
        build(*sys.argv[1:])
