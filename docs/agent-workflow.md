# Agent workflow

Use this procedure for multi-step work, repeated failures, delegation or changes
to the agent process; read only the relevant section. A small, clear fix needs
the relevant rules in
[AGENTS.md](../AGENTS.md) and its domain procedure, not a separate planning document.

## Outcome and plan

Before implementation, identify the observable result, affected boundary and
evidence of success. Reuse the request or existing issue; do not make the user
fill in a template. Clarify only missing information that changes scope or risk,
and continue independent work while waiting.

| Work | Enough planning | Evidence |
| --- | --- | --- |
| Small fix or documentation | State the change and its focused check | Relevant behavior or Markdown/link review |
| Several components or contracts | Short ordered plan with dependencies | Checks for each changed boundary and the user flow |
| Migration, permissions, money, concurrency or HA | Invariants, failure cases, rollout and rollback in the relevant procedure | Required contract/data/runtime checks |

For work spanning sessions, keep a brief checkpoint in the existing issue, PR or
task plan: goal, decisions, files/commit, checks already run, remaining risk and
next action. Add a repository plan only when collaborators need durable project
context; do not commit scratch notes or full conversation logs.

## Context and feedback

- Start from the relevant entry in [the docs map](README.md), a symbol or an
  existing test. Expand the search when evidence shows another dependency.
- Read existing interfaces and tests before inventing a new abstraction. Treat
  current code, CI configuration and live observations as evidence; dated plans
  and remembered results must be rechecked when their state matters.
- Keep one canonical home for a rule or command. Root instructions hold shared
  boundaries and routing; domain docs hold procedures; tool-specific entry points
  link to them. Add a nested instruction only for a distinct local requirement.
- Tools should return the relevant excerpt, failure and exit status. Retain full
  diagnostics as an artifact when needed; do not hide failure or mistake truncated
  output for a successful check.
- After a repeated failure, compare the error, inputs and hypothesis before the
  next attempt. Distinguish a behavior bug from environment, dependency or flaky
  test failures. Change the approach or fix the cause; do not rerun an unchanged
  command or raise effort without new evidence.

## Validation and completion

Select local checks from [verification by change](development-workflow.md#verification-by-change).
For a bug, use a failing behavioral example when practical and a regression check
that would catch its return. Assertions should protect observable behavior or a
real invariant, not merely repeat the implementation. For low-impact prose or
presentation changes, use direct inspection instead of artificial tests.

Review the final diff for scope, boundary violations and failure cases. Check
access/tenant isolation, stale data, concurrency, migrations and generated
contracts when the change touches them. Expand testing when shared dependencies,
failures or unresolved risk justify it; passing focused tests do not waive CI.

Completion follows [the Git workflow](git-workflow.md). Report the delivered
behavior, actual checks, PR/release status and any remaining limitation. A local
test, CI result, merged commit and successful deployment are different evidence;
do not imply one proves the others. If blocked, name the missing input or failed
gate and preserve the next actionable step.

## Delegation and effort

Choose from models actually available in the current environment. Keep model
names and prices out of permanent project policy; honor an explicit user choice
and recommend a change only for a material mismatch.

| Work | Starting choice |
| --- | --- |
| Bounded inventory, docs or a straightforward check | Lower-cost model, low/medium effort |
| Implementation across a known boundary | Model/effort already reliable for comparable work |
| Architecture, concurrency, migrations, HA or security | Stronger reasoning appropriate to the demonstrated risk |

Delegate only if the independent result is worth dispatch, context, integration
and review cost. Keep small or tightly coupled work local; do not create a reviewer
for every edit. Before worthwhile delegation, say:
«Дружища, давай это сделает отдельный агент и с пониженными весами».

Send the goal, allowed scope/paths, constraints and acceptance checks. Prefer a
compact task brief over full history. Assign separate write ownership; use an
isolated checkout when edits would conflict. Test processes still require separate
physical PostgreSQL databases. Ask for findings, changed files, checks and risks;
the primary agent owns integration, validation, publication and the final report.
A subagent's result is evidence, not automatic approval.

## Improve the harness from evidence

When a failure repeats or exposes a concrete important risk, identify the missing
feedback: discoverability, environment setup, contract, test or instruction. Prefer
an enforceable check at the owning layer for a deterministic invariant. Update the
existing canonical rule when it is wrong; do not accumulate broad prohibitions,
duplicate skills or speculative infrastructure. Keep unrelated improvements out
of a small fix.

When changing this process, compare a few similar completed tasks using evidence
already available in the chat, PR and CI: time to verified completion, reported
token/usage data, retries, rework and escaped regressions. Missing usage data stays
unknown. Shorter instructions are measurable; lower total task cost is a hypothesis
until checked. A faster run that omits required checks is not an improvement.

Review instruction changes against these representative cases:

| Case | Expected behavior |
| --- | --- |
| Markdown-only fix | Focused link/Markdown review; normal PR/CI gate; no local DB/build ritual |
| API contract change | Scoped backend checks, regenerated OpenAPI/client, Manager build, required CI |
| Read-only production diagnosis | Fresh observations; no unrequested cleanup, backfill or grants |
| Failed check or long CI wait | Diagnose the failure or use a bounded watcher; no unchanged retry loop |

These are review scenarios, not automated coverage. Current executable gates live
in [CI](../.github/workflows/ci.yml), tests and release scripts. CI checks Manager
build/components, API-client freshness, migrations and backend suites; this does
not mean every architectural instruction is mechanically enforced. CI currently
has no dedicated Markdown/link gate, so documentation review remains explicit.

## Sources and scope

Reviewed 2026-10-06. This procedure adapts current guidance to MVN's existing gates;
external examples do not authorize changing production or installing new tooling.

- [OpenAI: rethinking skills and prompts](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
  — task-specific context, precise boundaries and avoiding instruction bloat.
- [OpenAI: best practices](https://learn.chatgpt.com/guides/best-practices)
  — outcome/verification, practical guidance and bounded delegation.
- [OpenAI: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
  — global, repository and directory instruction scopes.
