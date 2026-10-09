#!/usr/bin/env node
// Static motion checks over CSS (and <style> blocks in HTML), after Emil Kowalski's review checklist.
//   node motion-lint.mjs <file.css|file.html> [...]      (or: <states.mjs>, which may export `cssFiles`)
// Flags: transition on `all` / shorthand without properties · ease-in on UI · durations over 300ms (looping animations
// exempt) · :hover transforms outside @media (hover: hover) · entrances from scale(0). Warnings only: judgement applies.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

let files = process.argv.slice(2);
if (files.length === 1 && files[0].endsWith(".mjs")) {
  const mod = await import(pathToFileURL(path.resolve(files[0])));
  files = (mod.cssFiles || []).map((f) => path.resolve(path.dirname(path.resolve(files[0])), f));
}
if (!files.length) { console.error("usage: motion-lint.mjs <css/html files…> | <states.mjs exporting cssFiles>"); process.exit(2); }

const findings = [];
for (const file of files) {
  const raw = fs.readFileSync(file, "utf8");
  // CSS text plus the line each chunk starts on, so findings point at the right line
  const chunks = file.endsWith(".html") ? [...raw.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => ({ css: m[1], line: raw.slice(0, m.index).split("\n").length }))
    : [{ css: raw, line: 1 }];
  for (const { css, line: base } of chunks) {
    const stack = []; // enclosing at-rule / selector preludes
    let buf = "", line = base;
    const report = (rule, msg, at) => findings.push({ file: path.relative(process.cwd(), file), line: at, rule, msg });
    for (let i = 0; i < css.length; i++) {
      const ch = css[i];
      if (ch === "\n") line++;
      if (css.startsWith("/*", i)) { const end = css.indexOf("*/", i + 2); line += css.slice(i, end).split("\n").length - 1; i = end + 1; continue; }
      if (ch === "{") { stack.push(buf.trim()); buf = ""; continue; }
      if (ch === "}" || ch === ";") {
        const decl = buf.trim(); buf = "";
        if (decl.includes(":")) check(decl, stack, line, report);
        if (ch === "}") stack.pop();
        continue;
      }
      buf += ch;
    }
  }
}

function check(decl, stack, line, report) {
  const [prop, ...rest] = decl.split(":"), value = rest.join(":").trim(), p = prop.trim().toLowerCase();
  const selector = stack[stack.length - 1] || "", inHoverMedia = stack.some((s) => /@media[^{]*hover:\s*hover/.test(s));
  if (p === "transition") {
    if (/(^|,)\s*all\b/.test(value)) report("transition-all", `"${decl}": name the properties you animate`, line);
    else if (/^[\d.]+m?s\b/.test(value)) report("transition-all", `"${decl}": shorthand with no property animates everything`, line);
  }
  if ((p === "transition" || p === "animation" || p.endsWith("-timing-function")) && /\bease-in\b(?!-out)/.test(value))
    report("ease-in", `"${decl}": ease-in starts slow and feels sluggish; use ease-out`, line);
  if ((p === "transition" || p === "animation" || p.endsWith("-duration")) && !/infinite/.test(value)) {
    for (const m of value.matchAll(/(?<![\w-])([\d.]+)(ms|s)\b/g)) {
      const ms = m[2] === "s" ? parseFloat(m[1]) * 1000 : parseFloat(m[1]);
      if (ms > 300) { report("slow", `"${decl}": ${ms}ms; UI motion stays under 300ms`, line); break; }
    }
  }
  if (p === "transform" && /:hover/.test(selector) && !inHoverMedia && !/translate(X|Y)?\(0|none/.test(value))
    report("hover-touch", `"${selector}" moves on hover outside @media (hover: hover) and (pointer: fine)`, line);
  if (p === "transform" && /scale\(\s*0\s*\)/.test(value)) report("scale-0", `"${decl}": start from scale(0.95) with opacity 0`, line);
}

for (const f of findings) console.log(`warn  ${f.rule}: ${f.file}:${f.line}  ${f.msg}`);
console.log(findings.length ? `\n${findings.length} motion warning(s).` : "No motion warnings.");
