# Olympus design rulebook

How every site we host looks, reads and moves: Olympus, Network Watch, the Horae dashboard, Home Assistant, Pi-hole, and
anything added later. The UI skills in `.claude/skills/` check work against this file. Change the rules here first, then
in code, and log why in `docs/design-log.md`.

Sources: Emil Kowalski's skills (vendored unchanged in `.claude/skills/`: `emil-design-eng`, `apple-design`, `animate`,
`review-animations`, `find-animation-opportunities`, `animation-performance`, `mobile-native`, `break-ui`; MIT) and
Todd's decisions in the design log. Where a rule here is stricter than a skill, this file wins.

## 1. Product

- **Who:** Todd, alone, on his own tailnet. Technical: knows what a container, DNS lookup and IP are.
- **Where:** a desktop browser most of the time (Windows laptop), an iPhone often. **Light mode only** (by choice).
- **What it is for:** asking about the home lab and getting a straight answer with the evidence beside it.
  Olympus chat is the front door (`#/`); the Dashboard tab (`#/dashboard`) is for scanning everything at once.
- **Tone:** a quiet instrument, not a showpiece. Todd rejected a heavily themed version (temples, stamps, "Oracle"
  wording) as an art project. Subtle, modern, readable. The classical nods live in the margins (section 3).

## 2. Principles

1. **The answer comes first.** In chat the model's sentence is the biggest, highest thing in a reply; tiles follow.
2. **Data is the loudest thing on screen.** Chrome is light rings, plain labels and one accent. Colour means something
   (status, a series, the thing you clicked); it is never decoration.
3. **Plain names.** "Devices & people", "Lookups", "Blocked": never internal names (`network_query`, `registry`).
4. **Every number can be checked.** Each chart has a table view and drills down to the rows behind it.
5. **One place per job.** One nav for tabs, one row of site links, one search (Ctrl K). No parallel routes.
6. **Restraint in motion.** The more often something happens, the less it moves. Keyboard actions never animate.
7. **Response is instant.** Feedback starts on the press, not the release (Apple's first principle of fluid interfaces).
8. **Built for the worst data, not the demo.** Long names, zero rows, one row, 1,000 rows, an offline machine.

## 3. The theme: subtle nods, and what is banned

The machines are named for Greek gods; the suite says so quietly, in four places only.

| Nod | Where | Rule |
| --- | --- | --- |
| **Inscribed wordmark** | masthead | A 19px temple-front mark + "OLYMPUS" in Inter 600, uppercase, tracked `.17em`, like a lintel inscription. The only all-caps text in the suite. |
| **Machine marks** | machine cards, machine page title, search results; the temple front also marks the empty chat | 16px monoline glyphs (`Suite.mark(name)`): helios the sun, horae the hourglass (the hours), hephaestus the anvil (the forge), Olympus the temple front. Ink colour, never tinted. Unknown machines get a plain monitor. |
| **Sky arc** | masthead (desktop) | The real sun (gold) or moon along today's sunrise-to-sunset arc for Grove City, OH. Redrawn once a minute. |
| **Daylight** | page background | A faint radial glow from wherever the sun is now: left in the morning, right by evening, strongest at noon, cool moonlight after sunset. Set once a minute, never animated, at most 9% opacity. |

Home Assistant adds one more: a light that is **on** glows sun gold.

**Banned:** temples, columns or meanders as decoration; marble or stone textures; gold gradients; Greek or display
serif typefaces; "Oracle", "Pantheon", "decree" or other themed wording in the UI (internal code names are fine);
coloured top borders on cards; more nods than the four above. New ideas go to Todd first.

## 4. Tokens (`suite/suite.css`)

### Colour

| Role | Token | Value | Use |
| --- | --- | --- | --- |
| Page | `--bg` | `#f5f5f2` | marble: the page, the HA background, the dock fade |
| Surfaces | `--surface` / `--surface-2` / `--surface-3` | `#fff` / `#f9f9f7` / `#efefeb` | cards / insets, row hover / chips, meter tracks, selected rows |
| Lines | `--line` / `--line-strong` | `rgba(23,24,28,.08)` / `.15` | hairlines and rings / inputs and buttons. Translucent so they read on any surface |
| Text | `--text` / `--text-2` / `--muted` | `#17181b` / `#44464c` / `#62656c` | body / secondary / smallest text (≥ 5:1 everywhere) |
| Decoration | `--faint` | `#a6a8ad` | **never text** (2.2:1). Placeholders' decoration, the moon, dashed arcs |
| Accent | `--accent` / `--accent-ink` / `--accent-soft` | `#2a78d6` / `#1b5fad` / `#eaf1fb` | Aegean blue. Fills and focus / **text and links** / your question bubble, selection |
| Sun | `--sun` | `#d39a1c` | the sky arc, daylight, HA "on" lights. Nothing else |
| Status | `--ok` `--warn` `--bad` (+ `-soft`, `-ink`) | green / amber / red | dots and fills use the base; text on any surface uses `-ink` |
| Meter | `--meter` | `#4b5059` | a meter at a normal level; it turns warn at 75%, bad at 90% |

Measured contrast (WCAG): every text token clears **5:1** on every surface, including its own `-soft` tint.
White on `--accent` is only 4.4:1, so the accent fill never carries text; the primary button is ink (`--text`).

**Colour rules.**
- One accent. Host identity is carried by the mark, not by colour: per-host colours collided with status (helios'
  ochre meters read as warnings), so they are gone.
- Status colours mean status and nothing else. A green that isn't "OK", an amber that isn't "warning" is a bug.
- Light only: `color-scheme: light`, `theme-color` = `--bg`. `prefers-contrast: more` strengthens lines and `--muted`.

### Type

Inter (variable, optical sizing on) for everything; `font-feature-settings: "cv11", "ss01"`. JetBrains Mono **only for
machine strings**: IPs, MACs, container images, ports, log lines, `kbd`. Numbers people compare use Inter with
`tabular-nums` (`.num`), never mono. Tracking is size-specific (Apple): tight on big text, zero on body.

| Style | Size / line | Weight | Tracking | Use |
| --- | --- | --- | --- | --- |
| Display | 28 / 1.15 (24 on phones) | 600 | -.022em | page titles, the chat empty state |
| KPI | 24–28 / 1.1 | 600 | -.022em | big numbers, tabular |
| Title | 16 / 1.3 | 600 | -.012em | card titles (machines, servers) |
| Heading | 15 / 1.35 | 600 | -.006em | section headings |
| Answer | 16 / 1.6 | 400 | 0 | chat answers, the composer (16px also stops iPhone zoom) |
| Body | 14.5 / 1.55 | 400 | 0 | everything else |
| Small | 13 / 1.45 | 400–500 | 0 | meta lines, buttons, table cells (13.5) |
| Caption | 12–12.5 | 500 | 0 | labels under numbers, chips, table headers |

Sentence case everywhere. No ALL-CAPS labels except the wordmark.

### Shape, space, elevation

- **Radius:** cards 12px, overlays and chat bubbles 16px (one 6px corner toward the speaker), controls 8px, pills 99px.
  Nested corners are concentric: inner radius = outer radius − padding (the 10px segmented track holds 7px segments).
- **Space:** 4px base. Section gap 32px, card padding 14–18px, grid gap 12–14px. Page gutter 24px, **16px on phones**,
  and never less than the safe-area inset.
- **Elevation is light, not lines** (Emil): cards have no `border`. They get `--shadow`, a 1px translucent ring plus a
  soft drop. Hover gets `--shadow-hover` (faded in on a pseudo-element; animating `box-shadow` repaints).
  Overlays (palette, drawer, toast) get `--shadow-overlay`. Hairlines *inside* a card (`--line`) are fine.
- Widths: content max 1200px; a single game-server card caps at ~400px so it doesn't stretch.

## 5. Motion

From Emil Kowalski (`emil-design-eng`, `animate`, `review-animations`). Run the gate in order before writing any:

1. **Should it move at all?** By frequency: 100+/day or keyboard-triggered (Ctrl K, Esc, number keys, tab switches by
   key) → **never**. Tens/day (hover, tab clicks) → near-imperceptible or nothing. Occasional (drawer, toast, a new chat
   reply) → standard. Rare (first run) → the only delight budget.
2. **Name its purpose:** feedback, spatial consistency, state indication, preventing a jarring change. "Looks cool" is
   not one. Data people are reading never moves for style.
3. **Cheapest tool:** CSS transition → `@starting-style` → CSS animation → WAAPI. No motion library in this suite.
4. **Properties:** `transform` and `opacity` (and `clip-path`). Never `transition: all`; never layout properties
   (`width`, `height`, `top`, `margin`, `padding`): `motion-lint` warns on them.

| Token | Value | For |
| --- | --- | --- |
| `--ease-out` | `cubic-bezier(.23, 1, .32, 1)` | anything entering or answering a press |
| `--ease-in-out` | `cubic-bezier(.77, 0, .175, 1)` | something already on screen moving |
| `--ease-drawer` | `cubic-bezier(.32, .72, 0, 1)` | the drawer |
| `ease` | built in | hover colour changes only. **Never `ease-in`.** |

| Element | Duration | Notes |
| --- | --- | --- |
| Press (`:active`) | 160ms | `scale(.97)` on buttons, tabs, pills; `.99` on big cards |
| Hover colour / ring | 150ms | only inside `@media (hover: hover) and (pointer: fine)` |
| Entrances (chat reply, tiles) | 200ms | `@starting-style`: opacity 0 + 4px rise; never from `scale(0)` |
| Drawer | 250ms in, 200ms out | enters from the right, leaves to the right (exit faster); **Esc closes instantly** (`Suite.instant`) |
| Toast | 200ms | rises from the bottom edge, leaves the same way; its timer waits while the tab is hidden |
| Number tween | 300ms | `Suite.tween`, the state change of a live value |
| Charts | 250ms first draw, 200ms updates | |
| View transitions | 200ms | none when the change came from the keyboard |
| Focus rings | 0ms | a ring appears the instant focus lands |
| Command palette | 0ms | opened from the keyboard many times a day |

- **Reduced motion** = no movement, fades and colour changes stay; the live dot stops pulsing; the drawer cross-fades.
- **Interruptible:** use transitions, not keyframes, for anything that can fire twice in a second.
- **Idle loops:** one, the "Live" dot (2.4s). Nothing else loops.
- Feel-check new motion at 2–5× duration or in DevTools' Animations panel, and again the next day.

## 6. Phones (from `mobile-native`)

The iPhone is a first-class screen. Baseline, already in `suite.css`:
- `viewport-fit=cover` + `env(safe-area-inset-*)` on the page gutters, the chat dock, drawers and toasts. **Never**
  `user-scalable=no` or `maximum-scale=1` (`/ui-audit` blocks it).
- Fields are 16px on touch screens (smaller fields make iPhone zoom in and stay zoomed; `/ui-audit` warns).
- `-webkit-tap-highlight-color: transparent`, with an `:active` state on everything tappable instead.
- Every `:hover` rule lives inside `@media (hover: hover) and (pointer: fine)`; a tap would leave it stuck.
- `touch-action: manipulation` on controls (no double-tap delay); `user-select: none` on controls, never on content.
- `100dvh` for app-height layouts; `overscroll-behavior: contain` on drawers, the palette and scroll boxes.
- Set the keyboard: `enterkeyhint="send"` on the composer, `type`/`inputmode` on every field.
- Keyboard hints (`Ctrl K`, tab numbers) hide on touch screens.
- Test on the real iPhone before calling a touch interaction done; emulation misses all of the above.

## 7. Components

Reuse these; don't fork a parallel version.

- **Masthead** (`Suite.mount`): wordmark, app switcher (`.suite-nav`, hidden in Olympus, whose site links cover it),
  live status, sky arc and clock (desktop), search button. A hairline `.rule` under it.
- **Tabs:** segmented control (`.tabs .tab`, Olympus) for two or three views; underline tabs (Network Watch) for more.
  The active tab is ink, never accent. `aria-current="page"`.
- **Site links** (`.site`): every service with a URL: status dot, name, ↗, new tab. ↗ only on links that leave the app.
- **Card** (`.card`), **panel** (`.panel`), **lift** (`.card.lift`, clickable: hover shadow, press `.99`).
- **Machine card** (`.host`): mark + name + role, status pill, CPU sparkline, meters, a foot line of facts. Offline:
  flat (`--surface-2`, ring only) with a sentence saying why and what to expect.
- **Server card** (`.server`), **service tile** (`.svc`), **stat** (`.stat` / `.plaque`), **KPIs** (`.kpis`).
- **Meter** (`.bar > i`): neutral ink, `.w` ≥ 75%, `.b` ≥ 90%. The number beside it is the truth; the bar is the glance.
- **Badge** (`.badge.ok|warn|bad|plain`), **dot** (`.dot.ok|warn|bad|off`, `.live`).
- **Buttons** (`.btn`): quiet default; `.btn.go` primary is ink with white text (one per view); `.btn.danger` is red
  text that fills red only on hover. Destructive actions ask first.
- **Fields:** ring, not border; focus = accent ring + 4px halo, instantly. Selects get the suite chevron.
- **Ledger table** (`.ledger`): header row in caption style; group rows in 600 sentence case; numbers right-aligned
  and tabular. Scrolling boxes get `tabindex="0" role="region" aria-label="…"`.
- **Chat:** question bubble (right, `--accent-soft`) → reply card (left, answer 16px, then the lookups it ran as
  `.step` chips) → tiles (full width). The composer sits in a **dock** pinned to the bottom; the thread fades out
  under it (a scroll-edge fade, not a hard line). The composer's focus ring is a soft halo on the whole bar.
- **Tile** (`.card.tile`): `h4` title + `small` subtitle + actions (Table, Open ↗) right; KPIs; chart (`.viz`);
  table. Drill-down tiles carry a `↳` crumb saying where they came from.
- **Drawer** (`.drawer > .sheet`): right side, scrim, Esc and scrim-click close it, body is a named scroll region.
- **Command palette** (Ctrl K, `/`): combobox + listbox with groups; marks or a letter as icons; no animation.
- **Toast** (`Suite.toast`): one line, ink, bottom centre, ~3s.
- **Empty / error states:** a sentence in `.empty`: what happened, what to do next.

## 8. Charts (`olympus/hub/static/viz.js`, Apache ECharts 6.1.0; Network Watch's bars follow the same rules)

- Series colours in a fixed order, never cycled; a 9th folds into "Other":
  `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4 #008300 #4a3aa7 #e34948`. Allowed = slot 1, blocked = slot 2 (stacked on
  top). One series = slot 1 (CPU, memory and GPU charts are all blue); a second colour only when two series share a
  chart (network in solid blue, out dashed orange). Heatmaps use one blue ramp with a scale legend.
- Thin marks: bars ≤ 24px with a rounded data end; 2px lines; 1px translucent grid; a 1px white gap between stacked
  segments.
- A legend only for two or more series; empty series are dropped (`tidy()`); one y-axis, never two.
- Tooltips: value first, then a short key and the series name; `confine: true`.
- Every chart: hover tooltip, a Table toggle with the same numbers, click-to-drill-down where a deeper question exists.

## 9. Writing

- Sentence case. Buttons say what happens: "Save", "New conversation", "Open ↗". One name per action across button,
  toast and heading ("Save" → "Saved Sam's iPad").
- Errors say what happened and what to do: "Couldn't load devices: Network Watch isn't reachable." No apologies.
- Empty states invite the next action ("Nobody assigned yet. Type who uses a device and save.").
- Numbers: thousands separators, units after a space ("3.8 GB", "4 ms"), local 12-hour times, plurals that agree
  ("1 player", "2 players").
- Meta lines: a middle dot may join two or three short facts of different kinds ("helios · Chat"); anything longer
  is laid out as separate items with a gap, not a dotted string.

## 10. Data at its worst (from `break-ui`)

Design against the realistic worst case, then check it: a 60-character device name, an unbreakable hostname, zero
rows, one row, 1,000 rows, a machine offline, a number in the millions.
- **Wrap** names people need in full (devices, sites in a drawer: `overflow-wrap: anywhere`). **Truncate** secondary
  meta at the end, with the full value in a `title`. **Never truncate** numbers, dates or anything compared: on a
  phone, let the text beside them wrap instead.
- Flex and grid children that hold text get `min-width: 0`; icons, dots, badges and actions get `flex: none`.
- `tabular-nums` on every number that updates or lines up in a column.
- Use `toLocaleString` / `Intl` for numbers and times; never render `NaN`, `undefined` or a raw float.

## 11. Accessibility floor (checked by `/ui-audit`)

WCAG 2.2 AA: text ≥ 4.5:1 (the tokens give ≥ 5:1), visible keyboard focus on every stop with no fade-in,
keyboard-reachable scroll regions, valid ARIA (the palette is a combobox + listbox), tap targets ≥ 24px on phones
(a checkbox counts its label), no sideways page scroll at 390px, zoom never locked, reduced motion respected, no console
errors.

## 12. Each site

| Site | Tier | How the rules apply |
| --- | --- | --- |
| **Olympus** (`olympus/hub/static`) | built here | Full system. Chat is the front door; Dashboard tab; host marks; the dock. |
| **Network Watch** (`pihole-watch/app/static`) | built here | Full system. Underline tabs; activity bars in the chart palette; site drawer. |
| **Horae** (Homepage, `horae/homepage`) | themed | `deploy.sh horae-theme` bundles `suite.css` + `overrides.css` into Homepage's `custom.css`, and `suite.js` + `mount.js` into `custom.js` (masthead, search). Only restyle Homepage's own classes in `overrides.css`. |
| **Home Assistant** (`horae/homeassistant`) | themed | The **Olympus** theme (`themes/olympus.yaml`): marble background, white cards with the ring shadow, ink header and sidebar, Aegean toggles, status colours, chart palette, sun-gold "on" lights, Inter via `www/olympus/fonts.js`. Light only (no `modes:`). Install: `./deploy.sh horae-ha`, then `sudo bash ~/olympus-ha/ha-theme.sh` on horae. Dashboards: tile cards, no custom CSS cards. |
| **Pi-hole** (admin) | built-in theme | `default-light` via `FTLCONF_webserver_interface_theme` in `horae/stack/docker-compose.yml`. Don't fork its UI. |
| **Open WebUI, ComfyUI, others** | left alone | Light mode in their own settings where offered. Linked from Olympus, not restyled. |

**A new site** we build: copy the suite in (`deploy.sh` pattern), call `Suite.mount({ app })`, add it to `APPS` in
`suite.js` and to Olympus' services, build from the components above, add its screens to `dev/ui/states.mjs`, and pass
the checks below. A new third-party app: use its light theme and its theming hooks; never ship patched copies of its UI.

## 13. Workflow and checks

1. Read this file and the newest `docs/design-log.md` entries (`olympus-design` skill).
2. Plan in the system's terms: which tokens, which component, which states.
3. Build. Motion → `animate` (and `find-animation-opportunities` before adding any); gestures, materials,
   typography → `apple-design`; phones → `mobile-native`; jank → `animation-performance`.
4. Run it: `dev/stack.sh start` (Olympus :9290, Network Watch :9295, fake data).
5. Check: `/ui-audit` (no blocking issues), `motion-lint` (no warnings, or each justified in the log),
   `/ui-critique` screenshots at desktop and phone, `break-ui` for new components, `review-animations` for new motion.
6. `/ui-polish`, then a dated entry in `docs/design-log.md`. Ship with `./deploy.sh <app>` (only Todd can).
