// Shared shell for every BioFut page: header + tabs, theme, who is logged in, and the activity beacon (/admin, Atividade).
// Load it as the first thing in <body>; it writes the header synchronously, so nothing jumps. Exposes window.BF.
(() => {
  "use strict";
  const store = {get: k => { try { return localStorage.getItem(k) } catch { return null } }, set: (k, v) => { try { localStorage.setItem(k, v) } catch {} }};
  if (store.get("biofutTheme")) document.documentElement.dataset.theme = store.get("biofutTheme");
  // a [name, [...tabs]] entry is a category: <details> that drops a row of its tabs under the header (Gab, 2026-10-16: too many tabs)
  const tabs = [["/#/", "Início"], ["/#/jogo", "Jogo da semana"], ["/#/copa", "Copa"], ["Futebol", [["/#/tabela", "Tabela"], ["/#/jogos", "Jogos"], ["/wiki", "Wiki"]]],
    ["Jogar", [["/#/cartas", "Cartas"], ["/#/deck", "Deck"], ["/#/duelo", "Duelo"], ["/#/truco", "BioTruco"], ["/#/biobet", "BioBet"]]],
    ["Grupo", [["/#/resenha", "Resenha"], ["/#/radio", "Rádio"], ["/transparencia", "Transparência"], ["/#/apoie", "Apoie"]]]];
  const tab = ([h, t]) => Array.isArray(t) ? `<details class="grp"><summary>${h}</summary><div class="menu">${t.map(tab).join("")}</div></details>` : `<a href="${h}">${t}</a>`;
  document.body.insertAdjacentHTML("afterbegin", `<header class="top"><div class="bar">
  <a class="brand" href="/#/"><img src="/logo.png" alt=""><span>Bio<b>Fut</b></span></a>
  <nav class="tabs" id="nav">${tabs.map(tab).join("")}</nav>
  <button class="theme" id="theme" aria-label="Trocar tema"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/></svg></button>
  <a class="theme" href="/entrar" id="me" aria-label="Entrar" title="Entrar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg></a>
</div></header>`);
  const page = location.pathname.replace(/\.html$/, "").replace(/^\/index$/, "/");
  // the home page marks its own tab per #/route (index.html render()); the others are one tab each
  if (page !== "/") document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.getAttribute("href") === page));
  // one category open at a time; a click outside it or on one of its tabs closes it
  document.addEventListener("click", e => document.querySelectorAll("#nav details[open]").forEach(d => (!d.contains(e.target) || e.target.closest("a")) && d.removeAttribute("open")));
  addEventListener("hashchange", () => document.querySelectorAll("#nav details[open]").forEach(d => d.removeAttribute("open")));
  document.getElementById("theme").onclick = () => {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches, cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = next; store.set("biofutTheme", next);
  };

  // what people do here -> POST /api/ev -> data/events.jsonl (no IPs; visitors are a daily hash, members their name)
  const ev = (e, d) => { try { navigator.sendBeacon("/api/ev", JSON.stringify({e, p: location.pathname + location.hash, d: String(d ?? "").slice(0, 120)})) } catch {} };
  ev("view", document.referrer && !document.referrer.startsWith(location.origin) ? document.referrer.split("/")[2] : "");
  addEventListener("hashchange", () => ev("view"));
  addEventListener("error", e => ev("js_error", `${e.message} @${(e.filename || "").split("/").pop()}:${e.lineno}`));
  addEventListener("unhandledrejection", e => ev("js_error", e.reason?.message || e.reason));
  document.addEventListener("click", e => {
    const a = e.target.closest("a,button,summary");
    if (a) ev("click", (a.dataset.ev || a.getAttribute("aria-label") || a.textContent || a.getAttribute("href") || "").trim().replace(/\s+/g, " ").slice(0, 60));
  }, true);

  const me = fetch("/api/me").then(r => r.json()).catch(() => ({user: null}));
  const link = document.getElementById("me");
  me.then(m => {
    if (m.user) { link.dataset.user = m.user; link.href = "/#/eu"; link.title = m.user + " · sua página"; link.ariaLabel = "Sua página"; link.classList.add("in"); }
    if (m.role === "admin" || m.role === "conselho") document.getElementById("nav").insertAdjacentHTML("beforeend", '<a href="/admin">Painel</a>');  // Gab and the Conselho
  });
  link.addEventListener("click", () => { if (!link.dataset.user) link.href = "/entrar?next=" + encodeURIComponent(location.pathname + location.hash); });
  window.BF = {me, ev};
})();
