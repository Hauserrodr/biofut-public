"""SQL copy of the site's JSON files: Postgres db "biofut" (pgvector on, for embeddings later), table docs (one jsonb
row per file) plus the views in SQL. biofut-db.timer (deploy.ps1) runs it every 5 minutes; `db.py schema` remakes the views.
ponytail: the JSON files stay the source of truth and the site never reads this; the site writing here is the upgrade."""
import json
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

HERE = Path(__file__).parent
SKIP = {"phones.json", "mensagens.json"}  # backup.sh leaves out the same: phone numbers, each member's own messages
SQL = """
create table if not exists docs (name text primary key, doc jsonb not null, at timestamptz not null default now());
drop view if exists balances, duelos, game_players, games, ledger, mercado_bets, mercados, bets cascade;
create view games as
  select (g->>'n')::int as n, g->>'season' as season, (g->>'date')::date as date, 'planilha' as src, g as game
    from docs, jsonb_array_elements(doc->'games') g where name = 'biofut.json'
  union all  -- server.py unsynced(): games played on the site that the sheet does not have yet
  select (g->>'n')::int, g->>'season', (g->>'date')::date, 'site', g
    from docs s, jsonb_array_elements(s.doc->'played') g where s.name = 'data/state.json'
     and not exists (select from docs, jsonb_array_elements(doc->'games') x where name = 'biofut.json' and x->>'date' = g->>'date');
create view game_players as
  select n, season, date, src, t->>'name' as team, t->>'res' as res, p->>0 as player, (p->>1)::int as goals,
         (p->>2)::int as assists, (p->>3)::int as own_goals, (p->>4)::int = 1 as captain
    from games, jsonb_array_elements(game->'teams') t, jsonb_array_elements(t->'players') p;
create view ledger as
  select i, x->>'player' as player, (x->>'amount')::int as amount, x->>'reason' as reason
    from docs, jsonb_array_elements(doc->'ledger') with ordinality l(x, i) where name = 'data/state.json';
create view duelos as  -- server.py duel_act: each member's Duelo record (run: wins in a row now, best_run: the longest)
  select player, (r->>'v')::int as wins, (r->>'e')::int as draws, (r->>'d')::int as losses, (r->>'run')::int as run,
         (r->>'top')::int as best_run, (r->'best'->>0)::int as best_for, (r->'best'->>1)::int as best_against
    from docs, jsonb_each(doc->'duelo') d(player, r) where name = 'data/state.json';
create view balances as  -- server.py balance(): WELCOME 25 + 1 per goal or assist ever + the ledger + 0.0001 a Duelo won
  select player, 25 + coalesce(g, 0) + coalesce(l, 0) + coalesce(w, 0) * 0.0001 as balance
    from (select player, sum(goals + assists) as g from game_players group by player) a
    full join (select player, sum(amount) as l from ledger group by player) b using (player)
    full join (select player, wins as w from duelos) c using (player);
create view mercados as
  select (m->>'id')::int as id, m->>'kind' as kind, (m->>'date')::date as date, m->>'text' as text, m->>'by' as opened_by,
         (m->>'min')::int as min, m->>'status' as status, to_timestamp((m->>'fecha')::float) as fecha,
         to_timestamp((m->>'done')::float) as done, m->>'end_by' as end_by, (m->>'casa')::int as casa,
         (select sum((b->>'stake')::int) from jsonb_array_elements(m->'bets') b) as pot
    from docs, jsonb_array_elements(doc->'mercados') m where name = 'data/state.json';
create view mercado_bets as
  select (m->>'id')::int as mercado, b->>'who' as who, b->>'side' as side, (b->>'stake')::int as stake,
         (b->>'odds')::numeric as odds, to_timestamp((b->>'at')::float) as at, (b->>'pay')::int as pay
    from docs, jsonb_array_elements(doc->'mercados') m, jsonb_array_elements(m->'bets') b where name = 'data/state.json';
create view bets as  -- game bets: the week's game (aberta), played (jogada), cancelled (cancelada)
  select (b->>'id')::int as id, (g->>'date')::date as date, st as status, b->>'bettor' as bettor, b->>'pick' as pick,
         (b->>'stake')::int as stake, (b->>'odds')::numeric as odds, (b->>'payout')::int as payout
    from docs, lateral (select doc->'match', 'aberta' union all select g, 'jogada' from jsonb_array_elements(doc->'played') g
                        union all select g, 'cancelada' from jsonb_array_elements(doc->'cancelados') g) s(g, st),
         jsonb_array_elements(g->'bets') b
   where name = 'data/state.json';
"""


def read(f):
    t = f.read_text(encoding="utf-8")  # .jsonl: the last piece is "" or a line still being written, so it waits
    return [json.loads(l) for l in t.split("\n")[:-1] if l.strip()] if f.suffix == ".jsonl" else json.loads(t)


files = [HERE / "biofut.json", *(f for d in ("data", "data/wiki") for f in sorted((HERE / d).glob("*.json*"))
                                 if f.suffix in (".json", ".jsonl") and f.name not in SKIP)]
names = [f.relative_to(HERE).as_posix() for f in files]
with psycopg.connect("dbname=biofut") as db:  # the local socket as user ubuntu (peer auth): no password
    if sys.argv[1:] == ["schema"]:
        db.execute(SQL)
    for name, f in zip(names, files):
        db.execute("insert into docs values (%s, %s) on conflict (name) do update set doc = excluded.doc, at = now()"
                   " where docs.doc is distinct from excluded.doc", [name, Jsonb(read(f))])
    db.execute("delete from docs where name <> all(%s)", [names])
