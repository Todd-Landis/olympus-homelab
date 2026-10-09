---
name: ui-critique
description: Visual design review from real screenshots - every screen at desktop and phone size, judged against the project's design system and plain UX heuristics, with prioritised findings. Use when asked to critique, review or improve how a UI looks or reads, after building a new screen, or when something "feels off".
---

# UI critique

You can't judge what you haven't seen. Screenshot first, then look at every image.

## 1. Context
Read the project's design system (Olympus: `docs/DESIGN.md`) and the latest design-log entries. If there is none,
write down in a few lines who uses the UI, on what screens, and what it is for, before judging anything.

## 2. Shoot
Start the app (Olympus: `dev/stack.sh start`), then
`node .claude/skills/ui-critique/scripts/shoot.mjs dev/ui/states.mjs [--only a,b] [--viewport phone]`.
Screenshots land in `dev/.run/shots/<state>-<viewport>.png`. Open each one with the Read tool. Any `!` line means the
page logged errors: that is a finding.

## 3. Judge each screen, in this order
1. **Squint test:** what is the first thing you see? Is it the most important thing (in Olympus chat: the answer)?
2. **Job:** can the person do the screen's job without reading instructions? Is anything doing two jobs, or two
   things doing one job (duplicate navigation, repeated numbers)?
3. **Truth:** does every label, number and chart match the data and the question? Wrong data is the worst finding.
4. **System:** tokens, components, type and spacing from the design system; anything off-system is a finding.
5. **Text:** plain words, sentence case, buttons that say what happens, errors that say what to do.
6. **States:** empty, loading, error, offline, very long names, zero rows. Add states to the states file if missing.
7. **Phone:** nothing off-screen, thumb-sized targets, nothing important below a pinned bar.
8. **Generic tells:** compare against the traits listed in Anthropic's `frontend-design` skill (cream + serif +
   terracotta, identical rounded cards everywhere, "A · B · C" meta strings, mono labels, ALL-CAPS eyebrows, arrows on
   every link). Report them as observations: a documented choice in the design system wins.

## 4. Report
Group findings as **Fix now** (bugs, broken or misleading), **Should fix** (clarity, consistency) and **Decide**
(taste or direction - give two or three concrete options and a recommendation). Reference the screenshot for each.
Fix "Fix now" items when asked to improve, re-shoot to confirm, and log the session in the design log.
