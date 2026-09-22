# Vendored design skills

These are **vendored, not fetched.** They are copied into every generated entry repository by
`src/pgm/engine-prompt.ts` (`copySkillsToEntry`) so the agent that writes the front end has them in
scope at the moment it needs them — and so an event-day network failure cannot change the look of
an entry, and a skill cannot change under the chassis between one hackathon and the next.

| skill | source | vendored | used by |
|---|---|---|---|
| `frontend-design` | Anthropic agent skills (`anthropics/skills`), `SKILL.md` sha256 `d91970639e9f5c37…` | 2026-09-21 | DP-UI WU-00, the design brief and the two-pass design plan (`templates/ui-craft.spec.md` §14) |
| `web-artifacts-builder` | Anthropic agent skills (`anthropics/skills`), `SKILL.md` sha256 `81c5002c6643b0de…` | 2026-09-21 | DP-UI, when an entry ships a standalone HTML surface |

Each folder carries its own `LICENSE.txt`; read it before redistributing.

## What the chassis adds

`frontend-design` supplies a point of view — it pushes the design off templated defaults and onto
choices grounded in the subject matter. It knows nothing about this pipeline's real constraint,
which is that the screen will be watched as footage. That half is `templates/ui-craft.spec.md`:
§1–§12 forbid the nine defects a shipped build actually had, §13 sizes and animates the UI for the
camera, and §14 is the brief the skill works from. Both bind DP-UI; neither replaces the other.

## Updating

Replace the folder wholesale from the upstream repository, update the date above, and re-run
`node scripts/lint-skills.ts`. Never edit a vendored `SKILL.md` in place: a local change that
upstream does not have is invisible the next time someone re-vendors.
