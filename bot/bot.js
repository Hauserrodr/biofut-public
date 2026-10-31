/**
 * bot.js - BioFut WhatsApp bot: draft commands + captain notifications.
 *
 * Dry-run by default: every outgoing message is appended to outbox.jsonl, nothing is sent.
 * Live (--live) runs on Gab's own number as an extra linked device (Gab, 2026-10-05: no SIM,
 * the bot speaks as him, every message tagged with PREFIX, the bot "ESQUIZOBOT"). It uses its own session dir and
 * refuses the read-only ingest session (~/.whatsapp-secrets). Live answers only in cfg.groupJid.
 *
 * Site -> bot contract (site/server.py calls this on every new sign-up):
 *   POST http://127.0.0.1:<PORT>/draft/join
 *   header  X-BioFut-Token: <BIOFUT_BOT_TOKEN>
 *   body    {"player": "Fulano", "count": 7, "captains": ["Victor", "Canova"]}
 *   -> 200 {"ok":true,"notified":K}  (401 bad token). captains = the site draft's captains ([] before the draft);
 *   their phones come from cfg.captains (name -> phone); with no draft yet every cfg.captains entry is told.
 *   POST /draft/pick (same header) {"captain", "player", "turn", "teams": {cap: [names]}, "available": [names]}: a site
 *   pick. DMs the other captain the teams so far, who is still free and whose turn it is. -> 200 {"ok":true,"notified":K}.
 *   POST /login (same header) {"id", "phone", "code"}: site login. 404 if the number is not in cfg.groupJid; else DMs
 *   the member the code, which the member types on the site (server.py login_code checks it).
 *   POST /group (same header) {"text": "..."} posts to cfg.groupJid, tagged when it starts with 🤖, else as is (the list to copy).
 *   {"text", "raw": true} is never tagged: a site sign-up's list, which the group copies and the bot must keep reading.
 *   POST /notify (same header) {"text": "..."} posts to cfg.avisosJid, the "BioFut Avisos" group
 *   (pipeline news: wiki proposals, súmulas, approvals). Live, an empty avisosJid is filled by itself with the
 *   group whose name matches "BioFut Avisos" (Gab only has to create it). 503 until there is one.
 * The list itself lives on the site: !lista and !capitaes read <siteUrl>/api/state.
 * Bot -> site: every image posted in cfg.groupJid goes to cfg.sumulaUrl (default the site's /api/sumula_image on the
 *   same host), same token. The site reads it with DeepSeek and queues real match sheets for review.
 *   Every group text that looks like the sign-up list goes to /api/lista on that host {"text", "ts", "sender", "phone"}:
 *   the site fills Jogo da semana from it and keeps only the poster's tabela name (the list's owner), never the number.
 *
 * Usage:
 *   node bot.js                 dry-run server (outbox.jsonl)
 *   node bot.js --say "!lista"  print the reply to one command (reads the live site)
 *   node bot.js --live          real WhatsApp (QR in <session>/qr.png on first run)
 * Config: config.json (copy config.example.json). Env: BIOFUT_BOT_TOKEN, BIOFUT_BOT_SESSION.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');

const HERE = __dirname;
const OUTBOX = path.join(HERE, 'outbox.jsonl');

function loadConfig() {
  const p = process.env.BIOFUT_BOT_CONFIG || (fs.existsSync(path.join(HERE, 'config.json')) ? 'config.json' : 'config.example.json');
  return JSON.parse(fs.readFileSync(path.join(HERE, p), 'utf8'));
}

// the site's public state: {match: {date, confirmed, draft: {captains, teams} | null}}
async function siteState(cfg) {
  try {
    const r = await fetch(`${cfg.siteUrl.replace(/\/$/, '')}/api/state`, { signal: AbortSignal.timeout(8000) });
    return (await r.json()).match;
  } catch { return null; }
}

// every outgoing message is tagged so the group knows it is the bot, not the admin typing. The bot is "ESQUIZOBOT"
// (2026-10-26): change it here, the one place. *bold* in WhatsApp. A site text's own leading
// 🤖 (server.py group_post: "tag this") folds into the tag.
const PREFIX = '🤖 *ESQUIZOBOT*';
const tag = (text) => `${PREFIX} ${String(text).replace(/^🤖\s*/u, '')}`;
// a picture the site sends as base64 (/group images): JPEG or PNG only
const isPic = (buf) => buf.length > 8 && (buf.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff])) || buf.subarray(0, 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47])));
// the admin group Gab creates: "BioFut Avisos", "biofut avisos", "BIOFUT - avisos"... (groups: {jid: {id, subject}})
const findAvisos = (groups) => Object.values(groups || {}).find((g) => /bio\s*fut.*avisos/i.test(g.subject || ''))?.id;
const tagged = (transport, cfg) => ({ ...transport, raw: transport.send, send: (to, text, image) => transport.send(to, tag(text), image) });
// "cancelado" / "jogo cancelado hoje" in the group on the game's day -> the site gives the bets back. A question is not a call.
const isCancel = (text) => /\bcancelad[ao]\b/i.test(String(text || '')) && String(text).length < 120 && !/\?/.test(text);

const toJid = (phone) => phone.includes('@') ? phone : `${phone.replace(/\D/g, '')}@s.whatsapp.net`;

// ---------------------------------------------------------------- pure logic
const draftUrl = (cfg) => `${cfg.siteUrl.replace(/\/$/, '')}/#/jogo`;

// m = site match state (null if the site is down)
function reply(text, cfg, m) {
  const cmd = (text || '').trim().split(/\s+/)[0].toLowerCase();
  const url = draftUrl(cfg);
  const off = `Site fora do ar agora, tenta direto: ${url}`;
  switch (cmd) {
    case '!draft': return `⚽ Draft da semana${m?.date ? ` (${m.date})` : ''}: ${url}`;
    case '!entrar': return `Confirma tua presença no site (nome + "Tô dentro"): ${url}`;
    case '!lista':
      if (!m) return off;
      return m.confirmed.length
        ? `Confirmados (${m.confirmed.length}):\n` + m.confirmed.map((p, i) => `${i + 1}. ${p}`).join('\n') + `\n${url}`
        : `Ninguém confirmou ainda. ${url}`;
    case '!times':
      if (!m) return off;
      if (!m.draft) return `Draft ainda não começou. ${url}`;
      return m.draft.captains.map((c) => `Time ${c}: ${m.draft.teams[c].join(', ')}`).join('\n') + `\n${url}`;
    case '!capitaes':
      if (!m) return off;
      return m.draft ? `Capitães: ${m.draft.captains.join(' x ')}` : `Capitães ainda não escolhidos. ${url}`;
    case '!ajuda': return '!draft link do draft\n!entrar como confirmar presença\n!lista quem já confirmou\n!capitaes capitães da semana\n!times times do draft';
    default: return null; // ponytail: not a command, stay silent in the group
  }
}

// The captains come from the site (the list's '(C)'); their numbers from the group's directory, cfg.captains as an override.
// Only the captains this message names: an empty list never DMs the whole group.
function withCaptains(body, cfg, dir) {
  const named = (body.captains?.length ? body.captains : Object.keys(body.teams || {})).map((c) => String(c).toLowerCase());
  const known = cfg.captains.map((c) => c.name.toLowerCase());
  return { ...cfg, captains: [...cfg.captains, ...dir.filter((d) => named.includes(d.name.toLowerCase()) && !known.includes(d.name.toLowerCase()))] };
}

// site sign-up -> [{to, text}] for the draft's captains (all known captains before the draft starts)
function join(body, cfg) {
  const name = String(body.player || '').trim().slice(0, 60);
  if (!name) throw new Error('player required');
  const caps = (body.captains || []).map((c) => String(c).toLowerCase());
  const to = caps.length ? cfg.captains.filter((c) => caps.includes(c.name.toLowerCase())) : cfg.captains;
  const count = Number.isInteger(body.count) ? ` (${body.count} confirmados)` : '';
  const text = body.pending  // the draft is running: both captains must accept, then the draft restarts
    ? `⚽ ${name} quer entrar com o draft rolando${count}. Se os dois capitães aceitarem, o draft recomeça: ${draftUrl(cfg)}`
    : `⚽ ${name} entrou no draft pelo site${count}. ${draftUrl(cfg)}`;
  return to.filter((c) => c.phone && c.name.toLowerCase() !== name.toLowerCase()).map((c) => ({ to: toJid(c.phone), text }));
}

// a site pick -> the captain who did not pick gets the board; ponytail: one DM per pick, no batching
function pick(body, cfg) {
  const name = (v) => String(v || '').trim().slice(0, 60);
  const captain = name(body.captain), player = name(body.player), turn = name(body.turn);
  const teams = body.teams && typeof body.teams === 'object' ? body.teams : {};
  const caps = Object.keys(teams);
  if (!captain || !player || caps.length !== 2) throw new Error('captain, player, teams required');
  const other = caps.find((c) => c.toLowerCase() !== captain.toLowerCase());
  const avail = (Array.isArray(body.available) ? body.available : []).map(name).filter(Boolean);
  const text = `⚽ ${captain} escolheu ${player}.\n\n` + caps.map((c) => `Time ${c}: ${teams[c].join(', ')}`).join('\n') +
    `\n\nSobram: ${avail.length ? avail.join(', ') : 'ninguém'}\n\n` +
    (!avail.length ? 'Acabou! Confirma teu time: ' : turn.toLowerCase() === other.toLowerCase() ? 'Tua vez! ' : `Vez de ${turn} de novo. `) + draftUrl(cfg);
  return cfg.captains.filter((c) => c.phone && c.name.toLowerCase() === other.toLowerCase()).map((c) => ({ to: toJid(c.phone), text }));
}

// ---------------------------------------------------------------- site login by WhatsApp
const bare = (jid) => String(jid || '').replace(/:\d+(?=@)/, ''); // drop the device suffix
// a group text that may be the weekly sign-up list ("[QUINTA - 19/03 18:30]" up top, a numbered slot per line); the site parses it
const isList = (text) => /\[[^\]\n]{0,30}\d{1,2}\/\d{1,2}/.test(String(text).slice(0, 200)) && String(text).split('\n').length > 6;
// the code on a line of its own: the site doesn't show it, the member types it there
const loginAsk = (code) => `Seu código para entrar no site do BioFut:\n\n*${code}*\n\n` +
  'Digite no site. Vale 10 minutos. Se não foi você, ignore esta mensagem e não passe o código para ninguém.';

// ---------------------------------------------------------------- transports
const dryRun = {
  async send(to, text, image) {
    const img = Buffer.isBuffer(image) ? `bytes:${image.length}` : image;
    fs.appendFileSync(OUTBOX, JSON.stringify({ ts: new Date().toISOString(), to, text, ...(img && { image: img }) }) + '\n');
  },
  async poll(to, name, values) {
    fs.appendFileSync(OUTBOX, JSON.stringify({ ts: new Date().toISOString(), to, poll: { name, values } }) + '\n');
  },
  async lookup(phone) { return [toJid(phone)]; }, // no group to check offline
};

async function liveTransport(cfg, onText) {
  const session = process.env.BIOFUT_BOT_SESSION || path.join(os.homedir(), '.biofut-bot-secrets', 'session');
  if (path.resolve(session).toLowerCase().includes('.whatsapp-secrets'))
    throw new Error("refusing the read-only ingest session; link the bot as its own device (BIOFUT_BOT_SESSION)");
  if (!cfg.groupJid) throw new Error("set groupJid in config.json: the bot runs on Gab's number and must only answer in the BioFut group");
  fs.mkdirSync(session, { recursive: true });
  let dirCache = null;  // directory(): the group's numbers -> names
  // own node_modules on the A1 (Docker); locally falls back to the whatsapp-ingest install
  const { createRequire } = require('module');
  let req = require;
  try { require.resolve('@whiskeysockets/baileys'); } catch { req = createRequire(cfg.baileysFrom || 'C:/dev/life-plan/scripts/whatsapp-ingest/package.json'); }
  const b = req('@whiskeysockets/baileys');
  const QR = req('qrcode');
  const { state, saveCreds } = await b.useMultiFileAuthState(session);
  const quiet = { level: 'warn', child() { return this; }, trace() {}, debug() {}, info() {}, warn: console.warn, error: console.error };
  const phone = (process.env.BIOFUT_BOT_PHONE || '').replace(/\D/g, '');
  let sock, asked = false, avatarsAt = 0;
  const avatarsDaily = () => { if (sock?.user && Date.now() - avatarsAt > 864e5) { avatarsAt = Date.now(); syncAvatars(sock, cfg); } };
  setInterval(avatarsDaily, 36e5);
  const useAvisos = (groups) => {
    const jid = findAvisos(Array.isArray(groups) ? Object.fromEntries(groups.map((g) => [g.id, g])) : groups);
    if (jid) { cfg.avisosJid = jid; console.log(`avisos group: ${jid}`); }
  };
  const connect = () => {
    sock = (b.default || b.makeWASocket)({ auth: state, logger: quiet, markOnlineOnConnect: false });
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('groups.upsert', (gs) => { if (!cfg.avisosJid) useAvisos(gs); });  // Gab created the group while the bot runs
    sock.ev.on('connection.update', ({ connection, qr, lastDisconnect }) => {
      if (qr) QR.toFile(path.join(path.dirname(session), 'qr.png'), qr).catch(() => {});
      // headless link: WhatsApp > Linked devices > Link with phone number, type this code
      if (qr && phone && !asked) { asked = true; sock.requestPairingCode(phone).then((c) => console.log(`PAIRING CODE: ${c}`), (e) => console.error('pairing code failed:', e.message)); }
      if (connection === 'open') {
        console.log('bot connected');
        avatarsDaily();
        if (!cfg.avisosJid) sock.groupFetchAllParticipating().then(useAvisos, (e) => console.error('group list failed:', e.message));
      }
      if (connection !== 'close') return;
      const code = lastDisconnect?.error?.output?.statusCode;
      // Unpaired session: requestPairingCode already wrote creds.me, so a reconnect would try to log in and stall.
      // Wipe it and exit; Docker's restart policy starts fresh with a new PAIRING CODE.
      if (!state.creds.registered && !state.creds.account) { // account is set by pair-success (QR or code)
        console.log(`not linked yet (close ${code}); new pairing code on restart`);
        fs.rmSync(session, { recursive: true, force: true });
        process.exit(1);
      }
      console.log(`connection closed (${code})`);
      if (code !== b.DisconnectReason.loggedOut) return connect();
      // Logged out (the linked device was removed, 2026-10-26): it never comes back by itself. Keep the dead session
      // aside and exit; Docker's restart policy starts in pairing mode (a new PAIRING CODE in the log).
      fs.renameSync(session, `${session}.dead-${Date.now()}`);
      process.exit(1);
    });
    sock.ev.on('messages.upsert', ({ messages, type }) => {
      if (type !== 'notify') return;
      for (const m of messages) {
        // the bot's own pictures (the tabela check, tagged captions) are not súmulas
        if (m.message?.imageMessage && m.key.remoteJid === cfg.groupJid && !String(m.message.imageMessage.caption || '').startsWith(PREFIX)) forwardImage(b, m, cfg);
        const text = m.message?.conversation || m.message?.extendedTextMessage?.text;
        const chat = m.key.remoteJid;
        // fromMe is allowed: the bot is Gab's number, so Gab's own !commands count. Its tagged replies are skipped (no loop).
        if (!text || text.startsWith(PREFIX)) continue;
        if (chat !== cfg.groupJid) continue; // only the BioFut group, never Gab's private chats
        onText(chat, text);
        // the poster's phone JID (Baileys 7: participant may be a LID, its phone JID is then participantAlt)
        const who = m.key.fromMe ? sock.user?.id : [m.key.participant, m.key.participantAlt].find((j) => String(j).endsWith('@s.whatsapp.net'));
        if (isList(text)) forwardList(m, text, who, cfg);
        else if (isCancel(text)) toSite('/api/cancelado', { ts: Number(m.messageTimestamp), sender: m.pushName || '', phone: who ? bare(who).split('@')[0] : '' }, cfg);;
      }
    });
  };
  connect();
  setTimeout(() => t.directory(), 60e3);  // warm: the site hashes every number once, ~seconds
  const t = {
    // image: a URL on the site (the SuperCopa countdown, 2026-10-26), Baileys fetches it, or the bytes (the tabela check);
    // the text becomes its caption
    up: () => Boolean(sock?.user && sock.ws?.isOpen),  // /health: linked and the socket open
    send: (to, text, image) => sock.sendMessage(to, image ? { image: Buffer.isBuffer(image) ? image : { url: image }, caption: text } : { text }),
    poll: (to, name, values) => sock.sendMessage(to, { poll: { name, values, selectableCount: 0 } }),  // 0: any number of choices
    // the group's members as [{name, phone}]: their numbers, named by the site. ponytail: memory only, rebuilt every 6 h
    async directory() {
      if (dirCache && Date.now() - dirCache.at < 6 * 3600e3) return dirCache.list;
      try {
        const { participants } = await sock.groupMetadata(cfg.groupJid);
        const phones = participants.map((p) => [p.phoneNumber, p.id].find((j) => String(j).endsWith('@s.whatsapp.net')))
          .filter(Boolean).map((j) => bare(j).split('@')[0]);
        const r = await fetch(new URL('/api/nomes', cfg.sumulaUrl || 'http://127.0.0.1:8013/'), {
          method: 'POST', headers: { 'content-type': 'application/json', 'x-biofut-token': process.env.BIOFUT_BOT_TOKEN || '' },
          body: JSON.stringify({ phones }), signal: AbortSignal.timeout(60000) });
        const { names } = await r.json();
        dirCache = { at: Date.now(), list: Object.entries(names || {}).map(([phone, name]) => ({ name, phone })) };
        console.log(`directory: ${dirCache.list.length} of ${phones.length} members named`);
      } catch (e) { console.warn('directory failed:', e.message); return dirCache?.list || []; }
      return dirCache.list;
    },
    // phone -> [phone JID, LID] if that WhatsApp is in the BioFut group, else null
    async lookup(phone) {
      const [r] = await sock.onWhatsApp(phone);
      if (!r?.exists) return null;
      const pn = bare(r.jid);
      const lid = await sock.signalRepository.lidMapping.getLIDForPN(pn).catch(() => null);
      const ids = [pn, lid && bare(lid)].filter(Boolean);
      const { participants } = await sock.groupMetadata(cfg.groupJid);
      return participants.some((p) => [p.id, p.phoneNumber, p.lid].some((j) => j && ids.includes(bare(j)))) ? ids : null;
    },
  };
  return t;
}

// Group photo -> site OCR. Fire and forget: a failed forward is logged, never crashes the bot.
async function forwardImage(b, m, cfg) {
  try {
    const img = await b.downloadMediaMessage(m, 'buffer', {});
    const date = new Date(Number(m.messageTimestamp) * 1000).toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' });
    const r = await fetch(cfg.sumulaUrl || 'http://127.0.0.1:8013/api/sumula_image', {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-biofut-token': process.env.BIOFUT_BOT_TOKEN || '' },
      body: JSON.stringify({ image: img.toString('base64'), date, sender: m.pushName || '' }) });
    if (!r.ok) console.warn('sumula forward:', r.status, await r.text());
  } catch (e) { console.warn('sumula forward failed:', e.message); }
}

// #35: the group members' WhatsApp profile photos -> the site (members-only, cards without an uploaded photo), once a day.
// The site keeps a photo only for a number it can name; the number itself is not stored.
async function syncAvatars(sock, cfg) {
  let n = 0;
  try {
    const { participants } = await sock.groupMetadata(cfg.groupJid);
    for (const p of participants) {
      const jid = [p.phoneNumber, p.id].find((j) => String(j).endsWith('@s.whatsapp.net'));
      const url = jid && await sock.profilePictureUrl(jid, 'image').catch(() => null); // null: no photo, or hidden from Gab
      if (!url) continue;
      const image = Buffer.from(await (await fetch(url, { signal: AbortSignal.timeout(15000) })).arrayBuffer()).toString('base64');
      const r = await fetch(new URL('/api/avatar', cfg.sumulaUrl || 'http://127.0.0.1:8013/'), {
        method: 'POST', headers: { 'content-type': 'application/json', 'x-biofut-token': process.env.BIOFUT_BOT_TOKEN || '' },
        body: JSON.stringify({ phone: bare(jid).split('@')[0], image }) });
      if (r.ok && (await r.json()).ok) n++;
      await new Promise((ok) => setTimeout(ok, 2000)); // ponytail: one every 2 s, gentle on WhatsApp's rate limits
    }
  } catch (e) { console.warn('avatars failed:', e.message); }
  console.log(`avatars: ${n} sent to the site`);
}

// Group sign-up list -> the site's Jogo da semana, same way. The number only finds the poster's name; the site keeps the name.
const forwardList = (m, text, jid, cfg) =>
  toSite('/api/lista', { text, ts: Number(m.messageTimestamp), sender: m.pushName || '', phone: jid ? bare(jid).split('@')[0] : '' }, cfg);

async function toSite(path, body, cfg) {
  try {
    const r = await fetch(new URL(path, cfg.sumulaUrl || 'http://127.0.0.1:8013/'), {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-biofut-token': process.env.BIOFUT_BOT_TOKEN || '' },
      body: JSON.stringify(body) });
    if (!r.ok) console.warn(path, r.status, await r.text());
  } catch (e) { console.warn(path, 'failed:', e.message); }
}

// ---------------------------------------------------------------- server
function serve(cfg, transport) {
  const token = process.env.BIOFUT_BOT_TOKEN;
  if (!token) throw new Error('set BIOFUT_BOT_TOKEN (shared secret with the site)');
  return http.createServer((req, res) => {
    const done = (code, obj) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(obj)); };
    if (req.method !== 'POST') return done(404, { ok: false });
    if (req.headers['x-biofut-token'] !== token) return done(401, { ok: false, error: 'bad token' });
    let body = '';
    req.on('data', (c) => { body += c; if (body.length > 20e6) req.destroy(); });  // 20 MB: /group images, a few photos in base64
    req.on('end', async () => {
      try {
        if (req.url === '/health') return done(200, { ok: true, up: transport.up ? transport.up() : true });  // the site asks every 10 min
        if (req.url === '/group') {
          const o = JSON.parse(body || '{}'), text = String(o.text || '').trim().slice(0, 4000);
          if (!text) return done(400, { ok: false, error: 'text required' });
          const image = o.image ? String(o.image) : undefined;  // optional picture URL (2026-10-26), the text is its caption
          if (image && !/^https?:\/\/\S+$/.test(image)) return done(400, { ok: false, error: 'image must be a URL' });
          // the tabela check (2026-10-26): pictures as base64 {data, caption} after the text, then a multiple-choice poll
          const images = (Array.isArray(o.images) ? o.images : []).slice(0, 4)
            .map((i) => ({ data: Buffer.from(String(i?.data || ''), 'base64'), caption: String(i?.caption || '').slice(0, 200) }));
          if (images.some((i) => !isPic(i.data))) return done(400, { ok: false, error: 'images: JPEG or PNG in base64' });
          const poll = o.poll && { name: String(o.poll.name || '').slice(0, 255), values: (Array.isArray(o.poll.values) ? o.poll.values : []).map(String).slice(0, 12) };
          if (poll && (!poll.name || poll.values.length < 2)) return done(400, { ok: false, error: 'poll: name and 2-12 values' });
          await (text.startsWith('🤖') && !o.raw ? transport.send : transport.raw || transport.send)(cfg.groupJid, text, image);
          for (const i of images) await transport.send(cfg.groupJid, i.caption, i.data);
          if (poll) await transport.poll(cfg.groupJid, poll.name, poll.values);
          return done(200, { ok: true });
        }
        if (req.url === '/notify') {
          const o = JSON.parse(body || '{}'), text = String(o.text || '').trim().slice(0, 2000);
          if (!text) return done(400, { ok: false, error: 'text required' });
          const image = o.image ? String(o.image) : undefined;  // the day's Instagram story to post by hand (2026-10-26)
          if (image && !/^https?:\/\/\S+$/.test(image)) return done(400, { ok: false, error: 'image must be a URL' });
          if (!cfg.avisosJid) return done(503, { ok: false, error: 'set avisosJid in config.json' });
          await transport.send(cfg.avisosJid, text, image);
          return done(200, { ok: true });
        }
        if (req.url === '/login') {
          const { id, phone, code } = JSON.parse(body || '{}');
          if (!/^[\w-]{16,64}$/.test(id || '') || !/^\d{10,15}$/.test(phone || '') || !/^\d{4}$/.test(code || ''))
            return done(400, { ok: false, error: 'id, phone, code' });
          const jids = await transport.lookup(phone);
          if (!jids) return done(404, { ok: false, error: 'esse número não está no grupo do BioFut' });
          await transport.send(jids[0], loginAsk(code));
          return done(200, { ok: true });
        }
        if (req.url === '/dm') {  // one tagged message to one member, sent by the admin by hand (2026-10-31)
          const { phone, text } = JSON.parse(body || '{}'), t = String(text || '').trim().slice(0, 2000);
          if (!/^\d{10,15}$/.test(phone || '') || !t) return done(400, { ok: false, error: 'phone, text' });
          const jids = await transport.lookup(phone);
          if (!jids) return done(404, { ok: false, error: 'esse número não está no grupo do BioFut' });
          await transport.send(jids[0], t);
          return done(200, { ok: true });
        }
        if (req.url !== '/draft/join' && req.url !== '/draft/pick') return done(404, { ok: false });
        const b = JSON.parse(body || '{}');
        const dir = (b.captains?.length || b.teams) && transport.directory ? await transport.directory() : [];
        const out = (req.url === '/draft/pick' ? pick : join)(b, withCaptains(b, cfg, dir));
        for (const m of out) await transport.send(m.to, m.text);
        done(200, { ok: true, notified: out.length });
      } catch (e) { done(400, { ok: false, error: e.message }); }
    });
  }).listen(cfg.port || 8787, '127.0.0.1', () => console.log(`bot webhook on 127.0.0.1:${cfg.port || 8787}`));
}

if (require.main === module) {
  const cfg = loadConfig();
  const args = process.argv.slice(2);
  if (args[0] === '--say') { siteState(cfg).then((m) => console.log(reply(args[1], cfg, m) ?? '(no reply)')); return; }
  (async () => {
    let transport = tagged(dryRun, cfg);
    if (args.includes('--live')) {
      transport = tagged(await liveTransport(cfg, async (chat, text) => {
        if (reply(text, cfg, null) === null) return; // not a command: don't hit the site
        const r = reply(text, cfg, await siteState(cfg));
        if (r) transport.send(chat, r);
      }), cfg);
    }
    serve(cfg, transport);
  })().catch((e) => { console.error(e.message); process.exit(1); });
}

module.exports = { PREFIX, reply, join, pick, toJid, tag, findAvisos, loginAsk, isList, syncAvatars, withCaptains };
