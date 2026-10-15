// Every screen worth looking at, for the UI skills (.claude/skills/ui-critique, ui-audit).
// Each state opens a URL and optionally drives the page into shape. Runs against dev/stack.sh.
// Add a state whenever you build a new screen or a new kind of chat tile.

const O = "http://127.0.0.1:9290", N = "http://127.0.0.1:9295";

export const viewports = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "phone", width: 390, height: 844, isMobile: true, hasTouch: true },
];

async function ask(page, ...questions) {
  for (const q of questions) {
    await page.fill("#ask-q", q);
    await page.press("#ask-q", "Enter");
    await page.waitForFunction(() => document.querySelector("#ask-go")?.textContent === "Ask", null, { timeout: 30000 });
  }
  await page.mouse.move(0, 0);       // no tooltip left hanging in the shot
  await page.waitForTimeout(800);     // chart entrance animation
}

export const states = [
  { name: "chat-empty", url: O + "/" },
  { name: "chat-status", url: O + "/", run: (p) => ask(p, "Is everything OK?") },
  { name: "chat-people", url: O + "/", run: (p) => ask(p, "Who used the network most this week?") },
  { name: "chat-heatmap", url: O + "/", run: (p) => ask(p, "When is the network usually busiest?") },
  { name: "chat-lookups", url: O + "/", run: (p) => ask(p, "What did the iPhone look up tonight?") },
  { name: "chat-logs", url: O + "/", run: (p) => ask(p, "Any errors in the pihole logs?") },
  { name: "chat-machine", url: O + "/", run: (p) => ask(p, "How is horae doing?") },
  { name: "chat-servers", url: O + "/", run: (p) => ask(p, "Is anyone on Dragonwilds?") },
  { name: "chat-adult", url: O + "/", run: (p) => ask(p, "Has anything looked up adult sites this week?") },
  {
    name: "chat-drilldown", url: O + "/",
    run: async (p) => {
      await ask(p, "Which sites were blocked most this week?");
      // click the biggest bar: ECharts draws on canvas, so find it through the chart instance
      const at = await p.evaluate(() => {
        const el = document.querySelector(".turn:last-child .viz");
        el.scrollIntoView({ block: "center" });
        const c = echarts.getInstanceByDom(el), o = c.getOption(), cats = o.yAxis[0].data, last = cats[cats.length - 1];
        const s = o.series.findIndex((x) => x.data.some((v) => v > 0));
        const [x, y] = c.convertToPixel({ seriesIndex: s }, [o.series[s].data[cats.length - 1] / 2, last]);
        const r = el.getBoundingClientRect();
        return [r.left + x, r.top + y];
      });
      await p.mouse.click(at[0], at[1]);
      await p.waitForSelector(".turn:last-child .crumb");
      await p.mouse.move(0, 0);
      await p.waitForTimeout(800);
    },
  },
  { name: "dashboard", url: O + "/#/dashboard", run: (p) => p.waitForSelector("#people-body tr[data-i]") },
  { name: "machine", url: O + "/#/host/helios", run: (p) => p.waitForSelector(".hero") },
  {
    name: "logs-drawer", url: O + "/#/host/helios",
    run: async (p) => { await p.click("[data-logs]"); await p.waitForSelector("#logs .ts"); await p.waitForTimeout(400); },
  },
  {
    name: "palette", url: O + "/#/dashboard",
    run: async (p) => { await p.waitForSelector(".host"); await p.click("#oracle-open"); await p.keyboard.type("ho"); await p.waitForTimeout(400); },
  },
  { name: "netwatch", url: N + "/" },
  { name: "netwatch-sites", url: N + "/", run: async (p) => { await p.click("#tabs [data-tab=sites]"); await p.waitForSelector("#sitetable tr[data-site]"); } },
  {
    name: "netwatch-site", url: N + "/",
    run: async (p) => { await p.click(".leaders li[data-site]"); await p.waitForSelector("#sheet .ledger"); await p.waitForTimeout(400); },
  },
];

// Stylesheets for the static motion check (ui-audit/scripts/motion-lint.mjs).
export const cssFiles = ["../../suite/suite.css", "../../suite/overrides.css", "../../olympus/hub/static/index.html", "../../pihole-watch/app/static/index.html"];
