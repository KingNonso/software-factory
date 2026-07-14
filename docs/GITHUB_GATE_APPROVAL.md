# GitHub Gate Approval

Status: MVP approval surface

Last updated: 2026-07-14

## Purpose

Humans approve factory gates in GitHub pull requests, not by reading JSON files.
JSON remains the machine/audit format used by `factoryctl`.

## Gate 1 Contract PR

Gate 1 approves intent and constraints before implementation starts.

Generate the PR body:

```bash
python3 software-factory/cli/factoryctl.py submit-gate WP-PKMS-001-001 \
  --project pkms \
  --gate 1 \
  --actor codex:operator \
  --role factory-recorder \
  --reason "prepare Gate 1 Contract PR"
```

The command writes:

```text
software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/gates/gate-1-github-pr-body.md
```

Open the PR with:

```bash
gh pr create \
  --title "Gate 1: Contract approval for WP-PKMS-001-001 - Converge service-layer tenant resolution with ABAC guard" \
  --body-file software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/gates/gate-1-github-pr-body.md
```

The PR body shows:

- problem;
- desired outcome;
- acceptance criteria;
- allowed paths;
- forbidden paths;
- required checks;
- risk level;
- required approver roles;
- rollout and rollback;
- optional OpenHands review prompt; and
- machine digests for audit.

## Human Approval

Review the PR body. Use GitHub's normal review controls:

- `Approve` means the contract can move forward.
- `Request changes` means the agent must revise the contract.
- Comment with product or technical concerns if the package is unclear.

For `R2` PKMS work, require both:

- `product-owner`
- `technical-owner`

After the PR is approved and merged, the factory recorder ingests a GitHub
source event and moves the package from `awaiting_gate_1` to `approved`.

## OpenHands

OpenHands is advisory at Gate 1. It can help find ambiguity or missing tests,
but it does not approve.

Comment this on the Contract PR when useful:

```text
@openhands Review this Gate contract for ambiguity, oversized scope, missing tests, risk misclassification, and rollback gaps. Do not implement code.
```

At Gate 2, OpenHands can review the implementation PR and post inline comments.
Human approval still happens through GitHub review.

## Recorder Source Event

Until GitHub API ingestion is implemented, the recorder uses a source event
shaped like:

```text
software-factory/templates/gate-source/gate-1-github-pr-source.example.json
```

This file is not for human review. It is a bridge between authenticated GitHub
activity and the factory ledger.

## Future Automation

The target implementation is:

1. `factoryctl submit-gate` generates the Contract PR body.
2. GitHub Actions validates factory artifacts on the PR.
3. Required reviewers approve through GitHub.
4. Merge of the Contract PR emits an authenticated event.
5. `factoryctl ingest-gate` reads GitHub API evidence and records the gate
   receipt.
6. Station 2 planning begins automatically.
