# Design log

Dated notes from `/ui-critique`, `/ui-audit` and `/ui-polish`: what was found, what changed, what was decided.
Newest first. Read the last few entries before starting UI work so the same ground isn't covered twice.

## 2026-10-15 — design refresh and the rulebook (all sites, Home Assistant included)

Asked for: a better design built with Emil Kowalski's skills (github.com/emilkowalski/skills, 15 skills read; the
eight that apply to plain web pages are now vendored in `.claude/skills/`), subtle nods to the theme, the same look
on Home Assistant, and one rulebook for every internal site. `docs/DESIGN.md` is now that rulebook.

**Resolves the open "reads as generated" decision** (2026-10-09, option c leaning on b): the cream page, Fraunces
wordmark and terracotta accent are gone; mono is limited to machine strings; ALL-CAPS table group rows are sentence case.

| Before | After | Why |
| --- | --- | --- |
| Cream `#f6f4ef` page, terracotta accent | Marble `#f5f5f2`, one Aegean blue accent (`#2a78d6`, text `#1b5fad`) | Off the generated-default palette; blue is the familiar "interactive" colour and equals chart slot 1 |
| Solid 1px borders on cards, inputs, buttons | Translucent 1px ring + soft shadow (`--shadow`) | Emil: shadows over solid borders; one value reads right on any surface |
| Fraunces "Olympus" wordmark | Temple-front mark + "OLYMPUS" in tracked Inter caps | The classical nod stays, the generic serif goes |
| Per-host colours: ochre/laurel/terracotta top borders, meters, sparklines | A mark per machine (sun, hourglass, anvil); neutral ink meters, warn ≥ 75%, bad ≥ 90%; blue sparklines | helios' ochre meters read as warnings and horae's laurel as "OK": colour now means status only |
| Static gold glow in the corner | Daylight that follows the real sun (moonlight at night), set once a minute | A quiet nod tied to something true; no motion |
| Numbers in JetBrains Mono in tables and leaders | Inter with tabular figures; mono only for IPs, images, ports, logs | Mono labels were a generic tell and harder to read |
| Hover rules ungated (`.btn:hover`, `.site:hover`, …) | All `:hover` inside `(hover: hover) and (pointer: fine)` | mobile-native: taps left hover stuck on iPhone |
| Composer 15.5px, filters/editor 13.5px | 16px on touch screens | mobile-native: iPhone zoomed into the field and stayed zoomed |
| Composer on a `box-shadow: 0 14px 0 var(--bg)` hack | A sticky dock with a scroll-edge fade; safe-area padding | apple-design: fade content under floating chrome instead of cutting it |
| Drawer: keyframes in, `display: none` out | Transitions: in 250ms `--ease-drawer`, out 200ms the same way; Esc closes instantly | Interruptible, symmetric path, faster exit; keyboard actions never animate |
| Card hover animated `box-shadow` | Hover shadow on a pseudo-element, fading `opacity` | animation-performance: box-shadow repaints every frame |
| Field focus rings faded in over 150ms | Instant | Keyboard-driven; the audit also couldn't see a ring at focus time |
| Toast hid after 2.8s even in a background tab | Its timer waits until the tab is visible | Sonner principle: handle edge cases invisibly |
| `:focus-visible` set `border-radius: 6px` on whatever had focus | Outline only | Cards changed shape when focused |
| Network Watch bars: pale blue + terracotta, blocked at the bottom, 45px wide | Chart palette (blue/orange), blocked on top, ≤ 24px, 1px white gap | Same rules as Olympus' charts |
| Network Watch's blocked bars carried the close button's `.x` styles | `button.x` | Bug: the shared class padded every blocked bar |
| Long times pushed the drawer's numbers off a phone screen | Times wrap on phones | break-ui: never truncate numbers |
| Palette list: divs, not reachable by keyboard as a region | combobox + listbox + option groups | ARIA and axe |

Also: Home Assistant **Olympus** theme (`horae/homeassistant/themes/olympus.yaml`, ~125 variables: surfaces, ink,
accent, status, cards with the ring shadow, ink header/sidebar, chart palette, sun-gold "on" lights) with an installer
that backs up and checks `configuration.yaml` (`horae/scripts/ha-theme.sh`; its YAML edit tested on six sample configs);
Pi-hole set to `default-light`; Homepage overrides moved to the new tokens.

Checks: `/ui-audit` 0 blocking across 17 states × 2 viewports (new states: logs drawer, palette, Network Watch sites
and site drawer). `motion-lint` 0 warnings. New checks added: `motion-lint` warns on layout-property transitions
(animation-performance); `/ui-audit` warns on touch fields under 16px and blocks a zoom-locked viewport
(mobile-native), and lets a checkbox count its label as the tap target (WCAG 2.5.8 equivalent control).

**Open:**
1. Horae (Homepage) and Home Assistant can't run locally: look at both after deploying. HA variable names change
   between releases; anything that stays default-coloured is a variable to add to the theme.
2. Real iPhone pass: the dock over the keyboard, safe areas, press feedback (emulation can't show these).
3. Raw errors in the status banner (`[Errno 111] Connection refused`) are still raw (low priority, from 2026-10-09).

## 2026-10-09 — Servers section (Dragonwilds)

New `serverCard` on the Dashboard (between Machines and Services), on helios' machine page, and as a chat tile
(`game_servers` tool). Critique pass: a single card stretched the full page width (meters over 1000px) → the grid now
fills ~400px columns. Audit and motion lint clean. Player lines confirmed against the real log (login pattern fixed for
names with spaces and the Dragonwilds login prefix).

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
