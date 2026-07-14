# Software Factory Operator Manual

Status: MVP operator manual

Applies to: `software-factory/` version `0.1.0`

First attached project: `pkms`

Last updated: 2026-07-14

## 1. What This Factory Does

The software factory is a deterministic control plane for AI-assisted software
delivery. It does not replace Codex, Claude Code, gstack, CI, or GitHub. It
gives them a shared operating contract:

- what work is approved;
- which files and risks are in scope;
- what evidence must exist;
- who approved a gate;
- which state the work package is in; and
- why the package may advance or must stop.

Humans own intent, constraints, risk, architecture, and acceptable outcomes.
Agents perform decomposition, implementation, verification, documentation, and
operational work inside approved boundaries.

## 2. Installed Layout

Reusable core:

```text
software-factory/
|-- README.md
|-- policy.json
|-- cli/factoryctl.py
|-- cli/tests/
|-- schemas/
|-- prompts/
|-- adapters/
|-- templates/
|-- adr/
`-- docs/OPERATOR_MANUAL.md
```

PKMS adapter:

```text
software-factory/projects/pkms/
|-- project.json
|-- adr/
|-- architecture/
|-- control/boards/
`-- work-packages/PKMS-001/WP-PKMS-001-001/
    |-- manifest.json
    |-- outcome-contract.json
    |-- build-contract.json
    |-- state.json
    |-- ledger.jsonl
    |-- plan.md
    |-- gates/
    |-- evidence/
    `-- reviews/
```

Project-owned PKMS product and code remain outside the reusable factory:

```text
product/
tasks/
backend/
frontend/
```

## 3. Operator Roles

`product-owner`: approves product outcome, non-goals, and acceptance criteria.

`technical-owner`: approves build boundaries, risk, tests, rollout, and
rollback.

`factory-recorder`: runs `factoryctl` to validate artifacts and record state.
The recorder writes the ledger but does not invent approval.

`implementer`: Codex, Claude Code, or another worker that writes code after the
package is claimed.

`verifier`: a separate worker that challenges the implementation without
modifying the implementation branch before issuing a verdict.

For `R2` PKMS work, Gate 1 and Gate 2 require both `product-owner` and
`technical-owner`.

## 4. Current PKMS Pilot Package

The first attached package is:

```text
WP-PKMS-001-001
```

Title:

```text
Converge service-layer tenant resolution with ABAC guard
```

Current state:

```text
awaiting_gate_1
```

Why this was chosen:

- It exists in `tasks/backlog.md` as `T-011`.
- It is a cross-tenant correctness risk.
- It exercises contracts, gate approval, risk policy, and independent
  verification.
- It is bounded enough for one work package.

Human review packet:

```text
software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/gates/gate-1-request.md
```

## 5. Daily Commands

Run commands from the repository root:

```bash
python3 software-factory/cli/factoryctl.py doctor
python3 software-factory/cli/factoryctl.py inventory
python3 software-factory/cli/factoryctl.py validate
python3 software-factory/cli/factoryctl.py status WP-PKMS-001-001 --project pkms
python3 software-factory/cli/factoryctl.py select-next --project pkms --shadow
python3 software-factory/cli/factoryctl.py generate-boards --project pkms
```

Use this when you need a digest for approval, evidence, or debugging:

```bash
python3 software-factory/cli/factoryctl.py digest <path>
```

Run factory unit tests:

```bash
python3 -m unittest discover -s software-factory/cli/tests -v
```

## 6. How Humans See Defined Work

Humans do not approve JSON or a chat summary. They review a GitHub Contract PR.

For a work package, inspect:

```text
gates/gate-1-github-pr-body.md
```

For the PKMS pilot:

```bash
sed -n '1,260p' software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/gates/gate-1-github-pr-body.md
```

The Gate 1 GitHub PR body shows:

- work package ID;
- title;
- current state;
- risk and independence level;
- problem;
- desired outcome;
- acceptance criteria;
- allowed and forbidden paths;
- required checks;
- rollout and rollback;
- required approver roles;
- optional OpenHands review prompt; and
- machine digests for audit.

Board views are generated here:

```text
software-factory/projects/pkms/control/boards/backlog.md
software-factory/projects/pkms/control/boards/in-progress.md
software-factory/projects/pkms/control/boards/qa.md
software-factory/projects/pkms/control/boards/in-review.md
software-factory/projects/pkms/control/boards/done.md
```

These are factory-owned views. They do not replace `tasks/*.md` yet.

## 7. Gate 1 Approval

Gate 1 answers:

- Is this the right user outcome?
- Are acceptance criteria falsifiable?
- Are non-goals and constraints correct?
- Is the risk level correct?
- Is the required independence level correct?

To generate or refresh the Gate 1 Contract PR body:

```bash
python3 software-factory/cli/factoryctl.py submit-gate WP-PKMS-001-001 \
  --project pkms \
  --gate 1 \
  --actor codex:operator \
  --role factory-recorder \
  --reason "prepare Gate 1 Contract PR"
```

Open a GitHub PR using the generated body:

```bash
gh pr create \
  --title "Gate 1: Contract approval for WP-PKMS-001-001 - Converge service-layer tenant resolution with ABAC guard" \
  --body-file software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/gates/gate-1-github-pr-body.md
```

Humans approve through the GitHub PR review UI:

- `Approve` means the contract can advance.
- `Request changes` means the contract returns to shaping.
- Comments are product or technical review notes.

For `R2` PKMS work, require both `product-owner` and `technical-owner`.

Optional advisory OpenHands review:

```text
@openhands Review this Gate contract for ambiguity, oversized scope, missing tests, risk misclassification, and rollback gaps. Do not implement code.
```

After the Contract PR is approved and merged, the factory recorder ingests a
GitHub source event:

```bash
python3 software-factory/cli/factoryctl.py ingest-gate WP-PKMS-001-001 \
  --project pkms \
  --gate 1 \
  --source-event <github-gate-source.json> \
  --actor human-or-service:factory-recorder \
  --role factory-recorder \
  --reason "record GitHub Gate 1 approval"
```

If approved, the state advances:

```text
awaiting_gate_1 -> approved
```

If modified, rejected, or deferred, the state advances according to policy:

```text
modify -> shaping
reject -> rejected
defer -> deferred
```

The local JSON source templates are for recorder bootstrap and tests only:

```text
software-factory/templates/gate-source/gate-1-github-pr-source.example.json
software-factory/templates/gate-source/gate-1-local-source.example.json
```

The normal human approval surface is GitHub.

## 8. Station 2 Planning

After Gate 1 approval, Station 2 creates the detailed implementation plan.

Expected command sequence:

```bash
python3 software-factory/cli/factoryctl.py transition WP-PKMS-001-001 \
  --project pkms \
  --to planning \
  --actor codex:planner \
  --role task-planner \
  --reason "begin Station 2 planning"
```

Station 2 then updates:

```text
plan.md
```

When the plan is complete and still matches the contracts:

```bash
python3 software-factory/cli/factoryctl.py validate WP-PKMS-001-001 --project pkms

python3 software-factory/cli/factoryctl.py transition WP-PKMS-001-001 \
  --project pkms \
  --to ready \
  --actor codex:planner \
  --role task-planner \
  --reason "Station 2 plan complete"
```

If planning discovers that intent, risk, architecture, or blocking acceptance
criteria must change, return to shaping instead of implementing:

```bash
python3 software-factory/cli/factoryctl.py transition WP-PKMS-001-001 \
  --project pkms \
  --to shaping \
  --actor codex:planner \
  --role task-planner \
  --reason "planning found contract-changing ambiguity"
```

## 9. Claiming Work

Only `ready` packages can be claimed.

```bash
python3 software-factory/cli/factoryctl.py claim WP-PKMS-001-001 \
  --project pkms \
  --actor codex:<run-id> \
  --role implementer \
  --lease 4h \
  --branch factory/WP-PKMS-001-001 \
  --worktree ../pkms-WP-PKMS-001-001 \
  --reason "claim implementation work"
```

This records:

- owner;
- claim timestamp;
- lease expiry;
- intended branch;
- intended worktree; and
- ledger event hash.

If the implementer cannot proceed:

```bash
python3 software-factory/cli/factoryctl.py release WP-PKMS-001-001 \
  --project pkms \
  --actor codex:<run-id> \
  --role implementer \
  --reason "release claim"
```

## 10. How Agents Update State

Agents update state only through `factoryctl`. They do not hand-edit
`state.json` or `ledger.jsonl`.

Use guarded transitions:

```bash
python3 software-factory/cli/factoryctl.py transition WP-PKMS-001-001 \
  --project pkms \
  --to implementing \
  --actor codex:<run-id> \
  --role implementer \
  --reason "implementation started"
```

Then, after implementation and author checks:

```bash
python3 software-factory/cli/factoryctl.py transition WP-PKMS-001-001 \
  --project pkms \
  --to self_checked \
  --actor codex:<run-id> \
  --role implementer \
  --evidence software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/evidence/manifest.json \
  --reason "author checks complete"
```

The CLI rejects illegal transitions. For example:

```text
awaiting_gate_1 -> claimed
```

is invalid because Gate 1 and Station 2 have not completed.

Every state-changing command should use an idempotency key in automation:

```bash
--idempotency-key WP-PKMS-001-001:<station>:<attempt>:<action>
```

Reusing the same key with different input fails.

## 11. Evidence Requirements

Evidence belongs under:

```text
software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/evidence/
```

The evidence manifest must map blocking acceptance criteria to proof:

```text
AC-001 -> source inspection plus targeted test
AC-002 -> source inspection plus targeted test
AC-003 -> pytest result
```

Evidence records should include:

- command;
- exit code;
- timestamp;
- implementation SHA;
- artifact path;
- artifact SHA-256;
- producer identity; and
- known gaps.

Do not store secrets, tokens, private staff content, production data, or large
logs in the repository. Store large artifacts in CI/object storage and record
stable links and hashes.

## 12. Independent Verification

Move to verification only after CI/evidence exists for the frozen
implementation SHA:

```bash
python3 software-factory/cli/factoryctl.py transition WP-PKMS-001-001 \
  --project pkms \
  --to verifying \
  --actor codex:<run-id> \
  --role factory-recorder \
  --reason "CI evidence ready for independent verification"
```

The verifier must use a fresh session and must not modify the implementation
branch before reporting.

Verifier output goes here:

```text
software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/reviews/verification-report.json
```

Record the verdict:

```bash
python3 software-factory/cli/factoryctl.py record-verdict WP-PKMS-001-001 \
  --project pkms \
  software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/reviews/verification-report.json \
  --actor codex:factory-recorder \
  --role factory-recorder \
  --reason "record independent verification verdict"
```

Verifier recommendation effects:

```text
APPROVE -> verified
COMMENT -> remediation
REQUEST_CHANGES -> remediation
```

## 13. Remediation Loop

When verification finds issues:

```text
verifying -> remediation -> self_checked -> draft_pr_open -> ci_pending -> verifying
```

Rules:

- Fix only inside the approved Build Contract.
- Do not weaken the Outcome Contract to make tests pass.
- Run author checks again after every code change.
- Run independent verification again after every new implementation SHA.
- Respect `max_remediation_cycles`.

If remediation requires intent or architecture change, return to `shaping` and
repeat Gate 1.

## 14. Gate 2 Approval

Gate 2 answers:

- Does the product result satisfy the approved outcome?
- Does the implementation respect technical constraints?
- Does independent verification pass?
- Are residual risks acceptable?
- Are rollout and rollback acceptable?
- Is the PR head and merge candidate unchanged since verification?

Generate the Gate 2 packet when state is `awaiting_gate_2`:

```bash
python3 software-factory/cli/factoryctl.py submit-gate WP-PKMS-001-001 \
  --project pkms \
  --gate 2 \
  --actor codex:operator \
  --role factory-recorder \
  --reason "submit Gate 2 packet"
```

Ingest Gate 2 approval:

```bash
python3 software-factory/cli/factoryctl.py ingest-gate WP-PKMS-001-001 \
  --project pkms \
  --gate 2 \
  --source-event <gate-2-source.json> \
  --actor human-or-service:factory-recorder \
  --role factory-recorder \
  --reason "record Gate 2 approval"
```

If approved:

```text
awaiting_gate_2 -> approved_to_merge
```

No code commit after Gate 2 may be merged under the old approval. A changed PR
head invalidates verification and Gate 2.

## 15. Board Generation

Refresh factory board views:

```bash
python3 software-factory/cli/factoryctl.py generate-boards --project pkms
```

Generated files:

```text
software-factory/projects/pkms/control/boards/backlog.md
software-factory/projects/pkms/control/boards/in-progress.md
software-factory/projects/pkms/control/boards/qa.md
software-factory/projects/pkms/control/boards/in-review.md
software-factory/projects/pkms/control/boards/done.md
```

These board files are safe for humans to inspect. They are generated from
factory state and should not be treated as the source of truth.

## 16. Adding A New Work Package

Create a scaffold:

```bash
python3 software-factory/cli/factoryctl.py create PKMS-001 WP-PKMS-001-002 \
  --project pkms \
  --title "Short title" \
  --risk R1 \
  --independence I1 \
  --actor codex:planner \
  --role next-work-planner
```

Then edit:

```text
manifest.json
outcome-contract.json
build-contract.json
```

Remove TODOs and blocking ambiguities before Gate 1. Run:

```bash
python3 software-factory/cli/factoryctl.py validate WP-PKMS-001-002 --project pkms
```

Move to `awaiting_gate_1` only when the contract is ready:

```bash
python3 software-factory/cli/factoryctl.py transition WP-PKMS-001-002 \
  --project pkms \
  --to awaiting_gate_1 \
  --actor codex:planner \
  --role next-work-planner \
  --reason "contracts ready for Gate 1"
```

## 17. Attaching Another Project

To reuse the factory:

1. Copy or vendor `software-factory/`.
2. Create `software-factory/projects/<project-slug>/project.json`.
3. Point the adapter at the project PRD, tasks, architecture, checks, and risk
   rules.
4. Create the first work package under
   `software-factory/projects/<project-slug>/work-packages/<PRD>/<WP>/`.
5. Run `doctor`, `validate`, `inventory`, and `generate-boards`.

Do not copy PKMS-specific paths or risk rules into the reusable core.

## 18. Failure Handling

`factoryctl validate` fails:

- Read every `ERROR:` line.
- Fix missing files, stale digests, invalid JSON, illegal ledger chains, or
  evidence gaps.
- Rerun validation.

An approval source is rejected:

- Check `gate`, `work_package_id`, and `decision`.
- Check required roles in `project.json`.
- For `R2`, include both `product-owner` and `technical-owner`.

An illegal transition is rejected:

- Run `status` to inspect current state.
- Use the state machine in `software-factory/README.md`.
- Do not bypass a gate by editing JSON manually.

A contract digest is stale:

- If the change is editorial and does not affect intent or risk, regenerate the
  gate packet and record the new digest.
- If the change affects intent, risk, architecture, or blocking acceptance
  criteria, return to `shaping` and repeat Gate 1.

## 19. Current MVP Limits

The MVP is intentionally local and deterministic.

Current limits:

- Gate PR body generation is implemented.
- Gate source ingestion still accepts local JSON paths; direct GitHub API
  ingestion is not implemented yet.
- Isolated worktree creation is documented but not automated yet.
- PR head, merge-candidate SHA, and deployment binding are documented but not
  fully enforced yet.
- JSON Schema files are present, while the CLI currently uses explicit standard
  library checks.
- Board files are generated under `software-factory/projects/pkms/control/` and
  do not update `tasks/*.md`.

Do not treat bootstrap-local gate sources as production-grade approval. The
normal human surface is the GitHub Contract PR; the next hardening step is
authenticated GitHub review or environment approval ingestion.

## 20. Minimum Operator Checklist

Before implementation:

- `doctor` passes.
- `validate` passes.
- Gate 1 Contract PR body exists.
- Product and technical owners approve the Contract PR.
- Gate 1 is ingested.
- Station 2 plan is complete.
- Package reaches `ready`.
- Implementer claims the package.

Before Gate 2:

- Implementation SHA is recorded.
- Evidence manifest covers every blocking acceptance criterion.
- Required checks have run.
- Independent verifier report exists.
- Verifier identity differs from implementer identity.
- No code changed after verification without a new verification pass.
- Gate 2 packet binds PR head, merge candidate, evidence, rollout, and rollback.

Before merge or deploy:

- Gate 2 is approved.
- PR head and merge candidate still match approved evidence.
- Required CI is green.
- Rollback path is known.
- Production deployment is authorized by the normal protected path.
