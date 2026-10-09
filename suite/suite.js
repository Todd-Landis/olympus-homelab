/* Olympus Suite: shared masthead, sun-and-moon sky, Oracle command palette, toasts, number tweening. */
(() => {
  const APPS = [
    { id: "olympus", name: "Overview", url: "http://helios/", blurb: "All machines and services" },
    { id: "netwatch", name: "Network", url: "http://helios:8095/", blurb: "Browsing activity and blocking" },
    { id: "horae", name: "Horae", url: "http://horae/", blurb: "Pi dashboard: DNS and home" },
  ];
  const LAT = 39.88, LON = -83.09; // Grove City, OH: drives the sun's real arc

  // Shown inside Olympus' app panel: drop our own masthead (Olympus already has one) so links don't nest the suite.
  const embedded = window.self !== window.top;
  if (embedded) document.documentElement.classList.add("embedded");
  let openApp = null; // set by mount(): returns true if the page opened the app itself (Olympus shows it in a tab)
  const go = (a) => { if (!(openApp && openApp(a))) location.href = a.url; };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (s, r = document) => r.querySelector(s);

  // ---------------------------------------------------------------- sun + moon
  function sunTimes(d) {
    const rad = Math.PI / 180, start = Date.UTC(d.getFullYear(), 0, 0);
    const n = Math.floor((Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) - start) / 864e5);
    const g = (2 * Math.PI / 365) * (n - 1);
    const eq = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
    const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
    const ha = Math.acos(Math.cos(90.833 * rad) / (Math.cos(LAT * rad) * Math.cos(decl)) - Math.tan(LAT * rad) * Math.tan(decl)) / rad;
    const midnight = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
    return { rise: new Date(midnight + (720 - 4 * (LON + ha) - eq) * 6e4), set: new Date(midnight + (720 - 4 * (LON - ha) - eq) * 6e4) };
  }
  const hm = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  function drawSky() {
    const el = $(".mast-sky");
    if (!el) return;
    const now = new Date(), { rise, set } = sunTimes(now);
    const day = now >= rise && now <= set;
    let t;
    if (day) t = (now - rise) / (set - rise);
    else {
      const prevSet = now < rise ? new Date(set - 864e5) : set, nextRise = now < rise ? rise : new Date(+rise + 864e5);
      t = (now - prevSet) / (nextRise - prevSet);
    }
    // A quiet arc: the day's progress from sunrise to sunset (or through the night), as one small dot.
    const W = 84, H = 26, x = 4 + t * (W - 8), y = H - 3 - Math.sin(Math.PI * t) * (H - 9);
    const dot = day ? `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.6" fill="#c98a12"/>`
                    : `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.4" fill="#fff" stroke="#a9a399" stroke-width="1.2"/>`;
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${day ? "Daylight" : "Night"}: sunrise ${hm(rise)}, sunset ${hm(set)}">
      <title>Sunrise ${hm(rise)} · sunset ${hm(set)}</title>
      <path d="M4 ${H - 3} Q ${W / 2} ${-H + 14} ${W - 4} ${H - 3}" fill="none" stroke="#d8d1c3" stroke-width="1.2" stroke-dasharray="1.5 3" stroke-linecap="round"/>
      <line x1="0" x2="${W}" y1="${H - 3}" y2="${H - 3}" stroke="#e7e2d8" stroke-width="1"/>${dot}</svg>`;
  }

  // ---------------------------------------------------------------- masthead
  function mount({ app, title, open }) {
    openApp = open || null;
    const host = $("#masthead");
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
    host.innerHTML = `
      <header class="mast">
        <a class="mast-brand" href="${APPS[0].url}"><b>Olympus</b>${title ? `<i>${esc(title)}</i>` : ""}</a>
        <nav class="suite-nav" aria-label="Apps">
          ${APPS.map((a) => `<a href="${a.url}" ${a.id === app ? 'aria-current="page"' : ""}>${esc(a.name)}</a>`).join("")}
        </nav>
        <div class="mast-right">
          <span class="status-pill" id="suite-live"><span class="dot"></span>Connecting</span>
          <span class="mast-sky"></span>
          <span class="clock" id="suite-clock"></span>
          <button class="search-btn" id="oracle-open" title="Search and run commands">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4" stroke-linecap="round"/></svg>
            <span>Search</span><kbd>${isMac ? "⌘" : "Ctrl"} K</kbd></button>
        </div>
      </header>
      <div class="rule"></div>`;
    $("#oracle-open").addEventListener("click", () => Oracle.open());
    $(".suite-nav").addEventListener("click", (e) => {
      const el = e.target.closest("a"), a = el && APPS.find((x) => x.url === el.getAttribute("href"));
      if (!a || e.button || e.ctrlKey || e.metaKey || e.shiftKey || !openApp) return;
      if (openApp(a)) e.preventDefault();
    });
    const tick = () => { const c = $("#suite-clock"); if (c) c.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); };
    tick(); setInterval(tick, 1000 * 15);
    drawSky(); setInterval(drawSky, 60000);
  }
  function setLive(ok, text) {
    const el = $("#suite-live");
    if (el) el.innerHTML = `<span class="dot ${ok ? "ok live" : "bad"}"></span>${esc(text || (ok ? "Live" : "Reconnecting"))}`;
  }

  // ---------------------------------------------------------------- toast
  function toast(msg) {
    let t = $("#suite-toast");
    if (!t) { t = document.createElement("div"); t.id = "suite-toast"; t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("show"), 2800);
  }

  // ---------------------------------------------------------------- number tweening
  // Elements with data-tw="key" data-v="123" count from their previous value to the new one.
  const twPrev = new Map();
  function tween(root = document) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    root.querySelectorAll("[data-tw]").forEach((el) => {
      const key = el.dataset.tw, to = Number(el.dataset.v), from = twPrev.get(key);
      twPrev.set(key, to);
      if (from == null || from === to || !isFinite(to)) return;
      const fmt = el.dataset.fmt || "int", t0 = performance.now(), D = 650;
      const show = (v) => { el.textContent = fmt === "pct" ? `${Math.round(v)}%` : Math.round(v).toLocaleString(); };
      const step = (now) => {
        const p = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - p, 3);
        show(from + (to - from) * e);
        if (p < 1 && el.isConnected) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  // ---------------------------------------------------------------- the Oracle (command palette)
  const providers = [];
  const Oracle = {
    items: [], sel: 0,
    register(fn) { providers.push(fn); },
    open(q = "") {
      if (!$("#oracle")) build();
      $("#oracle").classList.add("open");
      const input = $("#oracle-q");
      input.value = q; input.focus();
      this.search();
    },
    close() { $("#oracle")?.classList.remove("open"); },
    async search() {
      const q = $("#oracle-q").value.trim().toLowerCase();
      const base = APPS.map((a) => ({ group: "Go to", icon: a.name[0], title: a.name, sub: a.blurb, run: () => go(a) }));
      const lists = await Promise.all(providers.map((p) => Promise.resolve(p(q)).catch(() => [])));
      const all = [...base, ...lists.flat()];
      const scored = all.map((it) => ({ it, s: score(q, it) })).filter((x) => x.s > 0);
      scored.sort((a, b) => b.s - a.s);
      // Keep each group together (groups ordered by their best match), at most 8 per group.
      const groups = new Map();
      for (const { it } of scored) {
        if (!groups.has(it.group)) groups.set(it.group, []);
        const g = groups.get(it.group);
        if (!q || g.length < 8) g.push(it);
      }
      this.items = [...groups.values()].flat().slice(0, 60);
      this.sel = 0;
      this.render();
    },
    render() {
      const list = $("#oracle-list");
      if (!this.items.length) { list.innerHTML = `<div class="empty">No matches.</div>`; return; }
      let html = "", group = null;
      this.items.forEach((it, i) => {
        if (it.group !== group) { group = it.group; html += `<div class="oracle-group">${esc(group)}</div>`; }
        html += `<div class="oracle-item ${i === this.sel ? "on" : ""}" data-i="${i}"><span class="ic">${esc(it.icon || "•")}</span>
          <div style="min-width:0"><div class="t">${esc(it.title)}</div>${it.sub ? `<div class="s">${esc(it.sub)}</div>` : ""}</div>${it.hint ? `<span class="k">${esc(it.hint)}</span>` : ""}</div>`;
      });
      list.innerHTML = html;
      list.querySelector(".oracle-item.on")?.scrollIntoView({ block: "nearest" });
    },
    run(i) { const it = this.items[i]; if (!it) return; this.close(); it.run(); },
  };
  // Substring matches anywhere win; otherwise a tight in-order match on the title only (typo-tolerant, not scattershot).
  function score(q, it) {
    if (!q) return 1;
    const title = it.title.toLowerCase(), rest = `${it.sub || ""} ${it.keywords || ""}`.toLowerCase();
    const at = title.indexOf(q);
    if (at >= 0) return 200 - Math.min(at, 50) - title.length / 100;
    if (rest.includes(q)) return 90;
    let ti = 0, s = 0, gaps = 0;
    for (const ch of q) { const f = title.indexOf(ch, ti); if (f < 0) return 0; if (f !== ti && ti) gaps++; s += f === ti ? 3 : 1; ti = f + 1; }
    return gaps <= 1 && q.length >= 3 ? s : 0;
  }
  function build() {
    const el = document.createElement("div");
    el.id = "oracle"; el.className = "oracle";
    el.innerHTML = `<div class="oracle-box" role="dialog" aria-label="Search">
      <div class="oracle-in"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4" stroke-linecap="round"/></svg>
        <input id="oracle-q" placeholder="Search machines, services, containers, sites…" autocomplete="off" spellcheck="false"></div>
      <div class="oracle-list" id="oracle-list"></div>
      <div class="oracle-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span></div></div>`;
    document.body.appendChild(el);
    el.addEventListener("click", (e) => {
      if (e.target === el) return Oracle.close();
      const it = e.target.closest(".oracle-item"); if (it) Oracle.run(+it.dataset.i);
    });
    el.addEventListener("mousemove", (e) => {
      const it = e.target.closest(".oracle-item");
      if (it && +it.dataset.i !== Oracle.sel) { Oracle.sel = +it.dataset.i; Oracle.render(); }
    });
    let deb;
    $("#oracle-q").addEventListener("input", () => { clearTimeout(deb); deb = setTimeout(() => Oracle.search(), 60); });
    $("#oracle-q").addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); Oracle.sel = Math.min(Oracle.items.length - 1, Oracle.sel + 1); Oracle.render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); Oracle.sel = Math.max(0, Oracle.sel - 1); Oracle.render(); }
      else if (e.key === "Enter") { e.preventDefault(); Oracle.run(Oracle.sel); }
      else if (e.key === "Escape") Oracle.close();
    });
  }
  document.addEventListener("keydown", (e) => {
    const typing = /input|textarea|select/i.test(document.activeElement?.tagName || "");
    if ((e.key === "k" || e.key === "K") && (e.ctrlKey || e.metaKey)) { e.preventDefault(); Oracle.open(); }
    else if (e.key === "/" && !typing) { e.preventDefault(); Oracle.open(); }
  });

  // View transitions when the browser supports them (Chrome, Edge, Safari 18+).
  function transition(fn) {
    if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) return document.startViewTransition(fn);
    fn();
  }

  window.Suite = { mount, setLive, toast, tween, Oracle, esc, transition, APPS, embedded };
})();
