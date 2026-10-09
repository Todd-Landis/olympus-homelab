---
name: ui-audit
description: Deterministic accessibility and layout checks for a web UI - axe-core WCAG 2.2 AA, sideways overflow on phones, tap targets, visible keyboard focus, console errors - run on every screen at desktop and phone size, then fix what fails. Use when asked to audit, check accessibility, or before calling any UI change done.
---

# UI audit

Mechanical checks only: same input, same report. Taste belongs to `/ui-critique`.

## Run
1. Find the project's UI states file (default `dev/ui/states.mjs`; it exports `viewports` and `states` - see
   "New project" below) and start the app the way the project says (README / DESIGN.md; in Olympus `dev/stack.sh start`).
2. Install the tools once beside the states file: `npm install --prefix dev/ui` (Playwright + axe-core). If Chromium is
   missing: `npx --prefix dev/ui playwright install chromium` (or set `CHROME_PATH`).
3. Run: `node .claude/skills/ui-audit/scripts/audit.mjs dev/ui/states.mjs [--only a,b] [--json out.json]`
   (from a global install, use `~/.claude/skills/ui-audit/scripts/audit.mjs`).

4. Static motion check (Emil Kowalski's checklist: `transition: all`, ease-in, > 300ms, hover motion on touch screens,
   `scale(0)` entrances): `node .claude/skills/ui-audit/scripts/motion-lint.mjs dev/ui/states.mjs` (the states file
   exports `cssFiles`), or pass CSS/HTML files directly. Warnings, not blockers: fix or justify each in the log.

## Fix
- **BLOCK** items are failures: fix them at the source (tokens over one-off overrides), then re-run until clean.
  Typical causes: text colour too light for its surface (darken the token, don't shrink the check); `outline: none`
  with no replacement; scroll boxes without `tabindex="0" role="region" aria-label`; ARIA on elements that can't carry it.
- **warn** items: fix when cheap; if you leave one, say why in the design log.
- Never weaken a check or skip a state to get green. If a check is wrong, fix the check and say so.

## Report
A short table: check → what failed → what you changed. Note anything left, and add a dated entry to the project's
design log (Olympus: `docs/design-log.md`).

## New project
Copy `dev/ui/package.json` and write a `states.mjs`: `export const viewports = [{name,width,height,isMobile?,hasTouch?}]`
and `export const states = [{ name, url, run?: async (page) => {} }]` - one state per screen and per meaningful
condition (empty, loading, error, long content), driven into shape by `run`.
