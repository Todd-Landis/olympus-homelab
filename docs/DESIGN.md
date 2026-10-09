# Olympus design system

The source of truth for how Olympus, Network Watch and the Horae dashboard look, read and behave.
The UI skills in `.claude/skills/` check work against this file. Change the system here first, then in code.

## Product

- **Who:** Todd, alone, on his own tailnet. Technical: knows what a container, DNS lookup and IP are.
- **Where:** a desktop browser most of the time, an iPhone often. Light mode only (by choice; no dark mode).
- **What it is for:** asking questions about the home lab and getting a straight answer with the evidence beside it.
  Chat is the front door (`#/`); the Dashboard tab (`#/dashboard`) is for scanning everything at once.
- **Tone:** a quiet instrument, not a showpiece. Todd rejected a heavily themed version (temples, "Oracle" wording) as
  an art project. Subtle, modern, readable. The classical nods (the Olympus wordmark, the sun arc) stay in the background.

## Principles

1. **The answer comes first.** In chat, the model's sentence is the biggest, highest thing in a reply; tiles follow.
2. **Data is the loudest thing on screen.** Chrome is thin borders, plain labels and one accent.
3. **Plain names.** "Devices & people", "Lookups", "Blocked" — never internal names (`network_query`, `registry`).
4. **Every number can be checked.** Each chart has a table view and drills down to the rows behind it.
5. **One place per job.** One nav for tabs, one row of site links, one search (Ctrl K). Don't add parallel routes.

## Tokens (`suite/suite.css`)

| Role | Token | Value | Use |
|---|---|---|---|
| Page | `--bg` | `#f6f4ef` | page background |
| Surface | `--surface` / `--surface-2` | `#fff` / `#faf8f4` | cards / insets, table hovers |
| Lines | `--border` / `--border-strong` | `#e7e2d8` / `#d8d1c3` | hairlines; strong = hover, inputs |
| Text | `--text` / `--text-2` / `--muted` | `#1d1c1a` / `#4a4741` / `#6b665e` | body / secondary / smallest text |
| Decoration | `--faint` | `#a9a399` | **never text** (2.5:1). Rules, dashed arcs, placeholders only |
| Accent | `--accent` / `--accent-ink` | `#c4552d` / `#b04822` | fills and marks / **text and links** |
| Status | `--ok` `--warn` `--bad` (+ `-soft`, `-ink`) | | dots and fills use the base; text on any surface uses `-ink` |
| Hosts | helios ochre `#c98a12`, horae laurel `#3f8a5a`, hephaestus terracotta `#c4552d` | | the top rule of machine cards, sparklines |

**Text contrast rule:** body and small text must clear 4.5:1 on the surface it sits on. Use `--muted` as the lightest
text colour and the `-ink` variants for coloured text. `/ui-audit` enforces this.

**Type:** Inter for everything (14.5px/1.55 body; 15.5px for chat answers). Fraunces only for the "Olympus" wordmark.
JetBrains Mono only for machine-ish strings: log lines, IPs, container images, timestamps in tables. Sentence case
everywhere; no ALL-CAPS labels except the small group headers in tables.

**Shape:** radius 12px cards, 14px chat bubbles (one tight corner toward the speaker), 99px pills, 7–8px controls.
Shadows are the two in `--shadow` / `--shadow-hover`; nothing heavier.

**Spacing:** 4px base. Section gap 30px (`.sec`), card padding 14–18px, grid gap 12–14px, 16px phone gutter.

**Motion:** number tweening, view transitions between routes, one pulse on live dots. Nothing else moves on its own.
`prefers-reduced-motion` turns all of it off (`suite.css`).

## Components

- **Tabs** (`.tabs .tab`, `aria-current="page"`): Chat, Dashboard. **Site links** (`.site`): every service with a URL,
  status dot + name + ↗, open in a new tab.
- **Composer** (`.composer`): pinned to the bottom of Chat, focused on arrival (desktop). Its focus ring is a soft
  blue halo on the whole bar, because it is focused nearly all the time.
- **Turn**: question bubble (right, `--accent-soft`) → reply bubble (left, white: answer text, then the lookups it
  ran as `.step` chips) → tiles (full width).
- **Tile** (`.card.tile`): `h4` title + `small` subtitle + actions (Table, Open ↗) on the right; KPIs; chart (`.viz`);
  table (`.scroll`, a keyboard-focusable region). Drill-down tiles carry a `↳` crumb saying where they came from.
- **Machine card** (`.host`), **service tile** (`.svc`), **badge** (`.badge.ok|warn|bad|plain`), **button** (`.btn`,
  `.btn.go` primary, `.btn.danger`), **ledger table** (`.ledger`), **toast**, **drawer** (logs), **Oracle** (Ctrl K).
- **Scrolling boxes** (tables, logs) get `tabindex="0" role="region" aria-label="…"` so keyboards can reach them.

## Charts (`olympus/hub/static/viz.js`, Apache ECharts 6.1.0)

- Colours (validated for colour-blind separation against the white card surface):
  allowed `#2a78d6`, blocked `#eb6834`; people/devices take slots in this fixed order —
  `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4 #008300 #4a3aa7 #e34948` — never cycled, a 9th folds into "Other".
  Heatmaps use one blue ramp, light to dark, with a scale legend.
- Thin marks: bars ≤ 24px with a 4px rounded data end; 2px lines; 1px solid hairline grid; a white gap between stacked segments.
- A legend only for two or more series; empty series are dropped (`tidy()`); one axis, never two y-scales.
- Tooltips: value first, then a short line key and the series name; `confine: true` so they never leave the chart.
- Every chart: hover tooltip, a Table toggle with the same numbers, and click-to-drill-down where a deeper question exists.

## Writing

- Sentence case. Buttons say what happens: "Save", "New conversation", "Open ↗" (↗ only for links that leave Olympus).
- Errors say what happened and what to do: "Couldn't load devices: Network Watch isn't reachable." No apologies.
- Empty states invite the next action ("Nobody assigned yet. Type who uses a device and save.").
- Numbers: thousands separators, units with a space ("3.8 GB", "4 ms"), times in local 12-hour format.

## Accessibility floor (checked by `/ui-audit`)

WCAG 2.2 AA: text ≥ 4.5:1, visible keyboard focus on every stop, keyboard-reachable scroll regions, valid ARIA,
tap targets ≥ 24px on phones, no sideways page scroll at 390px wide, reduced motion respected, no console errors.

## Open decisions

- **The look reads as "generated".** Anthropic's `frontend-design` skill lists the most common traits of AI-generated
  pages; this suite has several: a warm cream page with a serif display word and a terracotta accent, meta strings
  joined with middle dots, monospace for small data labels, ↗ on links. They were chosen on purpose (see Tone), so they
  stay until Todd decides otherwise. Options are written up in `docs/design-log.md`.
