#!/usr/bin/env node
// Screenshot every UI state at every viewport.
//   node shoot.mjs <states.mjs> [--out <dir>] [--only name,name] [--viewport desktop|phone]
// <states.mjs> exports `viewports` and `states` ({ name, url, run?(page) }); playwright is resolved from beside it.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
if (!args[0] || args[0].startsWith("--")) { console.error("usage: shoot.mjs <states.mjs> [--out dir] [--only a,b] [--viewport name]"); process.exit(2); }
const statesPath = path.resolve(args[0]);
const out = path.resolve(opt("--out", path.join(path.dirname(statesPath), "..", ".run", "shots")));
const only = opt("--only", "")?.split(",").filter(Boolean);
const vpOnly = opt("--viewport", "");
const { chromium } = createRequire(statesPath)("playwright");
const { states, viewports } = await import(pathToFileURL(statesPath));
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
let failed = 0;
for (const vp of viewports.filter((v) => !vpOnly || v.name === vpOnly)) {
  for (const st of states.filter((s) => !only?.length || only.includes(s.name))) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: !!vp.isMobile, hasTouch: !!vp.hasTouch });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    const file = path.join(out, `${st.name}-${vp.name}.png`);
    try {
      await page.goto(st.url, { waitUntil: "load" });
      await page.waitForTimeout(1000);
      if (st.run) await st.run(page);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`${errors.length ? "!" : "✓"} ${path.relative(process.cwd(), file)}${errors.length ? "  console: " + errors.slice(0, 3).join(" | ") : ""}`);
    } catch (e) {
      failed++;
      console.log(`✗ ${st.name}-${vp.name}: ${e.message.split("\n")[0]}`);
    }
    await ctx.close();
  }
}
await browser.close();
process.exit(failed ? 1 : 0);
