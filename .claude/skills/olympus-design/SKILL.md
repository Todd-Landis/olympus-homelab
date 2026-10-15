---
name: olympus-design
description: The Olympus home-lab design rulebook and UI workflow, for every site we host. Use before changing anything people see in this repo - olympus/hub/static (Olympus chat and dashboard, charts in viz.js), pihole-watch/app/static (Network Watch), suite/ (shared CSS/JS), horae/homepage (Horae theme), horae/homeassistant (Home Assistant theme), the Pi-hole theme setting, or chat tile/answer wording in olympus/hub/chat.py.
---

# Olympus design

1. **Read `docs/DESIGN.md`** (the rulebook: theme nods and bans, tokens, motion, phones, components, charts, writing,
   worst-case data, accessibility, how each site applies it) and the newest entries of `docs/design-log.md` (what was
   already tried and what is still open). Follow them; if a change needs the rules themselves to change, edit
   DESIGN.md in the same commit and say why.
2. **Plan in the system's terms** before coding: which tokens, which existing component, which states it adds.
   Reuse `.card`, `.tile`, `.btn`, `.badge`, `.bar`, `.ledger`, `Suite.mark`, `Suite.toast`, `Viz.*`; don't invent a
   parallel version.
3. **Build.** Shared look goes in `suite/suite.css` / `suite.js` (it ships to Olympus, Network Watch and Horae);
   page-specific CSS stays in the page; Home Assistant's look is `horae/homeassistant/themes/olympus.yaml`.
   Text colours: `--text`, `--text-2`, `--muted`, or an `-ink` token. Never `--faint` for text. Every `:hover` inside
   `@media (hover: hover) and (pointer: fine)`.
4. **Reach for Emil Kowalski's skills** (vendored in `.claude/skills/`) by job:
   - anything that moves, presses, opens or appears → `animate` (run its gate: often the answer is "don't");
     looking for where motion would help → `find-animation-opportunities`; reviewing motion → `review-animations`;
     dropped frames → `animation-performance`; the philosophy and review table → `emil-design-eng`.
   - gestures, drawers, materials, type tracking, the design principles → `apple-design`.
   - anything that will be used on the iPhone → `mobile-native`.
   - a new component or screen → `break-ui` (worst-case data: long names, zero/one/1,000 rows, offline).
   DESIGN.md wins where it is stricter (light only, no motion library, one accent, the theme bans).
5. **Run it locally:** `dev/stack.sh start` (Olympus on :9290, Network Watch on :9295, fake machines and a week of fake
   browsing). The chat model there is scripted by keywords (`dev/fakes.py`); add a keyword if you need a new tile.
6. **New screen, tile or overlay?** Add a state to `dev/ui/states.mjs` so the checks cover it.
7. **Check before calling it done:** `/ui-audit` must report no blocking issues; `motion-lint` no warnings (or each
   justified in the log); for anything visible and new, run `/ui-critique` on the affected states and look at the
   screenshots yourself, desktop and phone.
8. **Log it:** add a short dated entry to `docs/design-log.md` (found, changed, still open).
9. Ship with `./deploy.sh <app>`; only Todd can run it (the servers are on his tailnet). Home Assistant and Pi-hole
   changes also need a `sudo` step on horae, which the deploy target prints.

Hard rules from Todd: light mode only; plain labels; no themed/"art project" treatments (the four nods in DESIGN.md
section 3 are the whole allowance); chat stays the front door.
