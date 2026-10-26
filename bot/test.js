'use strict';
// node test.js : pure logic + dry-run webhook end to end
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { reply, join, toJid, tag, findAvisos, loginAsk, isList } = require('./bot');

const cfg = { siteUrl: 'https://biofut.example/', captains: [{ name: 'Victor', phone: '+55 51 90000-0001' }, { name: 'Canova', phone: '5551900000002' }] };
const url = 'https://biofut.example/#/jogo';
const m0 = { date: '2026-10-10', confirmed: [], draft: null };
const m1 = { date: '2026-10-10', confirmed: ['Victor', 'Canova', 'Zé'], draft: { captains: ['Victor', 'Canova'], teams: { Victor: ['Victor', 'Zé'], Canova: ['Canova'] } } };

assert.strictEqual(reply('!draft', cfg, m0), `⚽ Draft da semana (2026-10-10): ${url}`);
assert.match(reply('!ENTRAR agora', cfg, m0), /#\/jogo$/);
assert.match(reply('!lista', cfg, m0), /Ninguém/);
assert.match(reply('!lista', cfg, m1), /Confirmados \(3\):\n1\. Victor\n2\. Canova\n3\. Zé\n/);
assert.strictEqual(reply('!capitaes', cfg, m1), 'Capitães: Victor x Canova');
assert.match(reply('!capitaes', cfg, m0), /ainda não/);
assert.match(reply('!times', cfg, m1), /^Time Victor: Victor, Zé\nTime Canova: Canova\n/);
assert.match(reply('!lista', cfg, null), /fora do ar/);
assert.strictEqual(reply('bora jogar', cfg, null), null);
assert.strictEqual(tag('oi'), '🤖 *AG* oi');
assert.strictEqual(tag('🤖 Zé disse no site'), '🤖 *AG* Zé disse no site', "the site's 🤖 folds into the tag");
assert.strictEqual(toJid('+55 51 90000-0001'), '5551900000001@s.whatsapp.net');
assert.strictEqual(findAvisos({ a: { id: 'a@g.us', subject: 'BioFut ⚽' }, b: { id: 'b@g.us', subject: 'BIOFUT - Avisos' } }), 'b@g.us');
assert.strictEqual(findAvisos({ a: { id: 'a@g.us', subject: 'Avisos do condomínio' } }), undefined);
const list = '🚨 [QUINTA - 19/03 18:30]🚨\n💰 12 pilas\n\nGoleiro 1 - Zeca\n1 - Tito ✅\n2 - Beto\n3 - Juca\n4 -';
assert.ok(isList(list) && !isList('bora [19/03]?') && !isList(list.replace('19/03', 'quinta')), 'only sign-up lists go to the site');

// before the draft: every known captain; during it: only that week's captains; never the player himself
assert.strictEqual(join({ player: 'Zé', count: 3, captains: [] }, cfg).length, 2);
const out = join({ player: 'Zé', count: 3, captains: ['victor', 'Fulano'] }, cfg);
assert.deepStrictEqual(out, [{ to: '5551900000001@s.whatsapp.net', text: `⚽ Zé entrou no draft pelo site (3 confirmados). ${url}` }]);
assert.ok(join({ player: 'Bia', count: 3, captains: ['Victor', 'Canova'], pending: true }, cfg)[0].text.startsWith('⚽ Bia quer entrar com o draft rolando (3 confirmados). Se os dois capitães aceitarem'));
assert.strictEqual(join({ player: 'Canova', captains: [] }, cfg).length, 1);
assert.throws(() => join({ player: '  ' }, cfg));
// list captains ('Ana (C)') found in the group directory get the DM; an empty captain list never reaches the whole group
{ const { withCaptains, pick } = require('./bot.js'), dirx = [{ name: 'Ana', phone: '5551988887777' }, { name: 'Rui', phone: '5551966665555' }];
  assert.deepStrictEqual(join({ player: 'Zé', captains: ['ana'] }, withCaptains({ captains: ['ana'] }, cfg, dirx)).map((m) => m.to), ['5551988887777@s.whatsapp.net']);
  assert.strictEqual(join({ player: 'Zé', captains: [] }, withCaptains({ captains: [] }, cfg, dirx)).length, cfg.captains.length);
  assert.deepStrictEqual(pick({ captain: 'Ana', player: 'Zé', turn: 'Rui', teams: { Ana: ['Ana', 'Zé'], Rui: ['Rui'] } }, withCaptains({ teams: { Ana: [], Rui: [] } }, cfg, dirx)).map((m) => m.to), ['5551966665555@s.whatsapp.net']); }

// site login: the DM carries the code on its own bold line
assert.match(loginAsk('0420'), /\n\*0420\*\n/);

// webhook, dry-run
const dir = __dirname;
for (const f of ['outbox.jsonl']) fs.rmSync(path.join(dir, f), { force: true });
const srv = spawn(process.execPath, ['bot.js'], { cwd: dir, env: { ...process.env, BIOFUT_BOT_TOKEN: 't', BIOFUT_BOT_CONFIG: 'config.example.json' } });
srv.stdout.once('data', async () => {
  try {
    const post = (url, body, token = 't') => fetch(`http://127.0.0.1:8787${url}`, {
      method: 'POST', headers: { 'x-biofut-token': token, 'content-type': 'application/json' }, body: JSON.stringify(body),
    });
    assert.strictEqual((await post('/draft/join', { player: 'Zé' }, 'wrong')).status, 401);
    const r = await post('/draft/join', { player: 'Zé', count: 1, captains: [] });
    assert.deepStrictEqual(await r.json(), { ok: true, notified: 2 });
    const lines = fs.readFileSync(path.join(dir, 'outbox.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
    assert.strictEqual(lines.length, 2);
    assert.strictEqual(lines[0].to, '5551900000001@s.whatsapp.net');
    assert.match(lines[0].text, /^🤖 \*AG\* ⚽ Zé entrou/u);
    assert.strictEqual((await post('/draft/join', {})).status, 400);
    const p = await post('/draft/pick', { captain: 'Zé', player: 'Bia', turn: 'Victor', teams: { 'Zé': ['Zé', 'Bia'], Victor: ['Victor'] }, available: ['Leo', 'Dan'] });
    assert.deepStrictEqual(await p.json(), { ok: true, notified: 1 });
    const pl = fs.readFileSync(path.join(dir, 'outbox.jsonl'), 'utf8').trim().split('\n').map(JSON.parse).pop();
    assert.strictEqual(pl.to, '5551900000001@s.whatsapp.net');
    assert.match(pl.text, /Zé escolheu Bia\.\n\nTime Zé: Zé, Bia\nTime Victor: Victor\n\nSobram: Leo, Dan\n\nTua vez! /);
    assert.strictEqual((await post('/draft/pick', { captain: 'Zé' })).status, 400);
    const last = require('./bot.js').pick({ captain: 'Zé', player: 'Leo', turn: 'Zé', teams: { 'Zé': ['Zé', 'Bia', 'Leo'], Victor: ['Victor'] }, available: [] }, cfg);  // the other captain (Victor) is in cfg
    assert.match(last[0].text, /Sobram: ninguém\n\nAcabou! Confirma teu time: /, 'nobody left: confirm, not "your turn"');
    const out = async (b) => { assert.deepStrictEqual(await (await post('/group', b)).json(), { ok: true }); return fs.readFileSync(path.join(dir, 'outbox.jsonl'), 'utf8').trim().split('\n').map(JSON.parse).pop().text; };
    assert.match(await out({ text: '🤖 oi' }), /^🤖 \*AG\* oi$/u);
    assert.strictEqual(await out({ text: '🤖 [19/03]\n7 - Kiko', raw: true }), '🤖 [19/03]\n7 - Kiko', 'raw: the site sign-up list, never tagged');

    assert.strictEqual((await post('/notify', { text: 'oi' })).status, 503, 'no avisosJid in the example config');
    assert.strictEqual((await post('/notify', { text: 'oi' }, 'wrong')).status, 401);
    const L = { id: 'abcdefghijklmnopqrstuv', phone: '5551900000003', code: '0420' };
    assert.strictEqual((await post('/login', { ...L, phone: '12' })).status, 400);
    assert.deepStrictEqual(await (await post('/login', L)).json(), { ok: true });
    assert.match(fs.readFileSync(path.join(dir, 'outbox.jsonl'), 'utf8'), /"to":"5551900000003@s.whatsapp.net".*\*0420\*/);
    console.log('all tests passed');
  } catch (e) { console.error(e); process.exitCode = 1; }
  srv.kill();
  for (const f of ['outbox.jsonl']) fs.rmSync(path.join(dir, f), { force: true });
});
