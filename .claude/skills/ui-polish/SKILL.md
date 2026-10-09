---
name: ui-polish
description: Final pass before shipping a UI change - consistency with the design system, wording, edge cases (empty, error, offline, long text, zero rows), and a clean audit with before/after screenshots. Use when asked to polish, finish or tidy a UI, or right before deploying UI work.
---

# UI polish

The last ten percent. Small, careful, no new features.

1. **Diff review.** Read the UI diff since the last release (`git diff <base> -- <ui paths>`). For every new style,
   ask: is there a token or component for this already? Replace one-offs with the system.
2. **Words.** Every new string: sentence case, plain, says what happens; one name per action across buttons, toasts and
   headings ("Save" → "Saved …"); errors say what happened and what to do; empty states say what to do next.
3. **Edge cases.** Check each changed screen with: no data, an error from the backend, a machine offline, a 60-character
   name, a huge number, a phone. Add any missing ones to the states file so they stay covered.
4. **Motion sweep.** Run `ui-audit/scripts/motion-lint.mjs`; then by hand, for each thing that moves: should it animate at
   all (never for keyboard-triggered or constant actions)? ease-out, ≤ 300ms, exact properties, `:active` press
   feedback, hover motion only on pointer devices, reduced motion keeps fades. Review in the `emil-design-eng` table
   format (Before | After | Why).
5. **Detail sweep.** Alignment to the spacing scale, consistent radii, icons and arrows used the same way everywhere,
   no stray console output, no layout jump while loading (hold old content rather than flashing a skeleton).
6. **Prove it.** `/ui-audit` with no blocking issues, then screenshots of the changed states (desktop + phone) with
   `ui-critique/scripts/shoot.mjs`, looked at with the Read tool. Fix, re-shoot, repeat.
7. **Record** a short dated entry in the design log: what was polished and anything deliberately left.
