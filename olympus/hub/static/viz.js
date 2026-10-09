/* Olympus charts: interactive network and machine charts for chat answers, drawn with Apache ECharts.
   Colours are the validated categorical palette (checked against the white card surface): allowed = slot 1 blue,
   blocked = slot 2 orange, people/devices take slots in a fixed order, heatmaps use one blue ramp.
   Every chart has a table view, a hover tooltip, and click-to-drill-down where a deeper question makes sense. */
(() => {
  const { esc } = Suite;
  const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
  const ALLOWED = SERIES[0], BLOCKED = SERIES[1];
  const SEQ = ["#e8f1fc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
  const INK = "#1d1c1a", INK2 = "#4a4741", MUTED = "#6b665e", GRID = "#f1ede5", AXIS = "#d8d1c3", SURFACE = "#ffffff";
  const FONT = '"Inter", "Segoe UI", system-ui, sans-serif';
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const N = (n) => (n ?? 0).toLocaleString();
  const when = (t) => new Date(t * 1000).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const hourLabel = (h) => new Date(2026, 0, 1, h).toLocaleTimeString([], { hour: "numeric" });

  const base = () => ({
    animationDuration: 250, animationEasing: "cubicOut", animationDurationUpdate: 200,
    textStyle: { fontFamily: FONT, color: INK2, fontSize: 12 },
    grid: { left: 8, right: 16, top: 34, bottom: 8, containLabel: true },
    tooltip: {
      confine: true, backgroundColor: SURFACE, borderColor: "#e7e2d8", borderWidth: 1, padding: [8, 10],  // confine: never past the chart edge
      textStyle: { color: INK, fontFamily: FONT, fontSize: 12.5 },
      extraCssText: "box-shadow: 0 6px 24px rgba(40,32,20,.10); border-radius: 10px;",
    },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10, icon: "roundRect", textStyle: { color: INK2, fontSize: 12 } },
  });
  const axisCommon = {
    axisLine: { lineStyle: { color: AXIS } }, axisTick: { show: false },
    axisLabel: { color: MUTED, fontSize: 11.5 }, splitLine: { lineStyle: { color: GRID, type: "solid" } },
  };
  // Tooltip rows: value first (strong), then a short line-key and the series name. Names arrive escaped.
  const row = (color, value, name) => `<div style="display:flex;align-items:center;gap:8px;margin-top:3px"><span style="width:10px;height:2px;background:${color};display:inline-block"></span><b style="min-width:52px">${value}</b><span style="color:${MUTED}">${name}</span></div>`;

  // ---------------------------------------------------------------- one chart per network grouping

  const RANKED = { site: "site", domain: "domain", device: "device", person: "person" };

  function timeChart(t) {
    const size = t.group === "hour" ? 3600 : 86400;
    const rows = t.rows;
    return {
      ...base(),
      tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(42,120,214,.06)" } },
        formatter: (ps) => {
          const r = rows[ps[0].dataIndex];
          return `<div style="color:${MUTED}">${esc(when(r.t))}${t.group === "day" ? "" : " – " + new Date((r.t + size) * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</div>`
            + row(ALLOWED, N(r.queries - r.blocked), "allowed") + row(BLOCKED, N(r.blocked), "blocked")
            + `<div style="color:${MUTED};margin-top:6px;font-size:11.5px">Click to list these lookups</div>`;
        } },
      xAxis: { type: "category", data: rows.map((r) => r.t), ...axisCommon, splitLine: { show: false },
        axisLabel: { ...axisCommon.axisLabel, hideOverlap: true,
          formatter: (v) => new Date(v * 1000).toLocaleString([], t.group === "day" ? { month: "short", day: "numeric" } : { weekday: "short", hour: "numeric" }) } },
      yAxis: { type: "value", ...axisCommon, axisLine: { show: false }, minInterval: 1 },
      dataZoom: rows.length > 48 ? [{ type: "inside" }, { type: "slider", height: 18, bottom: 0, borderColor: GRID, fillerColor: "rgba(42,120,214,.10)", handleStyle: { color: ALLOWED }, textStyle: { color: MUTED } }] : [{ type: "inside" }],
      grid: { ...base().grid, bottom: rows.length > 48 ? 30 : 8 },
      series: [
        { name: "Allowed", type: "bar", stack: "n", data: rows.map((r) => r.queries - r.blocked), itemStyle: { color: ALLOWED, borderColor: SURFACE, borderWidth: 1 }, barMaxWidth: 24, cursor: "pointer" },
        { name: "Blocked", type: "bar", stack: "n", data: rows.map((r) => r.blocked), itemStyle: { color: BLOCKED, borderColor: SURFACE, borderWidth: 1, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 24, cursor: "pointer" },
      ],
      _height: 260,
      _drill: (p) => { const r = rows[p.dataIndex]; return [{ start: r.t, end: r.t + size, group: "none", limit: 200 }, `Lookups ${when(r.t)}`]; },
    };
  }

  function rankedChart(t) {
    const rows = [...t.rows].reverse(); // largest on top
    const names = rows.map((r) => r.name);
    return {
      ...base(),
      grid: { ...base().grid, right: 56 },
      tooltip: { ...base().tooltip, trigger: "item",
        formatter: (p) => {
          const r = rows[p.dataIndex];
          const who = r.people?.length ? `<div style="color:${MUTED}">Used by ${esc(r.people.join(", "))}</div>` : "";
          return `<b>${esc(r.name)}</b>${who}` + row(ALLOWED, N(r.queries - r.blocked), "allowed") + row(BLOCKED, N(r.blocked), "blocked")
            + `<div style="color:${MUTED};margin-top:6px;font-size:11.5px">Last ${esc(when(r.last))}${t.group === "person" && r.name === "Unassigned" ? "" : " · click to dig in"}</div>`;
        } },
      xAxis: { type: "value", ...axisCommon, axisLabel: { ...axisCommon.axisLabel, hideOverlap: true }, minInterval: 1 },
      yAxis: { type: "category", data: names, ...axisCommon, splitLine: { show: false },
        axisLabel: { color: INK2, fontSize: 12.5, width: 180, overflow: "truncate" } },
      series: [
        { name: "Allowed", type: "bar", stack: "n", data: rows.map((r) => r.queries - r.blocked), itemStyle: { color: ALLOWED, borderColor: SURFACE, borderWidth: 1 }, barMaxWidth: 18, cursor: "pointer" },
        { name: "Blocked", type: "bar", stack: "n", data: rows.map((r) => r.blocked), itemStyle: { color: BLOCKED, borderColor: SURFACE, borderWidth: 1, borderRadius: [0, 4, 4, 0] }, barMaxWidth: 18, cursor: "pointer",
          label: { show: true, position: "right", color: MUTED, fontSize: 11.5, formatter: (p) => N(rows[p.dataIndex].queries) } },
      ],
      _height: Math.max(140, rows.length * 26 + 50),
      _drill: (p) => {
        const r = rows[p.dataIndex], span = t.end - t.start, g = span <= 3 * 86400 ? "hour" : "day";
        if (t.group === "site" || t.group === "domain") return [{ domain: r.name, group: g }, `${r.name} by ${g}`];
        if (t.group === "device") return [{ device: r.name, group: "site" }, `Top sites on ${r.name}`];
        if (t.group === "person" && r.name !== "Unassigned") return [{ person: r.name, group: "site" }, `Top sites for ${r.name}`];
        return null;
      },
    };
  }

  function heatChart(t) {
    const max = Math.max(1, ...t.rows.map((r) => r.queries));
    return {
      ...base(),
      grid: { left: 8, right: 12, top: 8, bottom: 44, containLabel: true },
      tooltip: { ...base().tooltip, trigger: "item",
        formatter: (p) => `<div style="color:${MUTED}">${DAYS[p.value[1]]} ${esc(hourLabel(p.value[0]))}</div><b>${N(p.value[2])}</b> <span style="color:${MUTED}">lookups</span>` },
      xAxis: { type: "category", data: [...Array(24).keys()], ...axisCommon, splitLine: { show: false }, axisLine: { show: false },
        axisLabel: { ...axisCommon.axisLabel, interval: 2, formatter: (h) => hourLabel(+h) } },
      yAxis: { type: "category", data: DAYS, inverse: true, ...axisCommon, splitLine: { show: false }, axisLine: { show: false }, axisLabel: { color: INK2, fontSize: 12 } },
      visualMap: { min: 0, max, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 10, itemHeight: 160,
        inRange: { color: SEQ }, textStyle: { color: MUTED, fontSize: 11 }, text: [N(max), "0"] },
      series: [{ type: "heatmap", data: t.rows.map((r) => [r.hour, r.weekday, r.queries]),
        itemStyle: { borderColor: SURFACE, borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: INK, borderWidth: 1 } } }],
      _height: 290,
    };
  }

  function lookupsChart(t) {
    const devices = [...new Set(t.rows.map((r) => r.device))];
    const pts = (blocked) => t.rows.map((r, i) => ({ r, i })).filter((x) => x.r.blocked === blocked).map((x) => ({ value: [x.r.t * 1000, x.r.device], idx: x.i }));
    const tip = (p) => { const r = t.rows[p.data.idx]; return `<div style="color:${MUTED}">${esc(when(r.t))} · ${esc(r.device)}</div><b>${esc(r.domain)}</b>${r.blocked ? ` <span style="color:${MUTED}">blocked</span>` : ""}<div style="color:${MUTED};margin-top:6px;font-size:11.5px">Click for this domain over time</div>`; };
    const dot = (color) => ({ color, borderColor: SURFACE, borderWidth: 2 });
    return {
      ...base(),
      tooltip: { ...base().tooltip, trigger: "item", formatter: tip },
      xAxis: { type: "time", ...axisCommon, splitLine: { show: false }, axisLabel: { ...axisCommon.axisLabel, hideOverlap: true } },
      yAxis: { type: "category", data: devices, ...axisCommon, axisLabel: { color: INK2, fontSize: 12.5, width: 160, overflow: "truncate" } },
      dataZoom: [{ type: "inside", xAxisIndex: 0 }],
      series: [
        { name: "Allowed", type: "scatter", symbolSize: 10, data: pts(false), itemStyle: dot(ALLOWED), cursor: "pointer" },
        { name: "Blocked", type: "scatter", symbolSize: 10, data: pts(true), itemStyle: dot(BLOCKED), cursor: "pointer" },
      ],
      _height: Math.max(150, devices.length * 34 + 70),
      _drill: (p) => { const r = t.rows[p.data.idx], g = t.end - t.start <= 3 * 86400 ? "hour" : "day"; return [{ domain: r.domain, group: g }, `${r.domain} by ${g}`]; },
    };
  }

  function networkOption(t) {
    if (t.group === "hour" || t.group === "day") return timeChart(t);
    if (t.group === "weekday_hour") return heatChart(t);
    if (t.group === "none") return lookupsChart(t);
    if (RANKED[t.group]) return rankedChart(t);
    return null;
  }

  function networkTable(t) {
    const tr = (cells) => `<tr>${cells.join("")}</tr>`, td = (v, cls = "") => `<td class="${cls}">${v}</td>`;
    if (t.group === "none") return `<table class="ledger"><tr><th>Time</th><th>Device</th><th>Domain</th><th></th></tr>${t.rows.map((r) =>
      tr([td(esc(when(r.t)), "mono nowrap"), td(esc(r.device)), td(esc(r.domain), "brk"), td(r.blocked ? `<span class="badge bad">blocked</span>` : "")])).join("")}</table>`;
    if (t.group === "weekday_hour") return `<table class="ledger"><tr><th>Day</th><th>Hour</th><th class="r">Lookups</th><th class="r">Blocked</th></tr>${[...t.rows].sort((a, b) => b.queries - a.queries).map((r) =>
      tr([td(DAYS[r.weekday]), td(esc(hourLabel(r.hour))), td(N(r.queries), "r mono"), td(N(r.blocked), "r mono")])).join("")}</table>`;
    if (t.group === "hour" || t.group === "day") return `<table class="ledger"><tr><th>From</th><th class="r">Lookups</th><th class="r">Blocked</th></tr>${t.rows.map((r) =>
      tr([td(esc(when(r.t)), "mono nowrap"), td(N(r.queries), "r mono"), td(N(r.blocked), "r mono")])).join("")}</table>`;
    return `<table class="ledger"><tr><th>${esc(t.group[0].toUpperCase() + t.group.slice(1))}</th><th class="r">Lookups</th><th class="r">Blocked</th><th>Last</th></tr>${t.rows.map((r) =>
      tr([td(esc(r.name) + (r.people?.length ? `<div class="muted small">${esc(r.people.join(", "))}</div>` : "")), td(N(r.queries), "r mono"), td(N(r.blocked), "r mono"), td(esc(when(r.last)), "mono nowrap")])).join("")}</table>`;
  }

  // ---------------------------------------------------------------- machine history

  function hostOption(h) {
    const hist = (h.history || []).filter((p) => p.t);
    if (hist.length < 2) return null;
    const line = (name, key, color) => ({ name, type: "line", showSymbol: false, smooth: false, data: hist.map((p) => [p.t * 1000, p[key] == null ? null : +p[key].toFixed(1)]),
      lineStyle: { width: 2, color, cap: "round", join: "round" }, itemStyle: { color }, emphasis: { disabled: true } });
    const series = [line("CPU", "cpu", SERIES[0]), line("Memory", "mem", SERIES[1])];
    if (hist.some((p) => p.gpu != null)) series.push(line("GPU", "gpu", SERIES[2]));
    return {
      ...base(),
      tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: AXIS } },
        formatter: (ps) => `<div style="color:${MUTED}">${new Date(ps[0].value[0]).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</div>`
          + ps.map((p) => row(p.color, p.value[1] == null ? "–" : Math.round(p.value[1]) + "%", p.seriesName)).join("") },
      xAxis: { type: "time", ...axisCommon, splitLine: { show: false }, axisLabel: { ...axisCommon.axisLabel, hideOverlap: true } },
      yAxis: { type: "value", min: 0, max: 100, ...axisCommon, axisLine: { show: false }, axisLabel: { ...axisCommon.axisLabel, formatter: "{value}%" } },
      series,
      _height: 200,
    };
  }

  // ---------------------------------------------------------------- mounting

  // A series with nothing in it (e.g. "Allowed" when only blocked lookups were asked for) is dropped,
  // and a lone series gets no legend: the tile's title already says what it is.
  function tidy(opt) {
    if (!Array.isArray(opt.series) || opt.series.length < 2 || opt.series.some((s) => s.type === "heatmap")) return opt;
    const val = (d) => (Array.isArray(d) ? d[1] : d?.value ?? d);
    const keep = opt.series.filter((s) => s.type === "scatter" ? s.data.length : s.data.some((d) => +val(d) > 0));
    if (keep.length && keep.length < opt.series.length) {
      const last = keep[keep.length - 1], top = opt.series[opt.series.length - 1];
      if (last !== top && top.label) last.label = top.label;                   // the total label rides the outermost bar
      if (last !== top && top.itemStyle?.borderRadius) last.itemStyle = { ...last.itemStyle, borderRadius: top.itemStyle.borderRadius };
      opt.series = keep;
    }
    if (opt.series.length < 2) opt.legend = { show: false };
    return opt;
  }

  const live = new Set();
  function mount(el, option, onDrill) {
    if (!window.echarts || !option) return null;
    const { _height, _drill, ...rest } = option;
    const opt = tidy(rest);
    el.style.height = (_height || 240) + "px";
    const chart = echarts.init(el, null, { renderer: "canvas" });
    chart.setOption(opt);
    if (_drill && onDrill) chart.on("click", (p) => { if (p.componentType === "series") { const d = _drill(p); if (d) onDrill(...d); } });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    live.add({ el, chart, ro });
    return chart;
  }
  function disposeIn(root) {
    for (const x of [...live]) if (root.contains(x.el)) { x.ro.disconnect(); x.chart.dispose(); live.delete(x); }
  }

  window.Viz = { networkOption, networkTable, hostOption, mount, disposeIn, SERIES };
})();
