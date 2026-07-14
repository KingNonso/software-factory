# ADR-0001: Attach PKMS Through A Thin Project Adapter

Status: accepted

Date: 2026-07-14

## Context

PKMS already has product documents, task boards, backend/frontend apps, and
agent rules. The reusable factory should not absorb PKMS-specific product facts
into the core.

## Decision

Attach PKMS through `software-factory/projects/pkms/project.json` and package
state under `software-factory/projects/pkms/work-packages/`. Product PRDs remain
in `product/`, application code remains in `backend/` and `frontend/`, and the
factory adapter references those paths.

## Consequences

- The factory can be copied or vendored into another repo.
- PKMS-specific commands, risk rules, and path policies stay out of reusable
  schemas and prompts.
- Existing task boards can continue as human-facing inputs while the factory
  ledger becomes the package lifecycle source of truth.

## Rejected Options

- Move product PRDs under `software-factory/`: rejected because product intent is
  project-owned input, not reusable factory code.
- Rewrite the existing task boards first: rejected because the adapter can run
  before full source-of-truth cleanup is complete.
