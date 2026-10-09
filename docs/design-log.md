# Design log

Dated notes from `/ui-critique`, `/ui-audit` and `/ui-polish`: what was found, what changed, what was decided.
Newest first. Read the last few entries before starting UI work so the same ground isn't covered twice.

## 2026-10-09 — Servers section (Dragonwilds)

New `serverCard` on the Dashboard (between Machines and Services), on helios' machine page, and as a chat tile
(`game_servers` tool). Critique pass: a single card stretched the full page width (meters over 1000px) → the grid now
fills ~400px columns. Audit and motion lint clean. Still to confirm on the real server: the join/leave log lines
(the agent uses Unreal's standard ones; override per server with "patterns" in SERVERS).

## 2026-10-09 — motion pass (Emil Kowalski's design-engineering checklist)

Added `.claude/skills/emil-design-eng` (MIT, vendored unchanged) and `ui-audit/scripts/motion-lint.mjs`.

| Before | After | Why |
| --- | --- | --- |
| Ctrl K palette `animation: fade .12s` | no animation | keyboard-opened, many times a day |
| `.card.lift:hover` lift everywhere | lift only under `(hover: hover) and (pointer: fine)` | taps on phones fired hover |
| no `:active` state on buttons, tabs, pills | `scale(0.97)` (cards `0.99`), 160ms ease-out | presses need an answer |
| toast `transition: .2s` | `opacity, transform 200ms` ease-out | name properties |
| meter fill `width .6s ease` | `width 300ms` ease-out curve | ≤ 300ms |
| number tween 650ms every 5 s | 300ms | seen constantly |
| view transitions 300ms, also on Esc / number keys | 200ms; none when keyboard-driven | keyboard actions are instant |
| logs drawer `slide .2s ease-out` | 250ms `--ease-drawer` | drawer curve |
| chat replies and tiles pop in | `@starting-style` 200ms fade + 4px rise | appearing content shouldn't jump |
| reduced motion killed everything | movement off, fades and colour kept | reduced ≠ none |

Left on purpose: the live-dot pulse (it is the "connected" signal; stops under reduced motion).

## 2026-10-09 — first audit and critique (all screens, desktop + phone)

**Audit: 26 blocking → 0.**
- Terracotta text was 4.48:1 on white (needs 4.5); added `--accent-ink` `#b04822` and `-ink` steps for ok/warn/bad text.
- `--faint` (2.5:1) was used for small text (timestamps, IPs, images, Network Watch device IPs); moved to `--muted`,
  which was also darkened `#77726a → #6b665e` because it failed on the cream page (4.34:1).
- Keyboard focus was invisible on the chat input and the device editor (CSS removed the outline). Fixed.
- Tables, log boxes and container lists scrolled but weren't reachable by keyboard; now focusable named regions.
- `aria-label` on a plain `div` (site links) → `role="group"`.
- Tap targets under 24px on phones (tile actions, "New conversation", the wordmark, "← Dashboard"): padded.
- Left as a warning: Network Watch's 14px "Hide background" checkbox (its label is clickable).

**Critique — fixed:**
- Bug: "errors in the pihole logs" read **pihole-watch** on helios — a partial name on the first machine beat the exact
  `pihole` on horae. Exact names now win across all machines (`chat.py`, `t_logs`).
- The chat input is focused whenever Chat is open, so a hard focus ring was permanent noise → a soft halo on the bar.
- Three overlapping navs (suite app switcher, Chat/Dashboard tabs, site links; "Overview" highlighted while on Chat).
  Olympus now hides the suite switcher; Network Watch and Horae keep it to get back.
- "Blocked only" tiles showed the same number twice (3,204 lookups / 3,204 blocked) → one KPI named for the filter;
  normal tiles now show the blocked share.
- Phone: the device editor pushed Save buttons off-screen; section subtitles squeezed beside headings. Fixed.

**Open — needs Todd:**
1. *Distinctiveness.* The suite matches several traits Anthropic's `frontend-design` skill calls generated defaults
   (cream + serif wordmark + terracotta; "A · B · C" meta strings; mono labels; ↗ everywhere). Options:
   (a) keep as is — it was chosen and it works; (b) keep the warmth but swap the terracotta for the hosts' own colours
   as the only accents and drop the middle-dot strings for real layout; (c) a fresh direction built from the subject
   (a home network: e.g. a cooler, map-like palette and a single typeface). Recommendation: (b), small and reversible.
2. *Raw errors in the status banner* (`[Errno 111] Connection refused`): fine for Todd, but could read "ntfy isn't
   answering (connection refused)". Low priority.
3. *Chart axis on narrow ranked charts* shows only two ticks on a phone; acceptable, revisit if it bothers anyone.
