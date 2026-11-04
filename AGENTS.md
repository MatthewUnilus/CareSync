# AGENTS

## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root plus `docs/adr/`. See `docs/agents/domain.md`.

### BoardUI

The BoardUI design system is wired up as tooling but **not adopted in the frontend**. `frontend/` is hand-written CSS with no Tailwind; introducing BoardUI means a styling migration, not a drop-in, and should be a deliberate, recorded decision.

- MCP server: `opencode.jsonc` registers the stdio server (`npx -y boardui@latest mcp`), which can read the catalogue and install component source.
- Agent skill: `.agents/skills/boardui/` — installed with `npx boardui@latest skill -p .agents/skills/boardui`. Update with `-f`.

Keep the skill in its own subdirectory. A `SKILL.md` at the root of `.agents/skills/` makes that whole directory a single skill and stops discovery inside it, which hides every other skill in the repo.

If BoardUI is ever adopted, `init` also writes design rules into `AGENTS.md` and `.cursor/rules/`. Review that diff before accepting it: this file carries the issue-tracker and domain-doc conventions above.
