# Gate 1 Contract Approval

**Work package:** `WP-PKMS-001-001`
**Project:** `pkms`
**Title:** Converge service-layer tenant resolution with ABAC guard
**Current factory state:** `awaiting_gate_1`
**Risk:** `R2`
**Required independence:** `I2`
**Required human approvers:** product-owner, technical-owner

## What Approval Means

Approving this PR authorizes agents to plan and implement this exact work package. It does not approve code or deployment.

Approve only if the outcome, scope, tests, risk, and rollback below are acceptable.

## Problem

The ABAC guard may authorize a request using the shared request organization resolver while messaging and notification services resolve the current organization through a narrower fallback chain. That can make authorization and data access disagree when the tenant is derivable from headers but not attached to the request object.

## Desired Outcome

Every service-layer path that needs the current organization uses the same resolver as the ABAC guard, so an admitted request and the data path agree on tenant context or fail closed.

## Acceptance Criteria

- **AC-001** (blocking; oracle: `code-review-plus-test`): Messaging service organization resolution uses the shared request organization resolver instead of a custom tenant/org/user fallback chain.
  Evidence expected: `targeted pytest`, `verifier source inspection`
- **AC-002** (blocking; oracle: `code-review-plus-test`): Notification service organization resolution uses the shared request organization resolver instead of a custom tenant/org/user fallback chain.
  Evidence expected: `targeted pytest`, `verifier source inspection`
- **AC-003** (blocking; oracle: `automated-test`): A regression test covers a header-derived tenant path where the ABAC guard and the service layer must resolve the same organization.
  Evidence expected: `pytest result`
- **AC-004** (non-blocking; oracle: `source-inspection`): The stale user-facing copy 'Organization context is required.' in messaging service error handling is removed or replaced with copy that matches the tenant terminology used by the current codebase.
  Evidence expected: `verifier source inspection`

## Scope Boundaries

**Allowed paths:**

- `backend/api/apps/messaging/`
- `backend/api/apps/notifications/`
- `backend/api/apps/core/`
- `backend/api/apps/*/tests/`

**Forbidden paths:**

- `.github/workflows/`
- `backend/api/apps/abac/services/permission_registry.py`

## Non-Goals

- Do not redesign ABAC permissions.
- Do not change the tenant middleware contract unless a blocking defect proves it is necessary.
- Do not add new organization or tenant models.
- Do not change deployment workflows.

## Required Checks

- **backend-django-check**: Django configuration and app registry check
  Command: `cd backend && PYTHONPATH=. DJANGO_SETTINGS_MODULE=config.settings.test uv run python manage.py check`
- **backend-pytest**: Run backend tests
  Command: `cd backend && PYTHONPATH=. DJANGO_SETTINGS_MODULE=config.settings.test uv run pytest`

## Security And Privacy Constraints

- Fail closed when tenant context is absent.
- Do not weaken PermissionRequired or registered ABAC codenames.
- Do not log secrets, request tokens, personal data, or private staff content.
- Keep UUID inputs at request boundaries and internal integer IDs inside service code where applicable.

## Rollout

normal protected merge after Gate 2; no separate data migration or deployment workflow change

## Rollback

revert the implementation commit and redeploy the prior backend artifact

## Optional OpenHands Review Prompt

Comment this on the PR if you want an advisory agent review before human approval:

```text
@openhands Review this Gate contract for ambiguity, oversized scope, missing tests, risk misclassification, and rollback gaps. Do not implement code.
```

OpenHands feedback is advisory. Human approval is still the GitHub PR review.

## Human Approval Checklist

- [ ] Product owner agrees this is the right outcome.
- [ ] Technical owner agrees the scope and tests are sufficient.
- [ ] Risk and independence levels are acceptable.
- [ ] Rollback is acceptable.
- [ ] No blocking ambiguity remains.

## Machine Record

These files are for `factoryctl` validation and audit. Humans should not need to read them unless debugging the control plane.

- Outcome Contract: `software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/outcome-contract.json`
- Outcome digest: `sha256:7b487bc1cee82b8dcb167baacb75c56ec48127bbcf8fb99886618a658cf89923`
- Build Contract: `software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/build-contract.json`
- Build digest: `sha256:d964d21848f24fc67c2fe7eccbe136d1e38b696123eca074e3211dc247e0e013`
- State: `software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/state.json`
- Ledger: `software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/ledger.jsonl`

## After This PR Is Approved And Merged

The factory recorder ingests the authenticated GitHub approval and advances `WP-PKMS-001-001` to the next state.
