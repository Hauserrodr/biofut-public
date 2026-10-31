// ---------- Corre, Saul! (#/corre), a member's idea (2026-10-30): Saul runs to the Planet Ball before the 18:30 game.
// index.html loads this file on the first visit (bindCorre) and calls Corre(). It uses the page's globals: ST, D, ME, CARDS, face,
// slug, av, pname, esc, coin, rankList, post, setState, toast, store, ui, BF, $, SOMBRAS. The server keeps records, upgrades and
// coins (server.py corre_act); a visitor runs as SOMBRAS. Everyone runs the same street on the same day: the course comes from
// the Brasília date. Everything but the title lives in the game window: the canvas, the pad and the menus over them.
"use strict";
window.Corre = (() => {
  const K = {len: 12000, t0: 18 * 3600 + 20 * 60, k: 15, gol: 18 * 3600 + 30 * 60, rei: [6800, 10800]};  // same clock as server.py CORRE_*
  const spd = p => 220 + 300 * p, KMH = .05;  // street units per second at p of the way (slow start, faster near the Planet); km/h per unit/s
  const UP = {  // costs come from the server (ST.corre_up)
    chuteira: ["👟", "Chuteira nova", "Pula mais alto"],
    folego: ["🫁", "Fôlego", "+1 tropeço antes do jogo canelado"],
    cuia: ["🧉", "Cuia térmica", "O chimarrão dura mais"],
    ima: ["🧲", "Ímã de pilas", "Puxa as pilas de longe"],
  };
  const ACH = [  // [id, name, how, hidden until found]; ids match server.py CORRE_ACH
    ["pontual", "Pontual", "Chegue no Planet até 18:30"],
    ["limpo", "Sem tropeço", "Chegue sem tropeçar"],
    ["rei", "Rei deposto", "Derrube o BioFut King"],
    ["lista", "Na lista", "Junte L-I-S-T-A numa corrida", 1],
    ["saulnaro", "Saulnaro", "Faça o L três vezes numa corrida", 1],
    ["raspando", "Raspando", "5 pulos no último instante numa corrida", 1],
    ["tabelinha", "Tabelinha", "Chute uma bola que derrube um obstáculo", 1],
    ["minhoca", "Jogada de minhoca", "Deslize por baixo de 3 cornetadas do King", 1],
    ["pagou", "Pagou o jogo", "Chegue com 12 pilas ou mais", 1],
    ["devedor", "Devedor", "Chegue sem nenhuma pila", 1],
    ["apito", "No apito", "Chegue entre 18:29:55 e 18:30:00", 1],
    ["esquizo", "Esquizofut", "Toque na lua 3 vezes numa corrida", 1],
    ["pulinho", "Pulinho", "Passe 5 obstáculos com pulos curtinhos numa corrida"],
    ["canguru", "Canguru", "3 pulos bem altos numa corrida (segure ou deslize o dedo longe)"],
    ["carrinho", "Carrinho", "3 deslizes longos numa corrida (segure ↓)"],
    ["mergulho", "Mergulho", "5 vezes do alto direto para o chão deslizando", 1],
    ["voadora", "Voadora", "Devolva a bola do King lá do alto", 1],
  ];
  const LETRAS = [[1500, "L"], [3300, "I"], [4800, "S"], [6300, "T"], [11300, "A"]], AMIGOS = [2500, 5500, 10950];
  const ELES = [[1950, "Saulnaro fez o L?!"], [5150, "De novo, Saulnaro?"], [11650, "SAULNARO VIROU A CASACA!"]];  // the group's Faz o L sticker, for Leo
  const FIX = [...LETRAS.map(([x]) => x), ...AMIGOS, ...ELES.map(([x]) => x)];  // where the fixed pickups stand: no obstacle right there
  const SIZE = {cone: [22, 30], lixo: [30, 44], poca: [64, 6], pipoca: [56, 50], pombo: [26, 14], faixa: [74, 270], sombra: [24, 56], bola: [14, 14],
    pila: [12, 16], cuia: [18, 22], letra: [20, 22], amigo: [24, 62], kbola: [16, 16], corneta: [24, 34], alta: [16, 16], ele: [26, 26]};
  const HURT = new Set(["cone", "lixo", "poca", "pipoca", "pombo", "faixa", "sombra", "kbola", "corneta", "alta"]);
  const GROUND = new Set(["cone", "lixo", "pipoca", "sombra", "poca"]);  // what a kicked ball knocks down
  const FAIXAS = ["LISTA DUPLA", "SUPLÊNCIA", "DEVEDORES", "MENSALISTA", "RESENHA", "SAULNARO 22"];
  const SAUL = {shirt: "#2fae57", trim: "#23864a", num: "77", skin: "#d9a27a", skin2: "#b98463", hair: "#2b1d14", sock: "#f2f2ee", sock2: "#bdbdb6"};  // the green vest
  const KING = {shirt: "#1b1b20", trim: "#f2c230", num: "K", skin: "#c98d63", skin2: "#a87350", hair: "#1a120c", sock: "#1b1b20", sock2: "#121216"};  // the black one
  const N = [["pulos", "pulos"], ["deslizes", "deslizes"], ["chutes", "chutes"], ["tombos", "tropeços"]];  // what a run counts (server.py CORRE_N)

  const clk = s => [s / 3600, s / 60 % 60, s % 60].map(n => String(Math.floor(n)).padStart(2, "0")).join(":");
  const dia = () => new Date(Date.now() - 3 * 3600e3).toISOString().slice(0, 10);  // the group's day, as server.py counts it
  const rng = s => {  // a small seeded generator: the same street for everyone on the same day
    let h = 1779033703 ^ s.length;
    for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 3432918353), h = h << 13 | h >>> 19;
    return () => { h = Math.imul(h ^ h >>> 16, 2246822507); h = Math.imul(h ^ h >>> 13, 3266489909); h ^= h >>> 16; return (h >>> 0) / 4294967296; };
  };
  const rec = () => ST.corre?.[ME] || {best: 0, runs: 0, up: {}, ach: []};
  const lvl = k => ME ? rec().up?.[k] || 0 : 0;
  const local = () => { try { return JSON.parse(store.get("biofutCorre2") || "{}") } catch { return {} } };  // this browser: a visitor's own numbers
  const found = () => new Set([...(ME ? rec().ach : []), ...(local().ach || [])]);
  const nm = n => ST.profiles?.[n]?.nick || n;
  const num = n => Math.round(n || 0).toLocaleString("pt-BR");
  const touch = matchMedia("(pointer:coarse)").matches;
  const tipPool = () => [...(D.glossary || []).map(([k, v]) => ["Dicionário BioFut", k, v]), ...(D.nicknames || []).map(([k, v]) => ["Apelidos", k, v])];

  // ---------- the game window: canvas, pad and the menus over both (dark like the street, in both site themes)
  const CSS = `.corre-wrap{position:relative;margin-top:18px;border-radius:var(--r);overflow:hidden;border:1px solid var(--line);background:#0b0a1a}
#corre{display:block;width:100%;height:clamp(260px,58vw,460px);touch-action:none;cursor:pointer;-webkit-user-select:none;user-select:none;-webkit-tap-highlight-color:transparent}
.corre-pad{display:grid;grid-template-columns:1fr 1.4fr 1fr auto auto;gap:8px;padding:8px;background:#131124}
.corre-pad button{height:50px;min-width:50px;border-radius:12px;border:1px solid #2d2a45;background:#1d1a33;color:#f2f2ee;font:700 15px var(--cond);letter-spacing:.05em;text-transform:uppercase;
  display:flex;align-items:center;justify-content:center;gap:8px;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent;cursor:pointer}
.corre-pad button b{font-size:20px;line-height:1}
.corre-pad button.pri{background:var(--acc);border-color:var(--acc);color:#fff}
.corre-pad button.on{transform:scale(.96);filter:brightness(1.3)}
.corre-pad kbd{font:600 11px var(--body);opacity:.55;text-transform:none;letter-spacing:0}
@media (pointer:coarse){.corre-pad{gap:6px;padding:8px 8px calc(8px + env(safe-area-inset-bottom))}.corre-pad button{height:72px;flex-direction:column;gap:3px;font-size:12px;border-radius:16px}.corre-pad button b{font-size:24px}.corre-pad kbd{display:none}}
.corre-wrap:fullscreen{display:flex;flex-direction:column;border:0;border-radius:0}
.corre-wrap:fullscreen #corre{flex:1;height:auto;min-height:0}
@media (max-width:520px){#corre{height:min(84vw,62vh)}.corre-wrap{margin-left:-16px;margin-right:-16px;border-radius:0;border-left:0;border-right:0}}
.corre-menu{position:absolute;inset:0;z-index:2;display:flex;flex-direction:column;background:rgba(9,8,20,.9);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);
  --bg:#0b0a1a;--card:#16142a;--card2:#1d1a33;--line:#2d2a45;--line2:#3d3960;--ink:#f2f2ee;--mut:#b6b3c6;--dim:#807c96;--acc:#ff4a6e;--acc-ink:#16060a;--gold:#f2c230;--win:#43d17f;color:var(--ink);color-scheme:dark}
.corre-menu[hidden]{display:none}
.corre-tabs{display:flex;gap:4px;padding:8px;border-bottom:1px solid var(--line);overflow-x:auto;scrollbar-width:none;flex:none}
.corre-tabs::-webkit-scrollbar{display:none}
.corre-tabs button{flex:none;height:38px;padding:0 14px;border-radius:10px;border:0;background:none;color:var(--mut);font:700 15px var(--cond);letter-spacing:.04em;text-transform:uppercase;cursor:pointer}
.corre-tabs button[aria-selected=true]{background:var(--card2);color:var(--ink)}
.corre-tabs .x{margin-left:auto;position:sticky;right:0;font-size:20px;color:var(--ink);background:#131124;box-shadow:-10px 0 10px #131124}
@media (max-width:520px){.corre-tabs button{padding:0 9px;font-size:13px}.corre-body{padding:14px 16px 18px}}
.corre-body{flex:1;overflow:auto;overscroll-behavior:contain;padding:18px 18px 22px}
.corre-body h2{font:800 clamp(34px,7vw,56px)/1 var(--cond);letter-spacing:.01em;margin:0}
.corre-body h3{margin:0}
.corre-body .lead{max-width:620px;margin:10px 0 0;color:var(--mut)}
.corre-body .row{margin-top:16px}
.corre-tip{margin-top:18px;font-size:14px;color:var(--mut);border-left:3px solid var(--gold);padding:2px 0 2px 12px;max-width:620px}
.corre-tip b{color:var(--ink)}
.corre-help{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:12px;font-size:14px;color:var(--mut)}.corre-help b{color:var(--ink)}
.corre-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:12px}
.corre-ups{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-top:12px}
.corre-ups .btn{white-space:normal;line-height:1.2;height:auto;min-height:36px;width:100%;justify-content:center;margin-top:auto}
.corre-ups .card{display:flex;flex-direction:column;gap:6px}
.corre-ups .lv{display:flex;gap:4px}.corre-ups .lv i{width:18px;height:6px;border-radius:3px;background:var(--line2)}.corre-ups .lv i.on{background:var(--gold)}
.corre-ach{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-top:12px}
.corre-ach div{border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:13px;color:var(--dim)}
.corre-ach div b{display:block;font:700 15px var(--cond);letter-spacing:.03em;color:var(--mut)}
.corre-ach div.ok{border-color:var(--gold);color:var(--mut)}.corre-ach div.ok b{color:var(--gold)}
.corre-num{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin:10px 0 20px}
.corre-num div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.corre-num b{display:block;font:800 26px/1.05 var(--cond)}.corre-num small{color:var(--mut);font-size:13px}`;
  function page() {
    return `<div class="kicker">Jogar · novo</div><h1 style="font-size:52px;margin-top:8px">Corre, Saul!</h1>
  <div class="corre-wrap" id="correWrap">
    <canvas id="corre" tabindex="0" aria-label="Corre, Saul: toque ou espaço pula, deslize para baixo ou seta para baixo desliza, deslize para a direita ou X chuta"></canvas>
    <div class="corre-pad">
      <button data-k="slide" aria-label="Deslizar"><b>⬇</b>Deslizar <kbd>↓</kbd></button>
      <button data-k="jump" class="pri" aria-label="Pular"><b>⬆</b>Pular <kbd>espaço</kbd></button>
      <button data-k="kick" aria-label="Chutar"><b>⚽</b>Chutar <kbd>X</kbd></button>
      <button data-k="menu" aria-label="Menu e pausa" title="Menu (Esc)"><b>☰</b></button>
      ${document.fullscreenEnabled ? '<button data-k="fs" aria-label="Tela cheia" title="Tela cheia"><b>⛶</b></button>' : ""}
    </div>
    <div class="corre-menu" id="correMenu" hidden></div>
  </div>`;
  }
  const tip = () => {
    const T = tipPool();
    if (!T.length) return "";
    const [src, k, v] = T[Math.floor(Math.random() * T.length)];
    return `<p class="corre-tip"><span class="dim">${src} ·</span> <b>${esc(k)}</b>: ${esc(v)}</p>`;
  };

  // ---------- the game
  let cx;  // the canvas being drawn: the game, or the share card for a moment
  function Corre() {
    if (!document.getElementById("correCss")) document.head.insertAdjacentHTML("beforeend", `<style id="correCss">${CSS}</style>`);
    const pg = $("#correPg");
    if (!pg) return;
    pg.innerHTML = page();
    const cv = $("#corre"), ac = new AbortController(), on = {signal: ac.signal};
    cx = cv.getContext("2d");
    const R0 = rng("cidade");
    const town = Array.from({length: 26}, () => {  // the skyline and its windows once, so they don't flicker
      const w = 44 + R0() * 52, h = 50 + R0() * 100;
      return {w, h, lit: Array.from({length: Math.floor(h / 14) * Math.floor((w - 8) / 11)}, () => R0() < .28)};
    });
    const townW = town.reduce((s, b) => s + b.w + 6, 0);
    const ADS = [["torres", "#f4ecd8"], ["baita", "#eee9e6"], ["duplaface", "#000"]].map(([n, bg]) => {  // the Apoie sponsors, on rooftop billboards
      const im = new Image(); im.src = `/ad-${n}.png`; return {im, bg};
    });
    const faces = {};
    const fresh = () => {
      const d = dia(), R = rng(d), lives = 3 + lvl("folego");
      const pool = CARDS().map(c => c.name).filter(n => !/saul/i.test(n)).sort();
      const fix = [...LETRAS.map(([x, l]) => ({type: "letra", x, l, b: 70 + R() * 30})),
        ...AMIGOS.map(x => ({type: "amigo", x, name: pool.length ? pool[Math.floor(R() * pool.length)] : "", b: 0})),
        ...ELES.map(([x, say]) => ({type: "ele", x, say, b: 40 + R() * 50}))].sort((a, b) => a.x - b.x);
      fix.forEach(o => [o.w, o.h] = SIZE[o.type]);
      return {mode: "pronto", dia: d, R, RK: rng(d + "/king"), x: 0, y: 0, vy: 0, ht: 0, buf: 0, t: 0, lives, max: lives, hits: 0, inv: 0, slow: 1, boost: 0,
        slide: 0, sbuf: 0, kick: 0, kcd: 0, obs: [], fix, next: 700, pts: 0, streak: 0, pilas: 0, letras: "", near: 0, shield: 0, pops: [],
        king: {st: "off", hp: 3, cd: .5, ox: 0, n: 0, minhoca: 0, hit: 0, t: 0}, ach: new Set(), esq: 0, lua: 0, go: false, coins: null, seen: 0, eles: 0, vmax: 0, n: {pulos: 0, deslizes: 0, chutes: 0, tombos: 0},
        jcap: .26, jsw: 0, jh: 0, jc: false, sl: 0, sdur: .55, ph: 0, sm: 0, badge: null, c: {pulinho: 0, canguru: 0, carrinho: 0, mergulho: 0}, seenC: {}};
    };
    let g = ui.corre;
    if (!g || g.mode !== "corre" && g.mode !== "pausa" && g.dia !== dia()) g = ui.corre = fresh();
    if (g.mode === "corre" && performance.now() - g.seen > 400) g.mode = "pausa";  // came back to the page: wait in the menu
    let W = 600, H = 300, G = 256, sc = 1, last = 0, down = false;
    const sx = () => Math.min(120, W * .2);
    const fit = () => {
      const r = cv.getBoundingClientRect(), dpr = devicePixelRatio || 1;
      sc = Math.min(r.height / 300, r.width / 400);  // at least 400 units of street on screen, more on wide screens
      W = r.width / sc; H = r.height / sc; G = H - 44;
      cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr); cx.setTransform(sc * dpr, 0, 0, sc * dpr, 0, 0);
    };
    fit(); addEventListener("resize", fit, on); document.addEventListener("fullscreenchange", () => setTimeout(fit, 50), on);
    const speed = () => spd(g.x / K.len) * g.slow * (g.boost > 0 ? 1.3 : 1);
    const mult = () => Math.min(5, 1 + Math.floor(g.streak / 5));
    const add = (n, txt, c) => { n = Math.round(n * (g.esq ? 1.5 : 1)); g.pts += n; if (txt) pop(`${txt} +${n}`, c); };
    const pop = (txt, c = "#fff", big) => {  // a big pop slows the street for a moment, so the joke lands
      if (big) g.sm = .7;
      if (!big) g.pops = g.pops.filter(q => q.big || q.txt.split(" ")[0] !== txt.split(" ")[0]);  // the new streak count replaces the old one
      g.pops.push({txt, c, big, t: 0, y: big ? H * .42 + 40 * g.pops.filter(q => q.big).length : (sm => (up => up >= 140 ? up : Math.max(140, ...sm.map(v => v + 24)))(Math.min(G - g.y - 86, ...sm.map(v => v - 24))))(g.pops.filter(q => !q.big).map(q => q.y - q.t * 22))});  // above the pops on screen, or below them when that would reach the HUD
    };
    const got = id => { if (g.ach.has(id)) return; g.ach.add(id); g.badge = {txt: ACH.find(a => a[0] === id)[1], t: 0}; };
    const put = (type, x, b = 0, extra) => { const [w, h] = SIZE[type]; g.obs.push({type, x, w, h, b, ...extra}); };

    // the street: everything from the day's seed, in the same order for everyone, so the same day = the same street
    const spawn = () => {
      const R = g.R, x = g.next, p = x / K.len;
      if (FIX.some(f => f > x - spd(p) * .7 && f < x + 110)) return void (g.next = x + 120);  // a pickup and an obstacle at once is a coin toss; after it, room to land a full jump and react
      const pool = ["cone", "cone", "lixo", "poca", ...(p > .15 ? ["pipoca"] : []), ...(p > .1 ? ["pombo"] : []), ...(p > .2 ? ["faixa", "faixa"] : []), ...(p > .3 ? ["sombra"] : [])];
      const type = pool[Math.floor(R() * pool.length)], [w] = SIZE[type], low = type === "faixa" || type === "pombo";
      put(type, x, type === "pombo" ? 34 + R() * 8 : type === "faixa" ? 30 : 0, type === "faixa" ? {txt: FAIXAS[Math.floor(R() * FAIXAS.length)]} : type === "sombra" ? {vx: -70} : {});
      if (R() < .4) {  // pilas: an arc over what you jump, a low line under what you slide under
        const n = 3 + Math.floor(R() * 3);
        for (let i = 0; i < n; i++) { const k = i - (n - 1) / 2; put("pila", x + w / 2 + k * 24 - 6, low ? 6 : Math.max(8, 78 - k * k * 9)); }
      }
      if (R() < .16 && GROUND.has(type) && type !== "sombra") put("bola", x - 150 - R() * 60, 0, {vx: 0, vb: 0});
      if (R() < .18) put("cuia", x + w + 90 + R() * 60, 30 + R() * 60);
      g.next = x + w + spd(p) * (.75 + R() * .7);
      if (g.next > K.rei[0] - 200 && g.next < K.rei[1] + 100) g.next = K.rei[1] + 100;  // the King's stretch has no street obstacles
    };
    const endSlide = () => { if (g.sl >= .8 && ++g.c.carrinho === 3) got("carrinho"); g.slide = 0; };
    const hurt = o => {
      if (g.shield) { g.shield = 0; g.inv = 1; o.hit = true; pop("O colete segurou!", "#7dffb0"); return; }
      o.hit = true; g.lives--; g.hits++; g.n.tombos++; g.inv = 1.3; g.slow = .35; g.streak = 0;
      if (navigator.vibrate) try { navigator.vibrate(60); } catch {}
      if (!g.lives) finish(false);
    };
    const ballHit = (o, S) => {  // the ball as drawn (a circle) against the body, plus the head when standing
      const bx = o.x + 8, by = o.b + 8, top = g.slide ? S[3] : S[1] + 48;
      return Math.hypot(bx - Math.max(S[0], Math.min(bx, S[2])), by - Math.max(S[1], Math.min(by, top))) < 6.5 || !g.slide && Math.hypot(bx - g.x - 6, by - g.y - 58) < 14;
    };
    const kingX = () => g.x + g.king.ox;
    const kingStep = dt => {
      const k = g.king, v = speed(), home = W - 110 - sx();
      if (k.st === "off" && g.x >= K.rei[0]) { k.st = "intro"; k.t = 1.2; k.ox = W + 60; pop("BIOFUT KING", "#f2c230", true); BF.ev("corre_saul", "king"); }
      if (k.st === "off" || k.st === "fim") return;
      k.hit = Math.max(0, k.hit - dt);
      if (k.st === "intro" || k.st === "luta") k.ox += (home - k.ox) * Math.min(1, dt * 2.5);
      if (k.st === "intro" && (k.t -= dt) <= 0) k.st = "luta";
      if (k.st === "luta") {
        if (g.x >= K.rei[1]) { k.st = "foge"; pop("O King fugiu!", "#f2c230"); return; }
        if ((k.cd -= dt) > 0) return;
        k.n++; k.cd = [.65, .8, .95][k.hp - 1] + g.RK() * .2;  // faster as he gets weaker
        const kind = k.n % 2 === 0 ? "alta" : g.RK() < .5 ? "kbola" : "corneta", x0 = kingX() - 24;
        if (kind === "kbola") put("kbola", x0, 0, {vx: -240, vb: 0});
        else if (kind === "corneta") { put("corneta", x0, 30, {vx: -320}); k.sopro = .4; }
        else { const T = 1.05, d = x0 - (g.x + 30); put("alta", x0, 60, {vx: v - d / T, vb: 430}); }
      }
      if (k.st === "foge") { k.ox += 420 * dt; if (k.ox > W + 120) k.st = "fim"; }
      if (k.st === "caiu") { k.ox -= v * dt; k.t += dt; if (k.ox < -200) k.st = "fim"; }
    };
    const kingDown = () => {
      const k = g.king; k.st = "caiu"; k.t = 0; got("rei"); add(300, "REI DEPOSTO!", "#f2c230");
      g.obs = g.obs.filter(o => !["kbola", "corneta", "alta"].includes(o.type) || o.back);
      for (let i = 0; i < 8; i++) put("pila", g.x + W + 40 + i * 70, 10 + (i % 2) * 40);  // the street is clear: the King's change on the floor
    };
    const step = dt => {
      const v = speed();
      g.t += dt; g.inv = Math.max(0, g.inv - dt); g.boost = Math.max(0, g.boost - dt); g.buf = Math.max(0, g.buf - dt); g.sbuf = Math.max(0, g.sbuf - dt);
      g.kick = Math.max(0, g.kick - dt); g.kcd = Math.max(0, g.kcd - dt); g.slow = Math.min(1, g.slow + dt * .8);
      if (g.king.sopro) g.king.sopro = Math.max(0, g.king.sopro - dt);
      g.x = Math.min(K.len, g.x + v * dt); g.vmax = Math.max(g.vmax, v);
      g.ph += dt * (6 + v / 30);  // faster street, faster legs
      if (g.slide && (g.sl += dt) >= g.sdur) endSlide();
      if (g.buf && !g.y) { g.n.pulos++; if (g.slide) endSlide(); g.vy = 700 * (1 + .07 * lvl("chuteira")); g.y = .01; g.ht = g.jh = 0; g.jc = false; g.buf = 0; }
      if (g.y) {
        g.ht += dt;
        if (g.sbuf) g.vy = Math.min(g.vy, -900);  // slide asked in the air: drop fast
        const lift = (down || g.ht < g.jsw) && g.vy > 0 && g.ht < g.jcap;  // held longer, or swiped further: higher, up to .26 s of lift
        if (lift) g.jh += dt;
        g.vy -= (lift ? 1150 : 2500) * dt; g.y = Math.max(0, g.y + g.vy * dt);
        if (!g.y) {  // landed
          if (g.jh < .05 && g.jc && ++g.c.pulinho === 5) got("pulinho");
          if (g.jh > .24 && ++g.c.canguru === 3) got("canguru");
          if (g.sbuf) { g.sbuf = 0; g.slide = 1; g.sl = 0; g.n.deslizes++; if (++g.c.mergulho === 5) got("mergulho"); }
        }
      }
      while (g.next < g.x + W + 60 && g.next < K.len - 600) spawn();
      while (g.fix.length && g.fix[0].x < g.x + W + 100) g.obs.push(g.fix.shift());
      kingStep(dt);
      const ima = [0, 50, 100][lvl("ima")], S = g.slide ? [g.x - 14, g.y + 2, g.x + 16, g.y + 24] : [g.x - 9, g.y + 2, g.x + 9, g.y + 58];
      for (const o of g.obs) {
        if (o.vx) o.x += o.vx * dt;
        if (o.vb !== undefined && (o.type === "alta" || o.type === "kbola" || o.roll)) {
          o.vb -= 900 * dt; o.b += o.vb * dt;
          if (o.b < 0) { o.b = 0; o.vb = o.type === "alta" && !o.back ? 0 : -o.vb * .45; }
        }
        if (o.type === "pila" && !o.hit && ima && Math.abs(o.x - g.x) < ima) { o.x += (g.x - o.x) * Math.min(1, dt * 8); o.b += (g.y + 30 - o.b) * Math.min(1, dt * 8); }
        if (o.roll && !o.hit) {  // a kicked ball knocks down the first obstacle in its way
          const t = g.obs.find(q => GROUND.has(q.type) && !q.hit && !q.done && q.x < o.x + o.w && q.x + q.w > o.x);
          if (t) { t.hit = t.done = true; t.fly = 0; o.hit = true; g.streak++; got("tabelinha"); add(30 * mult(), "Tabelinha!", "#7dffb0"); }
          if (o.x > g.x + W + 100) o.hit = true;
        }
        if (o.back && !o.hit && o.x >= kingX() - 20) {  // returned to the King
          o.hit = true; const k = g.king;
          if (["intro", "luta", "foge"].includes(k.st)) { k.hp--; k.hit = .5; add(60, "No King!", "#f2c230"); if (!k.hp) kingDown(); }
        }
        if (o.hit || o.done) continue;
        const ox0 = o.x + 3, ox1 = o.x + o.w - 3, ob0 = o.b + 2, ob1 = o.b + o.h - 2;
        const xin = ox0 <= S[2] && ox1 >= S[0], ball = o.type === "kbola" || o.type === "alta";
        if (xin && HURT.has(o.type) && g.y > 0) o.clr = Math.min(o.clr ?? 1e9, S[1] - ob1);
        if (xin && o.type === "corneta" && g.slide) o.slid = true;
        if (ball ? ballHit(o, S) : xin && ob0 <= S[3] && ob1 >= S[1]) {
          if (o.type === "pila") { o.hit = true; g.pilas++; add(5); }
          else if (o.type === "ele") { o.hit = true; add(50); const all = ++g.eles === ELES.length; pop(o.say, all ? "#ff4a6e" : "#ffd2dc", true); if (all) got("saulnaro"); }
          else if (o.type === "cuia") { o.hit = true; g.boost = 2.2 + .8 * lvl("cuia"); pop("Chimarrão!", "#9be07a"); }
          else if (o.type === "letra") {
            o.hit = true; g.letras += o.l; pop(o.l, "#f2c230");
            if (g.letras.length === 5) { g.lives = Math.min(g.lives + 1, g.max + 1); got("lista"); pop("ENTROU NA LISTA! +1 vida", "#f2c230", true); }
          } else if (o.type === "amigo") { o.hit = true; g.shield = 1; pop(`${nm(o.name) || "Um parceiro"} te deu o colete!`, "#7dffb0"); }
          else if (o.type === "alta" && o.back) continue;
          else if (HURT.has(o.type) && !g.inv) hurt(o);
          if (g.mode !== "corre") return;
          continue;
        }
        if (HURT.has(o.type) && !o.back && ox1 < S[0]) {  // passed it clean
          o.done = true;
          if (o.type === "corneta" && o.slid && ++g.king.minhoca >= 3) got("minhoca");
          if (["kbola", "corneta", "alta"].includes(o.type)) { add(15); continue; }
          g.streak++; add(10 * mult()); if (g.y > 0) g.jc = true;
          if (o.clr !== undefined && o.clr < 7) { add(25, "Raspando!", "#ffd27a"); if (++g.near >= 5) got("raspando"); }
          if (g.streak % 5 === 0 && mult() > 1) pop(`Sequência x${mult()}`, "#ff7a9a");
        }
      }
      g.obs = g.obs.filter(o => o.x + o.w > g.x - sx() - 60 && (!o.hit || o.fly !== undefined || o.type === "amigo"));
      for (const o of g.obs) if (o.fly !== undefined) o.fly += dt;
      g.pops = g.pops.filter(p => (p.t += dt) < (p.big ? 3 : 1.8));
      if (g.badge && (g.badge.t += dt) > 2.6) g.badge = null;
      if (g.x >= K.len) finish(true);
    };

    // ---------- input: jump (tap, swipe up, Space, Up, W), slide (swipe down, Down, S), kick (swipe right, X, K), menu (Esc, P)
    const start = () => {
      Object.assign(g, fresh(), {mode: "corre"}); ui.correTip = null; menu(false); BF.ev("corre_saul", "start");
      post("corre", {op: "go"}).then(j => { if (j) g.go = true; });  // a visitor runs as Sombras (index.html post sends their browser's id)
      if (touch && (local().runs || 0) < 3) pop("Deslize: ↑ pula · ↓ desliza · → chuta", "#ffd27a", true);
      cv.focus({preventScroll: true});
    };
    const pause = () => { if (g.mode === "corre") g.mode = "pausa"; menu("jogar"); };
    const resume = () => { menu(false); if (g.mode === "pausa") g.mode = "corre"; cv.focus({preventScroll: true}); };
    const go = () => g.mode === "pausa" ? resume() : g.mode !== "corre" && !(g.mode === "fim" && performance.now() - g.end < 700) && start();  // a late tap must not restart the run
    const press = () => {
      down = true; g.jcap = .26; g.jsw = 0;
      if (g.mode === "corre") g.buf = .14;  // a jump asked a little before landing still counts
      else go();
    };
    const release = () => { down = false; };
    const slide = d => {  // d: how long in s; a held key or button slides up to .9 s, a longer swipe slides further
      if (g.mode !== "corre") return;
      g.sdur = g.slide || g.sbuf ? Math.max(g.sdur, d) : d;
      if (g.y) g.sbuf = .3; else if (!g.slide) { g.n.deslizes++; g.slide = 1; g.sl = 0; g.buf = 0; }
    };
    const unslide = () => { g.sdur = Math.min(g.sdur, g.slide ? Math.max(.3, g.sl) : .55); };  // let go: get up, after at least .3 s (a dive from the air: .55 s)
    const kick = () => {
      if (g.mode !== "corre" || g.kcd) return;
      g.kick = .28; g.kcd = .4; g.n.chutes++;
      for (const o of g.obs) {
        const d = o.x - g.x;
        if (o.type === "bola" && !o.roll && d > -16 && d < 64) { o.roll = true; o.vx = speed() + 480; o.vb = 140; }
        if (o.type === "alta" && !o.back && !o.hit && d > -18 && d < 74 && o.b < 90) { o.back = true; o.vx = speed() + 700; o.vb = 260; pop("Devolve!", "#f2c230"); if (g.y > 40) got("voadora"); }
      }
    };
    const buzz = () => { if (touch) try { navigator.vibrate?.(8); } catch {} };
    const ACT = {jump: press, slide: () => slide(.9), kick, menu: pause, fs: () => document.fullscreenElement ? document.exitFullscreen() : $("#correWrap").requestFullscreen?.().then(() => screen.orientation?.lock?.("landscape")).catch(() => {})};
    let tp = null;  // a finger on the street: a tap or a swipe up jumps (held: higher), a swipe down slides, a swipe right kicks
    cv.addEventListener("pointerdown", e => {
      e.preventDefault();
      const r = cv.getBoundingClientRect(), mx = (e.clientX - r.left) / sc, my = (e.clientY - r.top) / sc;
      if (g.mode === "corre" && Math.hypot(mx - W * .62, my - 72) < 26 && ++g.lua === 3 && !g.esq) {  // the moon, three times
        g.esq = 1; got("esquizo"); pop("HOJE É DIA DE ESQUIZOFUT! pontos x1,5", "#c38bff", true); BF.ev("corre_saul", "esquizofut"); return;
      }
      if (e.pointerType === "mouse" || g.mode !== "corre") return press();
      clearTimeout(tp?.tm);
      tp = {x: e.clientX, y: e.clientY, id: e.pointerId, tm: setTimeout(() => { if (tp && !tp.done) { tp.done = true; press(); } }, 90)};  // still after 90 ms: a held jump
    }, on);
    cv.addEventListener("pointermove", e => {
      if (!tp || tp.id !== e.pointerId) return;
      const dx = e.clientX - tp.x, dy = e.clientY - tp.y;
      if (!tp.done && Math.hypot(dx, dy) > 16) {
        tp.done = true; clearTimeout(tp.tm); tp.k = Math.abs(dx) > Math.abs(dy) ? dx > 0 ? "kick" : "" : dy < 0 ? "jump" : "slide"; tp.top = dy;
        if (tp.k === "kick") kick(); else if (tp.k === "jump") press(); else if (tp.k) slide(.3);
      }
      if (tp.k === "jump") { g.jsw = Math.max(g.jsw, .26 * Math.min(1, -dy / 140)); tp.top = Math.min(tp.top, dy); }  // a longer swipe: a higher jump
      if (tp.k === "slide") slide(.3 + .6 * Math.min(1, dy / 150));  // a longer swipe: a longer slide
      else if (tp.k === "jump" && !tp.fall && dy - tp.top > 30 && g.y) { tp.fall = true; slide(.55); }  // jumped, then down: drop fast
    }, on);
    const lift = e => {
      if (tp && tp.id === e.pointerId) { clearTimeout(tp.tm); if (!tp.done) press(); tp = null; }  // a quick tap: a short hop
      release();
    };
    addEventListener("pointerup", lift, on); addEventListener("pointercancel", lift, on);
    cv.addEventListener("contextmenu", e => e.preventDefault(), on);
    $("#correWrap").querySelectorAll("[data-k]").forEach(b => {
      b.addEventListener("pointerdown", e => { e.preventDefault(); b.classList.add("on"); buzz(); ACT[b.dataset.k](); }, on);
      for (const ev of ["pointerup", "pointerleave", "pointercancel"]) b.addEventListener(ev, () => { b.classList.remove("on"); if (b.dataset.k === "jump") release(); if (b.dataset.k === "slide") unslide(); }, on);
      b.addEventListener("contextmenu", e => e.preventDefault(), on);
    });
    const KEYS = {Space: "jump", ArrowUp: "jump", KeyW: "jump", ArrowDown: "slide", KeyS: "slide", KeyX: "kick", KeyK: "kick"};
    addEventListener("keydown", e => {
      if (/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(document.activeElement?.tagName || "") && document.activeElement !== cv) return;
      const open = $("#correMenu")?.hidden === false, k = KEYS[e.code];
      if (e.code === "KeyP" || e.code === "Escape") { if (open) g.mode === "pausa" && resume(); else if (g.mode === "corre") pause(); return; }
      if (!k) return;
      e.preventDefault();
      if (e.repeat) return;
      if (open) { if (k === "jump") go(); return; }
      ACT[k]();
    }, on);
    addEventListener("keyup", e => KEYS[e.code] === "jump" ? release() : KEYS[e.code] === "slide" && unslide(), on);
    document.addEventListener("visibilitychange", () => document.hidden && g.mode === "corre" && pause(), on);

    // ---------- the end of a run: points, records, coins; the result opens in the menu
    function finish(won) {
      g.mode = "fim"; g.won = won; g.end = performance.now();
      const at = Math.round(K.t0 + g.t * K.k);
      if (won) {
        if (at <= K.gol) { g.ach.add("pontual"); add(Math.round((K.gol - at) * 4)); }
        if (at <= K.gol && at >= K.gol - 5) g.ach.add("apito");
        if (!g.hits) g.ach.add("limpo");
        add(g.lives * 50);
        if (g.pilas >= 12) { g.ach.add("pagou"); add(50); }
        if (!g.pilas) g.ach.add("devedor");
      }
      g.at = at;
      const L = local(), n = {...L.n}, more = {...g.n, metros: Math.round(g.x / 10), pilas: g.pilas, chegadas: +won, na_hora: +(won && at <= K.gol), reis: +g.ach.has("rei")};
      for (const k in more) n[k] = (n[k] || 0) + more[k];
      store.set("biofutCorre2", JSON.stringify({best: Math.max(L.best || 0, g.pts), runs: (L.runs || 0) + 1, cedo: won ? Math.min(L.cedo || at, at) : L.cedo, n,
        ach: [...new Set([...(L.ach || []), ...g.ach])]}));
      BF.ev("corre_saul", won ? (at <= K.gol ? "a tempo" : "atrasado") : "cancelado");
      setTimeout(() => ui.corre === g && g.mode === "fim" && menu("jogar"), 900);
      if (g.go) post("corre", {op: "fim", t: g.t, pts: g.pts, pilas: g.pilas, chegou: won, rei: g.ach.has("rei"), ach: [...g.ach], n: {...g.n, metros: more.metros}})
        .then(j => { if (!j) return; setState(j); g.coins = j.coins; if ($("#correMenu")?.hidden === false) menu(); });
    }

    // ---------- the menus over the game: Jogar (title, pause, result), Ranking, Vestiário, Conquistas, Números
    const TABS = [["jogar", "Jogar"], ["ranking", "Ranking"], ["vestiario", "Vestiário"], ["conquistas", "Conquistas"], ["numeros", "Números"]];
    const comoJoga = () => `<div class="corre-help">${touch ? "<span><b>Toque</b> ou deslize <b>↑</b>: pula</span><span>Deslize <b>↓</b>: desliza</span><span>Deslize <b>→</b>: chuta</span><span>Segure: pula mais alto</span>"
      : "<span><b>Espaço</b>: pula (segure: mais alto)</span><span><b>↓</b>: desliza</span><span><b>X</b>: chuta</span><span><b>Esc</b>: pausa</span>"}</div>`;
    const sombras = () => ME ? "" : `<p class="muted" style="font-size:14px;margin-top:14px;max-width:620px">Sem entrar, você corre como <b>Sombras</b>: um nome só para todos os visitantes no ranking, sem moedas nem melhorias.
      <a class="link" href="/entrar?next=${encodeURIComponent("/#/corre")}">Entre com seu WhatsApp</a> para correr com o seu nome.</p>`;
    function telaJogar() {
      const T = ui.correTip ??= tip(), br = g.dia.slice(8) + "/" + g.dia.slice(5, 7);
      if (g.mode === "pausa") return `<div class="kicker">Pausa</div><h2>${clk(K.t0 + g.t * K.k)}</h2><p class="lead">${num(g.pts)} pontos até aqui. O Planet não sai do lugar.</p>
        <div class="row"><button class="btn pri" data-go>Continuar</button><button class="btn" data-new>Recomeçar</button></div>${comoJoga()}${T}`;
      if (g.mode === "fim") {
        const me = ME || SOMBRAS, i = Object.entries(ST.corre || {}).filter(([, r]) => r.dia?.[0] === dia()).sort(([, a], [, b]) => b.dia[1] - a.dia[1]).findIndex(([n]) => n === me);
        g.pos = ME && i >= 0 ? i + 1 : 0;
        const head = g.won ? `Chegou no Planet às ${clk(g.at)}${g.at <= K.gol ? ", a tempo!" : ", atrasado."}` : "Tomou canelada demais: jogo canelado.";
        const line = [`${g.t.toFixed(1).replace(".", ",")} s de corrida`, `máxima de ${Math.round(g.vmax * KMH)} km/h`, `${g.pilas} pila${g.pilas === 1 ? "" : "s"}`,
          g.coins && `+${coin(g.coins)} moeda`, g.pos ? `${g.pos}º hoje` : !ME && i >= 0 && `Sombras em ${i + 1}º hoje`].filter(Boolean).join(" · ");
        return `<div class="kicker" style="color:${g.won ? "var(--win)" : "var(--acc)"}">${g.won ? "Chegou" : "Jogo canelado"}</div><h2>${num(g.pts)} pontos</h2>
          <p class="lead"><b style="color:var(--ink)">${head}</b><br>${line}</p>
          <div class="row"><button class="btn pri" data-go>Correr de novo</button><button class="btn" data-share>Compartilhar imagem</button></div>${sombras()}${T}`;
      }
      return `<h2>Corre, Saul!</h2><p class="lead">Quinta, 18:30, Planet Ball, e o Saul (vulgo Saulnaro) saiu atrasado de novo. Pule, deslize e chute o que aparecer na rua,
        encare o BioFut King e chegue antes que alguém cancele o jogo. Começa devagar e acelera até o Planet. A rua de ${br} é a mesma para todo mundo.</p>
        <div class="row"><button class="btn pri" data-go>Correr</button></div>${comoJoga()}${sombras()}${T}`;
    }
    function telaRanking() {
      const hoje = dia(), R = Object.entries(ST.corre || {});
      const list = (title, rows, big, small) => `<div class="card pad"><h3>${title}</h3>${rows.length ? `<ul class="list" style="margin-top:8px">${rankList(rows, ([n, r], i) =>
        `<li><span class="dim num" style="width:20px;font:700 14px var(--cond)">${i + 1}</span>${av(n, "s")}${pname(n, esc(nm(n)))}<span class="r"><b class="num">${big(r)}</b><small>${small(r)}</small></span></li>`)}</ul>`
        : '<p class="muted" style="margin-top:8px">Ninguém ainda: a primeira corrida abre a lista.</p>'}</div>`;
      return `<h3>Quem chega primeiro</h3><div class="corre-grid">
        ${list("Corrida de hoje", R.filter(([, r]) => r.dia?.[0] === hoje).sort(([, a], [, b]) => b.dia[1] - a.dia[1]), r => num(r.dia[1]), () => "pontos")}
        ${list("Recorde", R.filter(([, r]) => r.best).sort(([, a], [, b]) => b.best - a.best), r => num(r.best), r => `${r.runs} corrida${r.runs > 1 ? "s" : ""}`)}
        ${list("Mais cedo no Planet", R.filter(([, r]) => r.cedo).sort(([, a], [, b]) => a.cedo - b.cedo), r => clk(r.cedo), r => r.cedo <= K.gol ? "a tempo" : "atrasado")}</div>
        <p class="muted" style="font-size:14px;margin-top:12px">Quem joga sem entrar aparece como <b>Sombras</b>, um nome só para todos os visitantes.</p>`;
    }
    function telaVestiario() {
      const cost = ST.corre_up || {}, bal = ST.balances?.[ME] ?? 25;
      return `<h3>O vestiário do Saul</h3><p class="muted" style="margin-top:6px">${ME ? `Você tem <b class="num">${coin(bal)}</b> moedas. A melhoria vale da próxima corrida em diante.`
        : `<a class="link" href="/entrar?next=${encodeURIComponent("/#/corre")}">Entre</a> para comprar melhorias com as suas moedas.`}</p>
        <div class="corre-ups">${Object.entries(UP).map(([k, [ico, name, desc]]) => {
          const c = cost[k] || [], l = lvl(k), next = c[l];
          return `<div class="card pad"><div style="font-size:28px;line-height:1">${ico}</div><h3>${name}</h3><p class="muted" style="font-size:14px">${desc}</p>
            <div class="lv">${c.map((_, i) => `<i class="${i < l ? "on" : ""}"></i>`).join("")}</div>
            ${next === undefined ? '<span class="dim" style="font-size:13px">No máximo</span>' : ME ? `<button class="btn sm${bal >= next ? " pri" : ""}" data-up="${k}">Comprar · ${coin(next)} moeda${next === 1 ? "" : "s"}</button>` : `<span class="dim" style="font-size:13px">${coin(next)} moedas</span>`}</div>`;
        }).join("")}</div>`;
    }
    function telaConquistas() {
      const mine = found();
      return `<h3>${mine.size} de ${ACH.length} conquistas</h3><p class="muted" style="margin-top:6px"><a class="link" href="/wiki#/p/biofut-king">Quem é o BioFut King? Na wiki</a></p>
        <div class="corre-ach">${ACH.map(([id, name, how, hid]) => mine.has(id) ? `<div class="ok"><b>${name}</b>${how}</div>`
          : hid ? '<div><b>???</b>Segredo. Continue correndo.</div>' : `<div><b>${name}</b>${how}</div>`).join("")}</div>`;
    }
    function telaNumeros() {
      const r = ME ? rec() : local(), n = r.n || {}, all = Object.values(ST.corre || {}), sum = k => all.reduce((s, x) => s + (x.n?.[k] || 0), 0);
      const km = m => (m / 1000).toFixed(1).replace(".", ","), tiles = T => `<div class="corre-num">${T.map(([v, l]) => `<div><b class="num">${v}</b><small>${l}</small></div>`).join("")}</div>`;
      return `<h3>${ME ? "Você" : "Você, neste navegador"}</h3>${tiles([[num(r.runs), "corridas"], [num(n.chegadas), "chegadas no Planet"], [num(n.na_hora), "a tempo"],
          [r.cedo ? clk(r.cedo) : "ainda não", "a chegada mais cedo"], [num(r.best), "recorde de pontos"], [num(n.reis), "reis derrubados"], [num(n.pilas), "pilas"],
          [km(n.metros || 0), "km corridos"], ...N.map(([k, l]) => [num(n[k]), l])])}
        <h3>Todo mundo</h3>${tiles([[num(all.reduce((s, x) => s + (x.runs || 0), 0)), "corridas"], [num(all.filter(x => x.dia?.[0] === dia()).length), "nomes no ranking de hoje"],
          [num(sum("chegadas")), "chegadas"], [num(sum("reis")), "reis derrubados"], [num(sum("pilas")), "pilas"], [km(sum("metros")), "km corridos"], [num(sum("pulos")), "pulos"], [num(sum("tombos")), "tropeços"]])}
        <p class="muted" style="font-size:13px">A corrida começa a ${Math.round(spd(0) * KMH)} km/h e chega a ${Math.round(spd(1) * KMH)} km/h perto do Planet. O chimarrão dá +30%, um tropeço freia.</p>`;
    }
    function menu(tab) {
      const m = $("#correMenu");
      if (!m) return;
      if (tab === false) return void (m.hidden = true);
      if (tab) ui.correTab = tab;
      tab = ui.correTab || "jogar";
      const keep = !m.hidden && m.dataset.tab === tab ? m.querySelector(".corre-body")?.scrollTop || 0 : 0;  // a redraw after the server's reply keeps the scroll
      m.dataset.tab = tab; m.hidden = false;
      m.innerHTML = `<div class="corre-tabs" role="tablist">${TABS.map(([k, l]) => `<button role="tab" aria-selected="${k === tab}" data-tab="${k}">${l}</button>`).join("")}
        <button class="x" data-x aria-label="Fechar o menu" title="Fechar">✕</button></div>
        <div class="corre-body">${{jogar: telaJogar, ranking: telaRanking, vestiario: telaVestiario, conquistas: telaConquistas, numeros: telaNumeros}[tab]()}</div>`;
      m.querySelector(".corre-body").scrollTop = keep;
      m.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => menu(b.dataset.tab));
      m.querySelector("[data-x]").onclick = () => g.mode === "pausa" ? resume() : menu(false);
      m.querySelectorAll("[data-go]").forEach(b => b.onclick = go);
      m.querySelectorAll("[data-new]").forEach(b => b.onclick = start);
      m.querySelectorAll("[data-share]").forEach(b => b.onclick = shareCard);
      m.querySelectorAll("[data-up]").forEach(b => b.onclick = async () => {
        b.disabled = true;
        const j = await post("corre", {op: "up", item: b.dataset.up});
        if (j) { setState(j); toast(`${UP[b.dataset.up][1]}: comprada`); BF.ev("corre_saul", "up " + b.dataset.up); }
        menu();
      });
    }

    // ---------- drawing (world units; G = the curb line)
    const box = (x, y, w, h, c) => { cx.fillStyle = c; cx.fillRect(x, y, w, h); };
    const glow = (x, y, r, c) => { const q = cx.createRadialGradient(x, y, 0, x, y, r); q.addColorStop(0, c); q.addColorStop(1, "rgba(0,0,0,0)"); cx.fillStyle = q; cx.fillRect(x - r, y - r, r * 2, r * 2); };
    const txt = (s, x, y, font, c, al = "center") => { cx.font = font; cx.fillStyle = c; cx.textAlign = al; cx.fillText(s, x, y); };
    const seg = (x, y, a, l, c, w) => { cx.strokeStyle = c; cx.lineWidth = w; cx.beginPath(); cx.moveTo(x, y); cx.lineTo(x + Math.sin(a) * l, y + Math.cos(a) * l); cx.stroke(); return [x + Math.sin(a) * l, y + Math.cos(a) * l]; };
    // angles from straight down, + = forward; thigh/upper arm, then shin/forearm, then the shoe across the shin
    const limb = (x, y, a1, l1, a2, l2, c1, c2, w, shoe) => {
      const [kx, ky] = seg(x, y, a1, l1, c1, w), [ex, ey] = seg(kx, ky, a2, l2, c2, w);
      if (shoe) seg(ex - Math.cos(a2), ey + Math.sin(a2), a2 + Math.PI / 2, 6, shoe, w + 1);
    };
    // a runner: pose run | air | slide | kick; P = colors; the King uses it too, mirrored
    const runner = (x, yb, ph, pose, P, q = .4) => {
      const s = Math.sin(ph), air = pose === "air", bob = pose === "run" || pose === "kick" ? Math.abs(Math.cos(ph)) * (1.5 + 2 * q) : 0;
      cx.lineCap = cx.lineJoin = "round";
      if (pose === "slide") {  // leaning back, legs first
        const hy = yb - 9;
        limb(x + 2, hy, 1.45, 14, 1.6, 14, P.skin2, P.sock2, 5, "#111"); limb(x - 2, hy - 18, -1.9, 9, -1.2, 8, P.skin2, P.skin2, 4);
        cx.save(); cx.translate(x, hy); cx.rotate(-1.2); torso(P); cx.restore();
        limb(x + 4, hy, 1.35, 14, 1.75, 14, P.skin, P.sock, 5, "#111");
        return;
      }
      const hy = yb - 27 - bob;
      const leg = (k, skin, sock) => {
        const t = s * k;
        if (pose === "kick" && k > 0) return limb(x, hy, 1.7, 14, 1.25, 14, skin, sock, 5, "#111");
        const a = air ? (k > 0 ? .95 : -.45) : (.6 + .35 * q) * t;  // the back foot kicks up, the front shin stays near vertical
        limb(x, hy, a, 14, air ? (k > 0 ? .1 : -1.6) : t > 0 ? .2 * t : a + 1.1 * t, 14, skin, sock, 5, "#111");
      };
      const arm = (k, c) => { const a = air ? -2.2 * k : pose === "kick" ? -1.2 * k : -(.7 + .5 * q) * s * k; limb(x + 3, hy - 17, a, 10, a + 1.5, 9, c, c, 4); };
      leg(-1, P.skin2, P.sock2); arm(-1, P.skin2);
      cx.save(); cx.translate(x, hy); cx.rotate(.1 + .16 * q); torso(P); cx.restore();
      leg(1, P.skin, P.sock); arm(1, P.skin);
    };
    const torso = P => {
      box(-7.5, -2, 15, 9, "#141414");  // shorts
      cx.fillStyle = P.shirt; cx.beginPath(); cx.roundRect(-7.5, -23, 15, 23, 4); cx.fill();
      box(-7.5, -23, 15, 3, P.trim);
      txt(P.num, 0, -8, "800 10px 'Barlow Condensed',sans-serif", P.num === "K" ? P.trim : "#fff");
      cx.fillStyle = P.skin; cx.beginPath(); cx.arc(1.5, -31, 8, 0, 7); cx.fill();  // head
      cx.fillStyle = P.hair; cx.beginPath(); cx.arc(1, -33, 8.4, Math.PI * .95, Math.PI * 2.08); cx.fill();  // hair
      box(5, -32, 2, 2.4, "#1a1310");  // eye
    };
    const crown = (x, y, s = 1) => {
      cx.fillStyle = "#f2c230"; cx.beginPath(); cx.moveTo(x - 9 * s, y); cx.lineTo(x - 9 * s, y - 9 * s); cx.lineTo(x - 4.5 * s, y - 4 * s); cx.lineTo(x, y - 11 * s);
      cx.lineTo(x + 4.5 * s, y - 4 * s); cx.lineTo(x + 9 * s, y - 9 * s); cx.lineTo(x + 9 * s, y); cx.fill();
      box(x - 9 * s, y - 2 * s, 18 * s, 2 * s, "#c9971a"); cx.fillStyle = "#ff4a6e"; cx.beginPath(); cx.arc(x, y - 5 * s, 1.6 * s, 0, 7); cx.fill();
    };
    const king = (px, now) => {
      const k = g.king, fall = k.st === "caiu";
      cx.save(); cx.translate(px, G); cx.scale(-1.3, 1.3);  // faces Saul, bigger
      if (fall) { cx.rotate(Math.min(1.5, k.t * 4)); cx.translate(0, -4); }
      const cape = Math.sin(now * 9) * 3;
      cx.fillStyle = "#b0172f"; cx.beginPath(); cx.moveTo(-3, -50); cx.lineTo(-20 - cape, -14); cx.lineTo(-8, -18); cx.lineTo(4, -48); cx.fill();
      if (!(k.hit && Math.floor(now * 20) % 2)) runner(0, 0, now * 11, k.st === "luta" || k.st === "intro" ? "run" : "air", KING);
      if (!fall) crown(1.5, -61, .9);
      if (k.sopro) { cx.fillStyle = "#f2c230"; cx.beginPath(); cx.moveTo(8, -56); cx.lineTo(22, -62); cx.lineTo(22, -48); cx.fill(); }  // the corneta at his mouth
      cx.restore();
      if (fall) crown(px + 30 + k.t * 120, G - 40 - k.t * 160 + k.t * k.t * 300, 1.1);  // the crown flies off
      if (k.st === "luta" || k.st === "intro") {
        txt("BIOFUT KING", px, G - 124, "800 13px 'Barlow Condensed',sans-serif", "#f2c230");
        for (let i = 0; i < 3; i++) box(px - 22 + i * 15, G - 117, 13, 4, i < k.hp ? "#f2c230" : "rgba(255,255,255,.18)");
      }
    };
    const ele = (x, y, k = 1) => {  // the group's Faz o L sticker: a red disc with a white rim, the hand making the L, a star
      cx.save(); cx.translate(x, y); cx.scale(k, k);
      cx.fillStyle = "#fff"; cx.beginPath(); cx.arc(0, 0, 13.5, 0, 7); cx.fill();
      cx.fillStyle = "#e3262f"; cx.beginPath(); cx.arc(0, 0, 12, 0, 7); cx.fill();
      cx.fillStyle = "#fff";
      for (const [x0, y0, w, h, r] of [[-7, -1, 9.5, 8.5, 2.6], [-7, -11, 3.8, 12, 1.9], [1, 3.6, 8.4, 3.8, 1.9]]) { cx.beginPath(); cx.roundRect(x0, y0, w, h, r); cx.fill(); }
      cx.beginPath();
      for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, r = i % 2 ? 1.5 : 3.6; cx.lineTo(5.5 + Math.cos(a) * r, -5 + Math.sin(a) * r); }
      cx.fill();
      cx.restore();
    };
    const pila = (x, y) => {
      cx.save(); cx.translate(x + 6, y + 8); cx.rotate(-.25);
      box(-7, -5, 14, 10, "#59b85f"); box(-6, -4, 12, 8, "#7bd383"); txt("R$", 0, 3, "800 6px 'Barlow Condensed',sans-serif", "#1f5a25");
      cx.restore();
    };
    const obstacle = (o, x, now) => {
      if (o.hit && o.fly === undefined && o.type !== "amigo") return;
      const y = G - o.b - o.h;
      if (o.fly !== undefined) { cx.save(); cx.translate(x + o.w / 2 + o.fly * 300, y + o.h / 2 - o.fly * 260 + o.fly * o.fly * 500); cx.rotate(o.fly * 9); cx.translate(-x - o.w / 2, -y - o.h / 2); }
      const t = o.type;
      if (t === "cone") {
        box(x - 2, G - 4, o.w + 4, 4, "#3a2a20");
        cx.fillStyle = "#ff7a1a"; cx.beginPath(); cx.moveTo(x + 2, G - 4); cx.lineTo(x + o.w / 2 - 3, y); cx.lineTo(x + o.w / 2 + 3, y); cx.lineTo(x + o.w - 2, G - 4); cx.fill();
        box(x + 6, G - 19, o.w - 12, 5, "#f2f2ee");
      } else if (t === "lixo") {
        cx.fillStyle = "#2f7d52"; cx.beginPath(); cx.roundRect(x, y + 6, o.w, o.h - 6, 3); cx.fill();
        box(x - 2, y, o.w + 4, 7, "#256542"); box(x + 6, y + 16, o.w - 12, 3, "#3f9a68");
      } else if (t === "poca") {
        cx.fillStyle = "#35486e"; cx.beginPath(); cx.ellipse(x + o.w / 2, G + 1, o.w / 2, 5, 0, 0, 7); cx.fill();
        cx.fillStyle = "rgba(255,226,150,.35)"; cx.beginPath(); cx.ellipse(x + o.w * .62, G, o.w / 6, 1.6, 0, 0, 7); cx.fill();
      } else if (t === "pipoca") {
        box(x + 4, y, o.w - 8, 4, "#d23a3a"); for (let i = 0; i < 5; i++) box(x + 4 + i * (o.w - 8) / 5, y + 4, (o.w - 8) / 10, 6, "#f2f2ee");
        box(x + 6, y + 10, o.w - 12, 14, "#f6e7a6"); box(x + 3, y + 24, o.w - 6, 18, "#d23a3a");
        txt("PIPOCA", x + o.w / 2, y + 36, "800 9px 'Barlow Condensed',sans-serif", "#fff");
        for (const wx of [x + 11, x + o.w - 11]) { cx.fillStyle = "#222"; cx.beginPath(); cx.arc(wx, G - 5, 5, 0, 7); cx.fill(); }
      } else if (t === "pombo") {
        const f = Math.sin(now * 18) * 6;
        cx.fillStyle = "#8b909b"; cx.beginPath(); cx.ellipse(x + 12, y + 8, 11, 6, 0, 0, 7); cx.fill();
        cx.beginPath(); cx.arc(x + 2, y + 5, 4.5, 0, 7); cx.fill(); box(x - 4, y + 5, 3, 2, "#e0a040");
        cx.fillStyle = "#6c717c"; cx.beginPath(); cx.moveTo(x + 8, y + 6); cx.lineTo(x + 20, y + 6 - f); cx.lineTo(x + 18, y + 9); cx.fill();
      } else if (t === "faixa") {  // a banner hung across the sidewalk: slide under it
        const top = G - 60;  // the hitbox starts 30 above the street: a slide (24 tall) passes under, a standing Saul doesn't
        box(x, top - 50, 3, 110, "#3a3548"); box(x + o.w - 3, top - 50, 3, 110, "#3a3548");
        box(x, top, o.w, 30, "#efe6cf"); box(x, top, o.w, 3, "#ff4a6e"); box(x, top + 27, o.w, 3, "#ff4a6e");
        txt(o.txt, x + o.w / 2, top + 20, "800 11px 'Barlow Condensed',sans-serif", "#2a2236");
      } else if (t === "sombra") {  // a guest nobody invited, walking the wrong way
        cx.save(); cx.globalAlpha = .92; cx.translate(x + 12, G); cx.scale(-1, 1);
        runner(0, 0, now * 9, "run", {shirt: "#2a2838", trim: "#2a2838", num: "?", skin: "#3b3850", skin2: "#302d42", hair: "#22202e", sock: "#2a2838", sock2: "#22202e"});
        cx.restore(); txt("SOMBRA", x + 12, y - 6, "700 9px 'Barlow Condensed',sans-serif", "rgba(220,215,255,.6)");
      } else if (t === "bola" || t === "kbola" || t === "alta") {
        if (t === "alta" && !o.back) { glow(x + 8, y + 8, 18, "rgba(242,194,48,.45)"); txt("!", x + 8, y - 10, "800 16px 'Barlow Condensed',sans-serif", "#f2c230"); }
        const r = o.w / 2, c = x + r, m = y + o.h / 2;  // centred on the hitbox (a street ball is 14, the King's are 16)
        cx.fillStyle = "#f4f4f0"; cx.beginPath(); cx.arc(c, m, r, 0, 7); cx.fill();
        cx.fillStyle = "#1c1c1c"; cx.beginPath(); cx.arc(c, m, r * .37, 0, 7); cx.fill();
        for (let i = 0; i < 5; i++) { const a = now * (o.roll || o.vx ? 14 : 0) + i * 1.257; box(c + Math.cos(a) * r * .7 - 1, m + Math.sin(a) * r * .7 - 1, 2.2, 2.2, "#1c1c1c"); }
      } else if (t === "corneta") {  // the King's corneta: a sound wave at head height
        cx.strokeStyle = "rgba(242,194,48,.85)"; cx.lineWidth = 3;
        for (let i = 0; i < 3; i++) { cx.beginPath(); cx.arc(x + 26 + i * 7, y + o.h / 2, 12 + i * 4, Math.PI * .7, Math.PI * 1.3); cx.stroke(); }
        txt("FOM!", x + 10, y + o.h / 2 + 4, "800 11px 'Barlow Condensed',sans-serif", "#f2c230");
      } else if (t === "ele") { glow(x + 13, y + 13, 26, "rgba(255,74,110,.3)"); ele(x + 13, y + 13 + Math.sin(now * 4) * 2); }
      else if (t === "pila") pila(x, y);
      else if (t === "cuia") {
        glow(x + 9, y + 12, 22, "rgba(140,220,110,.28)");
        cx.fillStyle = "#7a4a24"; cx.beginPath(); cx.ellipse(x + 9, y + 14, 8.5, 9, 0, 0, 7); cx.fill();
        box(x + 1.5, y + 4, 15, 4, "#5a361a"); box(x + 3, y + 3, 12, 3, "#6aa84f");
        cx.strokeStyle = "#cfd4da"; cx.lineWidth = 2; cx.beginPath(); cx.moveTo(x + 10, y + 6); cx.lineTo(x + 15, y - 6); cx.stroke();
      } else if (t === "letra") {
        glow(x + 10, y + 11, 20, "rgba(242,194,48,.3)");
        cx.fillStyle = "#f2c230"; cx.beginPath(); cx.roundRect(x, y, 20, 22, 4); cx.fill();
        txt(o.l, x + 10, y + 17, "800 16px 'Barlow Condensed',sans-serif", "#2a1d04");
      } else if (t === "amigo") {  // a teammate from the group cheering on the curb: pass by and get the colete
        cx.save(); cx.translate(x + 12, G); if (!o.hit) cx.translate(0, -Math.abs(Math.sin(now * 6)) * 3);
        runner(0, 0, 0, o.hit ? "run" : "air", {...SAUL, shirt: "#ff4a6e", trim: "#d93358", num: "", skin: "#c48a62", skin2: "#a87350"});
        cx.restore();
        const img = o.name && faces[o.name];
        if (img?.complete && img.naturalWidth) { cx.save(); cx.beginPath(); cx.arc(x + 13, y - 14, 11, 0, 7); cx.clip(); cx.drawImage(img, x + 2, y - 25, 22, 22); cx.restore(); }
        if (o.name) txt(nm(o.name).split(" ")[0], x + 12, y - (img ? 30 : 6), "700 10px 'Barlow Condensed',sans-serif", "#ffd2dc");
      }
      if (o.fly !== undefined) cx.restore();
    };
    const heart = (x, y, c) => {
      cx.fillStyle = c; cx.beginPath(); cx.moveTo(x, y + 4); cx.bezierCurveTo(x, y - 2, x - 9, y - 2, x - 9, y + 4); cx.bezierCurveTo(x - 9, y + 9, x - 2, y + 12, x, y + 15);
      cx.bezierCurveTo(x + 2, y + 12, x + 9, y + 9, x + 9, y + 4); cx.bezierCurveTo(x + 9, y - 2, x, y - 2, x, y + 4); cx.fill();
    };
    const planet = px => {  // the Planet Ball: the field's fence, its floodlights and the sign
      box(px - 30, G - 150, 360, 150, "#10241a");
      cx.strokeStyle = "rgba(120,200,150,.18)"; cx.lineWidth = 1;
      for (let i = 0; i < 360; i += 12) { cx.beginPath(); cx.moveTo(px - 30 + i, G - 150); cx.lineTo(px - 30 + i + 40, G); cx.stroke(); cx.beginPath(); cx.moveTo(px - 30 + i + 40, G - 150); cx.lineTo(px - 30 + i, G); cx.stroke(); }
      for (const lx of [px + 40, px + 300]) { box(lx, G - 196, 5, 196, "#3a3d44"); box(lx - 14, G - 204, 33, 10, "#e9eef5"); glow(lx + 2, G - 199, 90, "rgba(235,245,255,.22)"); }
      box(px - 2, G - 62, 38, 62, "#ffd98a"); box(px + 2, G - 58, 30, 58, "#ffcc66");
      txt("QUADRA 4", px + 17, G - 68, "700 9px 'Barlow Condensed',sans-serif", "#7dffb0");
      cx.save(); cx.shadowColor = "#43d17f"; cx.shadowBlur = 18; txt("PLANET BALL", px + 70, G - 160, "800 34px 'Barlow Condensed',sans-serif", "#7dffb0", "left"); cx.restore();
    };
    const sky = (w, h, gnd) => {
      const q = cx.createLinearGradient(0, 0, 0, gnd);
      q.addColorStop(0, g.esq ? "#1d0b33" : "#0b0a1a"); q.addColorStop(1, g.esq ? "#0f3b2a" : "#33182f");
      box(0, 0, w, h, q);
    };
    const skyline = (w, gnd, off) => {
      for (let bx = -(off % townW), i = 0; bx < w; i = (i + 1) % town.length) {
        const b = town[i], top = gnd - 30 - b.h, cols = Math.floor((b.w - 8) / 11);
        box(bx, top, b.w, b.h + 30, "#181430");
        b.lit.forEach((on, j) => on && box(bx + 6 + (j % cols) * 11, top + 8 + Math.floor(j / cols) * 14, 5, 7, "rgba(242,194,48,.55)"));
        const ad = i % 8 == 2 && ADS[(i - 2) / 8 % ADS.length];
        if (ad && ad.im.naturalWidth) {
          const pw = 62, ph = 50, px = bx + (b.w - pw) / 2, py = top - ph - 10 < 84 ? top + 12 : top - ph - 10, im = ad.im, k = Math.min((pw - 6) / im.naturalWidth, (ph - 6) / im.naturalHeight);
          if (py < top) { box(px + 10, py + ph, 3, 10, "#2c2838"); box(px + pw - 13, py + ph, 3, 10, "#2c2838"); }  // posts on the roof; a tall building gets it on the wall, under the HUD
          glow(px + pw / 2, py + ph / 2, 52, "rgba(255,236,190,.16)");
          box(px - 2, py - 2, pw + 4, ph + 4, "#2c2838"); box(px, py, pw, ph, ad.bg);
          cx.drawImage(im, px + (pw - im.naturalWidth * k) / 2, py + (ph - im.naturalHeight * k) / 2, im.naturalWidth * k, im.naturalHeight * k);
          if (ad.bg !== "#000") box(px, py, pw, ph, "rgba(10,8,30,.12)");  // night tint so a light panel sits in the scene
        }
        bx += b.w + 6;
      }
    };
    const HINTS = [  // [achievement, icon, progress, goal]: a chip on the street once you start on one
      ["saulnaro", "", () => g.eles, 3], ["raspando", "😬", () => g.near, 5], ["minhoca", "🪱", () => g.king.minhoca, 3], ["pulinho", "🐇", () => g.c.pulinho, 5],
      ["canguru", "🦘", () => g.c.canguru, 3], ["carrinho", "🛷", () => g.c.carrinho, 3], ["mergulho", "🤿", () => g.c.mergulho, 5], ["esquizo", "🌙", () => g.lua, 3]];
    const hints = now => {
      let x = 12;
      for (const [id, ic, f, goal] of HINTS) {
        const n = Math.min(goal, f()); if (!n) continue;
        if (g.seenC[id] !== n) g.seenC[id] = n, g.seenC[id + "@"] = now;  // just moved: the chip jumps
        const done = n >= goal, j = Math.max(0, .35 - (now - g.seenC[id + "@"])) * 14, y = H - 31 - j, w = 50;
        cx.fillStyle = done ? "rgba(242,194,48,.9)" : "rgba(10,8,20,.72)"; cx.beginPath(); cx.roundRect(x, y, w, 22, 11); cx.fill();
        if (!done) { cx.strokeStyle = "rgba(255,255,255,.18)"; cx.lineWidth = 1; cx.stroke(); }
        if (ic) txt(ic, x + 13, y + 16, "14px sans-serif", "#fff"); else ele(x + 13, y + 11, .62);
        txt(done ? "✓" : `${n}/${goal}`, x + 36, y + 16, "800 13px 'Barlow Condensed',sans-serif", done ? "#1a1408" : "#e4e2ec");
        x += w + 6;
      }
    };
    const scrim = (title, sub, c = "#fff", sub2) => {
      box(0, 0, W, H, "rgba(6,5,14,.66)");
      txt(title, W / 2, H / 2 - 8, `800 ${Math.min(52, W / 9)}px 'Barlow Condensed',sans-serif`, c);
      txt(sub, W / 2, H / 2 + 24, "600 18px 'Barlow',sans-serif", "#e4e2ec");
      if (sub2) txt(sub2, W / 2, H / 2 + 48, "500 14px 'Barlow',sans-serif", "#a9a6b8");
    };
    const draw = now => {
      const x0 = sx();
      sky(W, H, G);
      glow(W * .62, 72, 70, g.esq ? "rgba(195,139,255,.25)" : "rgba(255,240,210,.12)"); cx.fillStyle = g.esq ? "#d9b8ff" : "#f4ecd8"; cx.beginPath(); cx.arc(W * .62, 72, 15, 0, 7); cx.fill();
      skyline(W, G, g.x * .2);
      for (let lx = 140 - ((g.x * .6) % 260); lx < W + 40; lx += 260) {  // street lamps
        box(lx, G - 132, 4, 132, "#2c2838"); box(lx - 2, G - 134, 22, 4, "#2c2838"); glow(lx + 18, G - 126, 60, "rgba(255,190,110,.2)"); box(lx + 13, G - 130, 10, 4, "#ffd7a0");
      }
      box(0, G, W, H - G, "#17151c"); box(0, G, W, 18, "#2b2731"); box(0, G, W, 3, "#4a4552");  // sidewalk and street
      for (let tx = -(g.x % 48); tx < W; tx += 48) box(tx, G + 3, 2, 15, "#221f27");
      for (let dx = -(g.x % 90); dx < W; dx += 90) box(dx, G + 29, 40, 3, "rgba(242,194,48,.45)");
      const toEnd = K.len - g.x;
      if (toEnd < W + 400) planet(x0 + toEnd - 18);  // the door ends up under Saul
      for (const o of g.obs) if (o.type === "amigo") obstacle(o, o.x - g.x + x0, now);
      for (const o of g.obs) if (o.type !== "amigo") obstacle(o, o.x - g.x + x0, now);
      if (["intro", "luta", "foge", "caiu"].includes(g.king.st)) king(x0 + g.king.ox, now);
      if (g.shield) glow(x0, G - g.y - 28, 40, "rgba(125,255,176,.22)");
      if (!(g.inv && Math.floor(now * 12) % 2)) runner(x0, G - g.y, g.ph, g.slide ? "slide" : g.kick ? "kick" : g.y > 0 ? "air" : "run", SAUL, Math.min(1.3, (speed() - 220) / 300));
      const wind = (speed() - 400) / 300;  // fast: wind lines behind Saul
      if (wind > 0 && !g.y && !g.slide) { cx.fillStyle = `rgba(230,228,240,${Math.min(.35, wind)})`; for (let i = 0; i < 3; i++) box(x0 - 26 - ((now * 900 + i * 37) % 60), G - 14 - i * 17, 18 + i * 4, 1.5); }
      if (g.boost) { cx.fillStyle = "rgba(140,220,110,.5)"; for (let i = 0; i < 3; i++) box(x0 - 30 - i * 12 - (now * 300 % 12), G - 20 - g.y - i * 12, 14, 2); }
      // HUD: clock and points, the way to the Planet, lives, the colete, L-I-S-T-A, pilas
      const at = K.t0 + g.t * K.k;
      txt(clk(at), 14, 30, "700 24px 'Barlow Condensed',sans-serif", at > K.gol ? "#ff7a45" : "#f2f2ee", "left");
      txt(`${g.pts.toLocaleString("pt-BR")} pts`, 14, 50, "700 15px 'Barlow Condensed',sans-serif", "#d8d6e0", "left");
      txt(`${Math.round(speed() * KMH)} km/h`, 14, 68, "700 13px 'Barlow Condensed',sans-serif", g.boost ? "#9be07a" : "#a9a6b8", "left");
      if (mult() > 1) txt(`x${mult()}`, 14 + cx.measureText(`${g.pts.toLocaleString("pt-BR")} pts`).width + 8, 50, "800 15px 'Barlow Condensed',sans-serif", "#ff7a9a", "left");
      const hw = 22 * g.max + (g.lives > g.max ? 22 : 0), bx0 = 108, bw = Math.max(60, W - bx0 - hw - 92), p = g.x / K.len;
      box(bx0, 19, bw, 6, "rgba(255,255,255,.14)"); box(bx0, 19, bw * p, 6, "#ff4a6e");
      if (g.king.st === "off" || g.king.st === "intro" || g.king.st === "luta") crown(bx0 + bw * K.rei[0] / K.len, 17, .6);
      cx.fillStyle = "#ff4a6e"; cx.beginPath(); cx.arc(bx0 + bw * p, 22, 6, 0, 7); cx.fill();
      txt("PLANET", bx0 + bw + 8, 27, "800 13px 'Barlow Condensed',sans-serif", "#7dffb0", "left");
      for (let i = 0; i < Math.max(g.max, g.lives); i++) heart(W - 20 - i * 22, 13, i < g.lives ? "#ff4a6e" : "rgba(255,255,255,.18)");
      [..."LISTA"].forEach((l, i) => txt(l, W - 106 + i * 19, 50, "800 14px 'Barlow Condensed',sans-serif", g.letras.includes(l) ? "#f2c230" : "rgba(255,255,255,.2)"));
      txt(`R$ ${g.pilas}`, W - 14, 68, "700 13px 'Barlow Condensed',sans-serif", "#9be07a", "right");
      if (g.shield) txt("COLETE", W - 60, 68, "800 12px 'Barlow Condensed',sans-serif", "#7dffb0", "right");
      for (const q of g.pops) {
        const life = q.big ? 3 : 1.8, k = q.t < .12 ? .5 + q.t / .12 * .7 : q.t < .24 ? 1.2 - (q.t - .12) / .12 * .2 : 1;  // pops in a little too big, then settles
        cx.save(); cx.globalAlpha = Math.max(0, Math.min(1, (life - q.t) / (life * .35)));
        cx.translate(q.big ? W / 2 : x0 + 30, q.big ? q.y : q.y - q.t * 22); cx.scale(k, k);
        cx.font = q.big ? `800 ${Math.min(40, W / 12)}px 'Barlow Condensed',sans-serif` : "800 20px 'Barlow Condensed',sans-serif"; cx.textAlign = q.big ? "center" : "left";
        cx.lineJoin = "round"; cx.lineWidth = q.big ? 6 : 4; cx.strokeStyle = "rgba(8,6,16,.85)"; cx.strokeText(q.txt, 0, 0);
        if (q.big) { cx.shadowColor = q.c; cx.shadowBlur = 16; }
        cx.fillStyle = q.c; cx.fillText(q.txt, 0, 0); cx.restore();
      }
      if (g.badge) {  // a new achievement: a gold tag under the HUD
        const b = g.badge, k = Math.min(1, b.t * 6), s = `🏅 ${b.txt}`;
        cx.save(); cx.globalAlpha = Math.min(1, (2.6 - b.t) * 3); cx.font = "800 16px 'Barlow Condensed',sans-serif";
        const w = cx.measureText(s).width + 28, y = 74 + 10 * k;
        cx.fillStyle = "rgba(20,16,6,.88)"; cx.beginPath(); cx.roundRect(W / 2 - w / 2, y, w, 26, 13); cx.fill();
        cx.strokeStyle = "#f2c230"; cx.lineWidth = 1.5; cx.stroke();
        txt("CONQUISTA", W / 2, y - 3, "800 10px 'Barlow Condensed',sans-serif", "#f2c230"); txt(s, W / 2, y + 18, "800 16px 'Barlow Condensed',sans-serif", "#ffe7a0");
        cx.restore();
      }
      hints(now);
      const br = g.dia.slice(8) + "/" + g.dia.slice(5, 7);
      if (g.mode === "pronto") scrim("CORRE, SAUL!", "Toque para correr até o Planet", "#fff", `A rua de ${br}: a mesma para todo mundo hoje`);
      else if (g.mode === "pausa") scrim("PAUSA", "Toque para continuar");
      else if (g.mode === "fim") g.won ? scrim(`${g.pts.toLocaleString("pt-BR")} PONTOS`, `Chegou no Planet às ${clk(g.at)}${g.at <= K.gol ? ", a tempo!" : ", atrasado"}`, "#7dffb0", "Toque para correr de novo")
        : scrim("JOGO CANELADO", `${g.pts.toLocaleString("pt-BR")} pontos. Toque para tentar de novo`, "#ff4a6e");
    };

    // ---------- the share card: 1080x1350, drawn with the game's own art
    async function shareCard() {
      const c = document.createElement("canvas"); c.width = 1080; c.height = 1350;
      const old = cx; cx = c.getContext("2d");
      try {
        const w = 1080, h = 1350, gnd = 1010;
        sky(w, h, gnd);
        cx.save(); cx.translate(0, gnd); cx.scale(2.6, 2.6); cx.translate(0, -gnd / 2.6); skyline(w / 2.6, gnd / 2.6, 500); cx.restore();
        box(0, gnd, w, h - gnd, "#17151c"); box(0, gnd, w, 46, "#2b2731"); box(0, gnd, w, 7, "#4a4552");
        cx.save(); cx.translate(640, gnd); cx.scale(5, 5); runner(0, 0, 1.2, "air", SAUL); cx.restore();
        if (g.ach.has("rei")) crown(910, gnd - 30, 5);
        if (g.ach.has("saulnaro")) ele(935, 1170, 4.6);
        box(0, 0, w, 420, "rgba(6,5,14,.55)");
        glow(900, 190, 200, "rgba(255,240,210,.12)"); cx.fillStyle = "#f4ecd8"; cx.beginPath(); cx.arc(900, 190, 56, 0, 7); cx.fill();
        txt("BIOFUT · CORRE, SAUL!", 72, 110, "600 40px 'Barlow',sans-serif", "#bdb9cc", "left");
        txt(g.pts.toLocaleString("pt-BR"), 66, 290, "800 200px 'Barlow Condensed',sans-serif", "#fff", "left");
        txt("PONTOS", 72, 360, "800 56px 'Barlow Condensed',sans-serif", "#ff4a6e", "left");
        const line = g.won ? `Chegou no Planet às ${clk(g.at)}${g.at <= K.gol ? ", a tempo" : ", atrasado"}` : "Jogo canelado: tropeçou demais";
        txt(line, 72, 490, "700 52px 'Barlow Condensed',sans-serif", g.won ? "#7dffb0" : "#ff7a9a", "left");
        const extra = [g.pos && `${g.pos}º na corrida de hoje`, g.ach.has("rei") && "Derrubou o BioFut King", g.coins && `+${coin(g.coins)} moeda`].filter(Boolean);
        extra.forEach((s, i) => txt(s, 72, 556 + i * 52, "600 40px 'Barlow',sans-serif", "#e4e2ec", "left"));
        box(0, h - 150, w, 150, "#0b0a14");
        txt(ME ? nm(ME) : `Rua de ${g.dia.slice(8)}/${g.dia.slice(5, 7)}`, 72, h - 62, "800 48px 'Barlow Condensed',sans-serif", "#fff", "left");
        txt("biofut.h-brain.org/#/corre", w - 72, h - 62, "600 34px 'Barlow',sans-serif", "#ff4a6e", "right");
        ["#ff4a6e", "#f06060", "#f2c230", "#480078"].forEach((col, i) => box(i * w / 4, h - 12, w / 4, 12, col));
      } finally { cx = old; }
      const blob = await new Promise(r => c.toBlob(r, "image/png"));
      const text = `Corre, Saul! ${g.pts.toLocaleString("pt-BR")} pontos${g.won ? `, cheguei no Planet às ${clk(g.at)}` : ", jogo canelado"}. Tenta bater: https://biofut.h-brain.org/#/corre`;
      const file = new File([blob], "corre-saul.png", {type: "image/png"});
      BF.ev("corre_saul", "share");
      if (navigator.canShare?.({files: [file]})) { try { await navigator.share({files: [file], text}); return; } catch (e) { if (e.name === "AbortError") return; } }
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "corre-saul.png"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      if (navigator.share) { toast("Imagem salva"); try { await navigator.share({text}); return; } catch (e) { if (e.name === "AbortError") return; } }  // a phone that can't share files: the text through the share sheet
      try { await navigator.clipboard.writeText(text); toast("Imagem salva e texto copiado: cole no grupo"); } catch { toast("Imagem salva"); }
    }

    for (const o of [...g.fix, ...g.obs]) if (o.name && !faces[o.name]) { const f = face(slug(o.name)); if (f) { faces[o.name] = new Image(); faces[o.name].src = f; } }
    const loop = ts => {
      if (!cv.isConnected) return ac.abort();  // left the page (render() rebuilt it): stop drawing and listening
      const dt = Math.min(.033, (ts - (last || ts)) / 1000); last = ts; g.seen = performance.now();
      if (g.mode === "corre") {
        const k = g.sm > 0 ? .4 : 1, n = Math.ceil(dt / .012);
        g.sm = Math.max(0, g.sm - dt);
        for (let i = 0; i < n && g.mode === "corre"; i++) step(dt * k / n);
      }
      draw(ts / 1000);
      requestAnimationFrame(loop);
    };
    if (g.mode !== "corre") menu();
    document.fonts?.ready.then(() => requestAnimationFrame(loop));
  }
  return Corre;
})();
