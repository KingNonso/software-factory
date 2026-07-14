# OpenHands Integration

Status: proposed adapter and review surface

Last updated: 2026-07-14

## Role

OpenHands should be treated as a worker and reviewer, not as the authority for
factory state.

Use OpenHands for:

- issue-to-PR implementation;
- PR explanations;
- requested updates;
- advisory Gate 1 contract review;
- automated implementation PR review with inline comments; and
- remediation suggestions.

Do not use OpenHands for:

- final Gate 1 approval;
- final Gate 2 approval;
- direct edits to factory state;
- bypassing `factoryctl`; or
- weakening contracts to make implementation easier.

## Gate 1 Contract PR

After `factoryctl submit-gate` writes the GitHub PR body, the operator can
mention OpenHands on the Contract PR:

```text
@openhands Review this Gate contract for ambiguity, oversized scope, missing tests, risk misclassification, and rollback gaps. Do not implement code.
```

Expected OpenHands output:

- questions;
- missing acceptance criteria;
- risk or scope concerns;
- suggested test additions; and
- rollback concerns.

The human approver decides whether those comments require changes.

## Implementation PR

OpenHands can review implementation PRs and post inline comments. Its review is
evidence for Station 4, but it is not sufficient by itself for independent
verification unless the verifier identity, SHA, evidence, and no-write boundary
are recorded by the factory.

## GitHub Workflow

A project may install an OpenHands PR review workflow in `.github/workflows/`.
Keep reusable configuration under:

```text
software-factory/templates/github-workflows/
```

The workflow should:

- trigger on implementation PRs and optionally Contract PRs;
- post comments instead of modifying code during review;
- avoid secrets on untrusted forks;
- identify the exact PR head SHA reviewed; and
- preserve human approval as the final authority.
