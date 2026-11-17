# CLAUDE.md — Freya FDE Challenge

Project-level working agreement for the Freya (YC S25) FDE challenge.
Global rules in `~/.claude/` still apply. Where they conflict with this file (e.g. heavy planning-doc
or process requirements), this file wins: keep it lean.

## Roles
- **User** owns core decisions: scope, architecture, stack, trade-offs, what ships.
- **Claude** is the operating assistant: proposes options with a clear recommendation, implements
  agreed decisions, and keeps the docs below current.
- For any decision that shapes the product or architecture: present options + recommendation, then
  wait for the user. Never pick silently.

## Source-of-truth docs
| File | Purpose | Update when |
|---|---|---|
| `CHALLENGE.md` | Brief description of the challenge (from the user's screenshots) | Our understanding of the challenge changes |
| `PROGRESS.md` | Current status + dated decision log | Every decision, every finished milestone |
| `CLAUDE.md` | How we work | The working agreement changes |

Claude also keeps its project memory in sync with the path we chose (phase, approach, open questions).

## Engineering rules
1. **Surgical**: touch only what the task needs. No drive-by refactors.
2. **Clear**: small functions, explicit names, no clever tricks.
3. **Testable**: every service/functionality ships with its own test script. Not done until it passes.
4. **Scalable**: clean boundaries between services so pieces can grow or be swapped. No premature optimization.
5. **No overengineering**: build what the challenge asks for, nothing speculative. No abstractions for
   single-use code, no "just in case" config. If a simpler approach exists, use it or raise it.

## Workflow
1. Read challenge screenshots → write `CHALLENGE.md`.
2. Discuss strategy → record decisions in `PROGRESS.md`.
3. Build in small slices: implement → test script → passing → log in `PROGRESS.md`.

## Stack & commands
TBD: filled in once the stack is decided (see `PROGRESS.md`).
