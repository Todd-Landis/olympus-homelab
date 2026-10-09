---
name: olympus-design
description: The Olympus home-lab design system and UI workflow. Use before changing anything people see in this repo - olympus/hub/static (Olympus chat and dashboard, charts in viz.js), pihole-watch/app/static (Network Watch), suite/ (shared CSS/JS), horae/homepage (Horae theme), or chat tile/answer wording in olympus/hub/chat.py.
---

# Olympus design

1. **Read `docs/DESIGN.md`** (tokens, components, charts, writing, accessibility floor) and the newest entries of
   `docs/design-log.md` (what was already tried and what is still open). Follow them; if a change needs the system
   itself to change, edit DESIGN.md in the same commit and say why.
2. **Plan in the system's terms** before coding: which tokens, which existing component, which state it adds.
   Reuse `.card`, `.tile`, `.btn`, `.badge`, `.ledger`, `Viz.*`; don't invent a parallel version.
3. **Build.** Shared look goes in `suite/suite.css` / `suite.js` (it ships to all three apps); page-specific CSS stays in
   the page. Text colours: `--text`, `--text-2`, `--muted`, or an `-ink` token. Never `--faint` for text.
4. **Run it locally:** `dev/stack.sh start` (Olympus on :9290, Network Watch on :9295, fake machines and a week of fake
   browsing). The chat model there is scripted by keywords (`dev/fakes.py`); add a keyword if you need a new tile.
   Anything that moves, presses, opens or appears: follow the Motion rules in DESIGN.md, and for anything new or
   unusual (drawers, gestures, drag, toasts) consult `.claude/skills/emil-design-eng`.
5. **New screen or tile?** Add a state to `dev/ui/states.mjs` so the checks cover it.
6. **Check before calling it done:** `/ui-audit` must report no blocking issues; for anything visible and new, run
   `/ui-critique` on the affected states and look at the screenshots yourself, desktop and phone.
7. **Log it:** add a short dated entry to `docs/design-log.md` (found, changed, still open).
8. Ship with `./deploy.sh <app>`; only Todd can run it (the servers are on his tailnet).

Hard rules from Todd: light mode only; plain labels; no themed/"art project" treatments; chat stays the front door.
