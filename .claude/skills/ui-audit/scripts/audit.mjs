#!/usr/bin/env node
// Deterministic UI checks for every state at every viewport. No model involved; same input, same report.
//   node audit.mjs <states.mjs> [--only name,name] [--json <file>]
// Checks: axe-core WCAG 2.2 A/AA rules · horizontal page overflow · tap targets under 24px (WCAG 2.5.8, touch viewports)
//         · keyboard focus with no visible indicator · console errors. Exit code 1 if anything blocking is found.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
if (!args[0] || args[0].startsWith("--")) { console.error("usage: audit.mjs <states.mjs> [--only a,b] [--json file]"); process.exit(2); }
const statesPath = path.resolve(args[0]);
const req = createRequire(statesPath);
const { chromium } = req("playwright");
const axePath = req.resolve("axe-core/axe.min.js");
const { states, viewports } = await import(pathToFileURL(statesPath));
const only = opt("--only", "")?.split(",").filter(Boolean);

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
const report = [];
for (const vp of viewports) {
  for (const st of states.filter((s) => !only?.length || only.includes(s.name))) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: !!vp.isMobile, hasTouch: !!vp.hasTouch });
    const page = await ctx.newPage();
    const issues = [], add = (level, check, detail) => issues.push({ level, check, detail });
    page.on("pageerror", (e) => add("block", "console", e.message));
    page.on("console", (m) => m.type() === "error" && add("block", "console", m.text()));
    try {
      await page.goto(st.url, { waitUntil: "load" });
      await page.waitForTimeout(1000);
      if (st.run) await st.run(page);

      // 1. axe-core: WCAG 2.2 A and AA
      await page.addScriptTag({ path: axePath });
      const axe = await page.evaluate(() => axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] }, resultTypes: ["violations"] }));
      for (const v of axe.violations) {
        add(["serious", "critical"].includes(v.impact) ? "block" : "warn", `axe:${v.id}`,
          `${v.help} (${v.nodes.length}×) e.g. ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" ; ")}${v.nodes[0]?.failureSummary ? " → " + v.nodes[0].failureSummary.split("\n").slice(1, 2).join("").trim() : ""}`);
      }

      // 2. page wider than the screen (ignores things inside their own scroll/clip box)
      const over = await page.evaluate(() => {
        const extra = document.documentElement.scrollWidth - innerWidth;
        if (extra <= 1) return null;
        const clipped = (e) => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o !== "visible") return true; } return false; };
        const wide = [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 1 && !clipped(e))
          .slice(0, 3).map((e) => `${e.tagName.toLowerCase()}${e.id ? "#" + e.id : ""}${e.classList.length ? "." + [...e.classList].join(".") : ""}`);
        return `${extra}px too wide: ${wide.join(", ")}`;
      });
      if (over) add("block", "overflow", over);

      // 3. tap targets on touch screens (inline links inside sentences are exempt, as in WCAG 2.5.8)
      if (vp.hasTouch) {
        const small = await page.evaluate(() => [...document.querySelectorAll("a[href], button, input, select, textarea, [role=button], [tabindex]:not([tabindex='-1'])")]
          .filter((e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width && r.height && s.visibility !== "hidden" && (r.width < 24 || r.height < 24) && !(e.tagName === "A" && e.closest("p, li")); })
          .map((e) => `${(e.getAttribute("aria-label") || e.textContent || e.tagName).trim().slice(0, 30)} ${Math.round(e.getBoundingClientRect().width)}×${Math.round(e.getBoundingClientRect().height)}`));
        if (small.length) add("warn", "tap-target", `${small.length} under 24px: ${[...new Set(small)].slice(0, 6).join(" ; ")}`);
      }

      // 4. keyboard focus must be visible: Tab through the first 30 stops (desktop only)
      if (!vp.hasTouch) {
        const invisible = new Set();
        await page.locator("body").focus();
        for (let i = 0; i < 30; i++) {
          await page.keyboard.press("Tab");
          // Visible = focusing it changes the outline, shadow or border of the element or one of its two parents
          // (so a ring on a wrapper via :focus-within counts). Compare focused against blurred, then put focus back.
          const r = await page.evaluate(() => {
            const e = document.activeElement;
            if (!e || e === document.body) return null;
            const look = () => [e, e.parentElement, e.parentElement?.parentElement].filter(Boolean)
              .map((x) => { const s = getComputedStyle(x); return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.borderColor].join("|"); }).join("||");
            const on = look();
            e.blur();
            const off = look();
            e.focus();
            return on !== off ? "" : `${e.tagName.toLowerCase()}${e.id ? "#" + e.id : ""} "${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 24)}"`;
          });
          if (r === null) break;
          if (r) invisible.add(r);
        }
        if (invisible.size) add("block", "focus-visible", `no focus indicator on: ${[...invisible].slice(0, 6).join(" ; ")}`);
      }
    } catch (e) {
      add("block", "run", e.message.split("\n")[0]);
    }
    report.push({ state: st.name, viewport: vp.name, issues });
    const b = issues.filter((x) => x.level === "block").length, w = issues.length - b;
    console.log(`${b ? "✗" : w ? "!" : "✓"} ${st.name} @ ${vp.name}${issues.length ? `  (${b} blocking, ${w} warnings)` : ""}`);
    for (const x of issues) console.log(`    ${x.level === "block" ? "BLOCK" : "warn "} ${x.check}: ${x.detail}`);
    await ctx.close();
  }
}
await browser.close();
if (opt("--json")) fs.writeFileSync(opt("--json"), JSON.stringify(report, null, 2));
const blocking = report.reduce((n, r) => n + r.issues.filter((x) => x.level === "block").length, 0);
console.log(`\n${blocking ? `${blocking} blocking issue(s)` : "No blocking issues"} across ${report.length} state×viewport runs.`);
process.exit(blocking ? 1 : 0);
