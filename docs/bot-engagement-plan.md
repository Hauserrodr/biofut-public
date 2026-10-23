# Bot engagement plan (2026-10-23)

## Why the bot is silent today

Every group post from the bot is a reaction to something done on the site:
a site sign-up (`join_ping`), a site draft action (`draft_news`, `pick_ping`), or a
site `close_match` (`match_news`). On 22/10 the players did the list and the draft in
the WhatsApp chat, so none of these ran. The súmula photo went through OCR and was
released by the 6 h timer. That notice goes to the Avisos group only, so the main
group never saw the result or the OCR errors.

So the fix is to make the bot react to what the players already do in the chat,
and to show its readings in the group while they can still be corrected.

## Phase 0: no new number needed

1. **Show the súmula reading in the group when it arrives.** One post per photo:
   score, scorers, assists, and "sai às HH:MM, algo errado? responde aqui ou
   corrige no site". Players fix errors in the 6 h window. Today they never see it.
2. **Post the result when a súmula is released** (`match_news` runs only on a site
   `close_match` today). Result, top scorer, BioBet payouts.
3. **List parser fixes** (`lista.py`, `sync_list`):
   - count players under "Time X" headers as confirmed;
   - read bare names under a "Time X" header, not only `- name` lines.
4. **Chat draft feeds the site** (Gab decides): when a list post has two full team
   blocks, use them as the site draft, open BioBet, and post the same "Times
   fechados + odds" message the site draft posts. The players keep their habit;
   the site gets the data.
5. **Fix a released game.** No route edits a game after release. Add one: a
   `jogo` review item (the "súmula não bate" report) that Gab edits, and its release
   replaces game `n` in `played`.
6. **Reactions as feedback, zero noise.** The bot reacts ✅ to a list post it synced
   and 📸 to a photo it read as a súmula. Players see it worked without a message.

## Phase 1: the bot gets its own SIM

1. Register the SIM in the WhatsApp Business app on an Android phone (a dual-SIM
   phone works; the Business app keeps it apart from the personal account).
2. Link the bot to it: `bot/deploy-bot.ps1 -Phone <digits>` prints the pairing code.
   The phone must come online at least once every 14 days or the link drops.
3. A group admin adds the number to the group and to Avisos.
4. Drop the `[ESQUIZOFUT]` prefix. It exists only because the bot speaks from Gab's
   account. Give the number a name and avatar.
5. Login codes and draft DMs then come from the bot, not from Gab.
6. Warm the number up: a few days of normal group posts before any DMs. New numbers
   that send many DMs get banned.

## Phase 2: things worth a message

A weekly rhythm, at most 3 bot posts a day, none between 23:00 and 08:00:

| When | Post |
|---|---|
| Monday | Week recap: last result, top scorer, BioBet winners, ranking moves |
| Game day, list time | "Lista aberta" with the link and who is already in |
| Game day, after the draft | Teams and BioBet odds (from the site or the chat draft) |
| After the súmula | Reading for confirmation, then the result |
| After the game | Native WhatsApp poll: craque da partida, result goes to the site |

Also:

- **Answer when called.** A reply to a bot message or an @mention gets an answer
  ("quem tá na lista", "odds", "artilheiro"), without needing `!` commands.
- **Pix reminder** (Gab decides on/off and tone): one line the day after the game.
  No names in the group.
- **Kill switch:** admins send `!silencio` to mute the bot for 24 h.

## Phase 3: the draft happens with the bot (Gab's request, 2026-10-23)

### Push people to the site at the right moment

- **Draft signs in the chat:** a list post with team blocks, the word "draft", or
  "(C)" marks. The bot answers once with the Draft Live link.
- **Game day, 11:00:** if the list is full, the bot posts
  "📋 A lista está cheia e é hora do draft! Votação para quem quer ser capitão
  começa agora: {link} (ou manda !capitao)".
  "Full" = 14 players + goalies (Gab, 2026-10-23); 16 is the maximum.

### Captain flow

1. **11:00 to 12:30: volunteers.** Players volunteer on the site or with
   `!capitao`. A group poll can hold at most 12 options, so the list does not fit
   in one poll. Volunteering uses the site and the command.
2. **12:30:** with 2 volunteers or more, the bot takes the 2 with the most votes.
   With fewer, it draws the missing captains at random from the list. It skips
   goalkeepers and maybe last week's captains.
3. **The drawn player gets a DM poll with 2 options:**
   "🎖️ O EsquizoBot consultou os astros, o VAR e a tia do cafezinho: você foi
   escolhido para ser CAPITÃO hoje. Aceita essa honra ou vai amarelar?"
   Options: "Aceito, me dá a braçadeira 💪" and "Passo, não nasci pra liderar 🐔".
4. **A "Passo" vote stays private.** The bot draws again until 2 players accept.
   No answer in 20 min: draw again (Gab, 2026-10-23).
5. **Announce** the 2 captains in the group. `draft_start` then runs as today.

DMs need the bot's own number (Phase 1). From Gab's account they would come from Gab.

### Image cards

The bot sends images in place of some text posts: draft status, the players still
available with a small chart of their goals, assists and win rate, and the BioBet
odds. Rendering choices:

- Pillow in the site container. It is a pip install, and `og_copa.py` already
  draws with Pillow on Gab's PC.
- or node canvas in the bot.

The bot sends the PNG through Baileys (`sendMessage(to, {image, caption})`).
Pillow in the site is the shorter path: the site has the data.

### Three ways to pick

1. **Paste the list.** The captain pastes the list back, with or without the picked
   players removed. The parser diffs it against the last state: a name that
   disappeared, or a name marked with the captain's team, is a pick. Names go
   through the alias table. When the diff is unclear, the LLM (DeepSeek, already
   used for the súmula OCR) reads it, and the bot asks "foi o X?" before it
   records the pick.
2. **`!pick <nome>`** in the group, accepted only from the captain whose turn it is.
3. **The site,** as today.

All three call the same `draft_pick` code, so the site, the group post and BioBet
stay in step.

### Draft Live page

A `#/draft-live` page, shown while a draft is open:

- banners: whose turn it is, picks so far, team totals (goals, assists, win rate);
- a slideshow of the players still on the list, one card each, with their table
  stats;
- the model's prediction for the teams so far, which updates after every pick, and
  the model's track record (see below).

## Model v2: stats as input

Gab asked whether the BioBet prediction got 22/10 right. It did not. The deployed
model gave team A 46 %, the draw 15 % and team B 39 %. Team B won 6×4.

`site/backtest.py` tests this walk-forward. It runs on the 85 games after the
deployed model's training cut (n 217 to 300, plus 22/10), and every game is
predicted from earlier games only:

| Model | Input | Log loss | Accuracy | Goals per team, MAE |
|---|---|---|---|---|
| deployed logistic | players (one-hot + pairs) | 0.968 | 0.50 | none |
| base rates | none | 0.949 | 0.51 | 2.73 |
| Poisson GLM | team sums and means of the table stats | **0.905** | **0.57** | **2.37** |
| xgboost (Poisson) | same | 0.936 | 0.55 | 2.38 |

On 22/10 the GLM gave team B 49 % and 5.9 × 6.4 goals. xgboost gave team A 59 %.

- The deployed model is worse than base rates on games it did not see. It knows
  players by name, so new players and alternate spellings of a name fall
  out of it.
- The table-stats input is what Gab asked for, and it works. Inputs per player:
  goals and assists per game, win rate, points per game, team goals for and
  against, form (last 10), games played, all shrunk toward the league mean with 5
  pseudo-games.
- **Ship the GLM first.** It is a set of coefficients, so the stdlib server can run
  it the way it runs the logistic today. 300 games is little for trees. xgboost
  stays as a challenger, and the backtest is re-run each month.
- **Score:** two Poisson goal rates give the score and the win/draw/loss odds.
- **Goals and assists per player:** the team's goal rate times the player's share
  of the team's goals per game. Player goals MAE 0.735 against 0.856 for a flat
  share. Assists use the same method, not yet tested.
- Caveats: one run, 85 games. The first-listed team wins more often in the data,
  so the site must feed teams in a fixed order.

## Scoreboard photos

On 22/10 a player posted 6 photos of the scoreboard (04 06). The pipeline reads the
súmula only. Reading the scoreboard too gives a check: when the scoreboard total
differs from the súmula goals, the item is held for review.

## How to tell it worked

Per game night, from the site state and the WhatsApp log: list synced (yes/no),
teams on the site (yes/no), number of BioBet bets, súmula corrected before release
(yes/no), replies and reactions to bot posts. Compare 4 weeks before and after.

## Decisions for Gab

1. ~~Chat draft feeds the site draft~~ **Decided 2026-10-23: yes. A block is 6 field players + the goalie. A team change gives the game bets back; list mercados keep working. A site sign-up during a chat draft with room left resets the draft and tells the group.**
2. ~~Pix reminder~~ **Decided 2026-10-23: on, funny, no names.**
3. ~~Bot name and avatar~~ **Decided 2026-10-23: "AG", a styled tag and a robot-chimera avatar of the animal champions.**
4. ~~Which admin adds the number~~ **Decided 2026-10-23: Gab adds it.**
5. ~~A drawn captain who does not answer the DM poll~~ **Decided 2026-10-23: draw again.**
6. ~~"List full"~~ **Decided 2026-10-23: 14 players + goalies is the threshold (the game happens). 16 is the maximum (e.g. 14 + 2 goalies, 15 + 1, or 16 players).**
7. ~~Model v2~~ **Decided 2026-10-23: ship the GLM in place of the logistic.**
