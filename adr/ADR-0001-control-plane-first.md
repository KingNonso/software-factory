# ADR-0001: Build The Factory As A Deterministic Control Plane

Status: accepted

Date: 2026-07-14

## Context

The repository needs Codex, Claude Code, and future workers to plan, implement,
review, and continue product work with minimal human intervention. The same
system also needs human approval, risk limits, independent verification, and
auditable state.

General-purpose agent runtimes can execute work, but they should not be the
source of truth for approvals, evidence, or state transitions.

## Decision

Build `software-factory/` as a reusable deterministic control plane. It owns
contracts, schemas, state, ledgers, evidence manifests, gate packets, prompts,
project adapters, and the `factoryctl` CLI. Agent tools remain replaceable
execution engines.

## Consequences

- State transitions can be tested without an LLM.
- Human approval binds to hashes instead of chat summaries.
- Codex and Claude can both operate against the same artifacts.
- The local MVP can run with Python standard library only.
- A later orchestrator such as Temporal can host the workflow without owning the
  product policy.

## Rejected Options

- Make one agent product the source of truth: rejected because it makes approval,
  evidence, and state harder to audit and harder to replace.
- Start with a distributed orchestration service: rejected because the first
  risk is governance correctness, not scheduling reliability.
