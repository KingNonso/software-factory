#!/usr/bin/env python3
"""Deterministic control-plane CLI for the reusable software factory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


VERSION = "0.1.0"

FACTORY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = FACTORY_ROOT.parent
PROJECTS_ROOT = FACTORY_ROOT / "projects"

STATES = [
    "candidate",
    "shaping",
    "awaiting_gate_1",
    "approved",
    "planning",
    "ready",
    "claimed",
    "implementing",
    "self_checked",
    "draft_pr_open",
    "ci_pending",
    "verifying",
    "remediation",
    "verified",
    "awaiting_gate_2",
    "approved_to_merge",
    "merged",
    "deployed",
    "observing",
    "closed",
    "rejected",
    "deferred",
    "cancelled",
    "blocked",
    "verification_failed",
    "rolled_back",
    "superseded",
    "closed_non_runtime",
    "incident_closed",
]

STATE_INDEX = {state: index for index, state in enumerate(STATES)}

TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"shaping", "deferred", "superseded", "cancelled"},
    "shaping": {"awaiting_gate_1", "deferred", "rejected", "superseded", "blocked"},
    "awaiting_gate_1": {"approved", "shaping", "rejected", "deferred", "superseded", "blocked"},
    "approved": {"planning", "blocked", "cancelled"},
    "planning": {"ready", "blocked", "cancelled"},
    "ready": {"claimed", "blocked", "cancelled"},
    "claimed": {"implementing", "ready", "blocked", "cancelled"},
    "implementing": {"self_checked", "blocked", "cancelled"},
    "self_checked": {"draft_pr_open", "implementing", "blocked", "cancelled"},
    "draft_pr_open": {"ci_pending", "self_checked", "blocked", "cancelled"},
    "ci_pending": {"verifying", "self_checked", "blocked", "cancelled"},
    "verifying": {"verified", "remediation", "verification_failed", "blocked", "cancelled"},
    "remediation": {"self_checked", "blocked", "cancelled"},
    "verified": {"awaiting_gate_2", "blocked", "cancelled"},
    "awaiting_gate_2": {"approved_to_merge", "remediation", "shaping", "rejected", "blocked"},
    "approved_to_merge": {"merged", "blocked", "cancelled"},
    "merged": {"deployed", "closed_non_runtime", "rolled_back", "blocked"},
    "deployed": {"observing", "rolled_back", "blocked"},
    "observing": {"closed", "rolled_back", "blocked"},
    "rolled_back": {"remediation", "incident_closed", "blocked"},
    "blocked": set(STATES),
}

BOARD_BUCKETS = {
    "backlog": {"candidate", "shaping", "awaiting_gate_1", "approved", "planning", "ready", "deferred"},
    "in-progress": {
        "claimed",
        "implementing",
        "self_checked",
        "draft_pr_open",
        "ci_pending",
        "remediation",
        "blocked",
    },
    "qa": {"verifying", "verified", "verification_failed"},
    "in-review": {"awaiting_gate_2", "approved_to_merge"},
    "done": {"merged", "deployed", "observing", "closed", "closed_non_runtime", "incident_closed"},
}

REQUIRED_PROJECT_KEYS = {"schema_version", "project_slug", "name", "paths", "commands", "gate_policy"}
REQUIRED_MANIFEST_KEYS = {
    "schema_version",
    "work_package_id",
    "prd_id",
    "title",
    "contract_revision",
    "outcome_contract",
    "build_contract",
    "risk",
    "independence",
    "acceptance_criteria",
    "allowed_paths",
    "forbidden_paths",
}
REQUIRED_OUTCOME_KEYS = {
    "schema_version",
    "work_package_id",
    "prd",
    "problem",
    "desired_outcome",
    "target_users",
    "acceptance_criteria",
    "invariants",
    "non_goals",
    "ambiguities",
}
REQUIRED_BUILD_KEYS = {
    "schema_version",
    "work_package_id",
    "architecture_refs",
    "allowed_paths",
    "forbidden_paths",
    "security_privacy_constraints",
    "migration",
    "required_checks",
    "adversarial_scenarios",
    "rollout",
    "rollback",
    "risk",
    "budgets",
}


class FactoryError(Exception):
    """Raised for deterministic factory contract failures."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise FactoryError(f"missing JSON file: {display_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise FactoryError(f"invalid JSON in {display_path(path)}: {exc}") from exc
    if not isinstance(data, dict):
        raise FactoryError(f"{display_path(path)} must contain a JSON object")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def require_keys(data: dict[str, Any], keys: set[str], label: str) -> list[str]:
    return [f"{label} missing required key: {key}" for key in sorted(keys - data.keys())]


def project_config(project: str) -> dict[str, Any]:
    path = PROJECTS_ROOT / project / "project.json"
    data = load_json(path)
    data["_path"] = path
    return data


def iter_project_configs(project: str | None = None) -> list[dict[str, Any]]:
    if project:
        return [project_config(project)]
    configs = []
    for path in sorted(PROJECTS_ROOT.glob("*/project.json")):
        data = load_json(path)
        data["_path"] = path
        configs.append(data)
    return configs


def package_root(project_data: dict[str, Any]) -> Path:
    path_text = project_data.get("paths", {}).get("work_packages")
    if not path_text:
        return project_data["_path"].parent / "work-packages"
    return repo_path(path_text)


def find_work_package(work_package_id: str, project: str | None = None) -> tuple[dict[str, Any], Path]:
    for project_data in iter_project_configs(project):
        root = package_root(project_data)
        for manifest_path in sorted(root.glob(f"*/{work_package_id}/manifest.json")):
            return project_data, manifest_path.parent
    raise FactoryError(f"work package not found: {work_package_id}")


def iter_work_packages(project: str | None = None) -> list[tuple[dict[str, Any], Path]]:
    packages: list[tuple[dict[str, Any], Path]] = []
    for project_data in iter_project_configs(project):
        root = package_root(project_data)
        for manifest_path in sorted(root.glob("*/*/manifest.json")):
            packages.append((project_data, manifest_path.parent))
    return packages


def load_manifest(package_dir: Path) -> dict[str, Any]:
    data = load_json(package_dir / "manifest.json")
    data["_path"] = package_dir / "manifest.json"
    return data


def load_state(package_dir: Path) -> dict[str, Any]:
    return load_json(package_dir / "state.json")


def state_path(package_dir: Path) -> Path:
    return package_dir / "state.json"


def ledger_path(package_dir: Path) -> Path:
    return package_dir / "ledger.jsonl"


def read_ledger(package_dir: Path) -> list[dict[str, Any]]:
    path = ledger_path(package_dir)
    if not path.exists():
        return []
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FactoryError(f"{display_path(path)}:{line_number} is invalid JSON: {exc}") from exc
        if not isinstance(event, dict):
            raise FactoryError(f"{display_path(path)}:{line_number} must be a JSON object")
        events.append(event)
    return events


def event_hash(event: dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "event_hash"}
    return sha256_bytes(canonical_json(payload))


def validate_ledger(package_dir: Path) -> list[str]:
    errors: list[str] = []
    prior_hash = None
    prior_state = None
    for index, event in enumerate(read_ledger(package_dir), start=1):
        label = f"{display_path(ledger_path(package_dir))}:{index}"
        expected_hash = event_hash(event)
        if event.get("event_hash") != expected_hash:
            errors.append(f"{label} event_hash mismatch")
        if event.get("previous_event_hash") != prior_hash:
            errors.append(f"{label} previous_event_hash mismatch")
        previous_state = event.get("previous_state")
        next_state = event.get("next_state")
        if previous_state and previous_state not in STATES:
            errors.append(f"{label} previous_state is invalid: {previous_state}")
        if next_state and next_state not in STATES:
            errors.append(f"{label} next_state is invalid: {next_state}")
        if previous_state and next_state and previous_state != next_state:
            if next_state not in TRANSITIONS.get(previous_state, set()):
                errors.append(f"{label} illegal transition: {previous_state} -> {next_state}")
        if prior_state and previous_state and previous_state != prior_state:
            errors.append(f"{label} previous_state does not follow prior next_state")
        prior_hash = event.get("event_hash")
        prior_state = next_state or prior_state
    return errors


def ledger_tail_hash(package_dir: Path) -> str | None:
    events = read_ledger(package_dir)
    if not events:
        return None
    return events[-1].get("event_hash")


def command_input_hash(command: str, args: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json({"command": command, "args": args}))


def find_idempotent_event(package_dir: Path, key: str | None, input_hash: str) -> dict[str, Any] | None:
    if not key:
        return None
    for event in read_ledger(package_dir):
        if event.get("idempotency_key") == key:
            if event.get("input_hash") != input_hash:
                raise FactoryError(f"idempotency key reused with different input: {key}")
            return event
    return None


def actor_identity(actor: str, role: str = "operator") -> dict[str, str]:
    provider = actor.split(":", 1)[0] if ":" in actor else "local"
    return {
        "id": actor,
        "role": role,
        "provider": provider,
        "run_id": os.environ.get("FACTORY_RUN_ID", ""),
    }


def append_event(
    package_dir: Path,
    *,
    work_package_id: str,
    actor: str,
    role: str,
    event_type: str,
    previous_state: str | None,
    next_state: str | None,
    reason: str,
    input_hash: str,
    idempotency_key: str | None = None,
    artifacts: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = find_idempotent_event(package_dir, idempotency_key, input_hash)
    if existing:
        return existing
    prior_tail = ledger_tail_hash(package_dir)
    event = {
        "schema_version": 1,
        "event_id": f"evt_{uuid.uuid4().hex}",
        "timestamp": utc_now(),
        "work_package_id": work_package_id,
        "actor": actor_identity(actor, role),
        "event_type": event_type,
        "previous_state": previous_state,
        "next_state": next_state,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "input_hash": input_hash,
        "previous_event_hash": prior_tail,
        "artifacts": artifacts or {},
        "data": data or {},
    }
    event["event_hash"] = event_hash(event)
    ledger_path(package_dir).parent.mkdir(parents=True, exist_ok=True)
    with ledger_path(package_dir).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def parse_duration(value: str) -> timedelta:
    unit = value[-1]
    amount_text = value[:-1]
    if unit not in {"m", "h", "d"} or not amount_text.isdigit():
        raise FactoryError("lease duration must look like 30m, 4h, or 1d")
    amount = int(amount_text)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


def now_plus(duration: timedelta) -> str:
    return (datetime.now(timezone.utc) + duration).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def contract_digests(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "outcome": sha256_file(repo_path(manifest["outcome_contract"])),
        "build": sha256_file(repo_path(manifest["build_contract"])),
    }


def validate_project(project_data: dict[str, Any]) -> list[str]:
    errors = require_keys(project_data, REQUIRED_PROJECT_KEYS, display_path(project_data["_path"]))
    if project_data.get("schema_version") != 1:
        errors.append(f"{display_path(project_data['_path'])} schema_version must be 1")
    for key, value in project_data.get("paths", {}).items():
        if key in {"work_packages", "product_root", "tasks_root"}:
            if not repo_path(value).exists():
                errors.append(f"project path does not exist: {key}={value}")
    return errors


def validate_package(project_data: dict[str, Any], package_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest = load_manifest(package_dir)
    label = display_path(manifest["_path"])
    errors.extend(require_keys(manifest, REQUIRED_MANIFEST_KEYS, label))
    if errors:
        return errors

    if manifest["work_package_id"] != package_dir.name:
        errors.append(f"{label} work_package_id must equal directory name")

    outcome_path = repo_path(manifest["outcome_contract"])
    build_path = repo_path(manifest["build_contract"])
    if not outcome_path.exists():
        errors.append(f"{label} outcome_contract missing: {manifest['outcome_contract']}")
    if not build_path.exists():
        errors.append(f"{label} build_contract missing: {manifest['build_contract']}")
    if not outcome_path.exists() or not build_path.exists():
        return errors

    outcome = load_json(outcome_path)
    build = load_json(build_path)
    errors.extend(require_keys(outcome, REQUIRED_OUTCOME_KEYS, display_path(outcome_path)))
    errors.extend(require_keys(build, REQUIRED_BUILD_KEYS, display_path(build_path)))

    for artifact_name, data in {"outcome": outcome, "build": build}.items():
        if data.get("work_package_id") != manifest["work_package_id"]:
            errors.append(f"{artifact_name} contract work_package_id does not match manifest")

    outcome_ac = {criterion.get("id") for criterion in outcome.get("acceptance_criteria", [])}
    for criterion_id in manifest.get("acceptance_criteria", []):
        if criterion_id not in outcome_ac:
            errors.append(f"manifest acceptance criterion not present in outcome contract: {criterion_id}")

    for reference in outcome.get("prd", {}).values():
        if isinstance(reference, str) and reference.endswith(".md") and not repo_path(reference).exists():
            errors.append(f"outcome PRD reference does not exist: {reference}")
    for reference in build.get("architecture_refs", []):
        if not repo_path(reference).exists():
            errors.append(f"build architecture reference does not exist: {reference}")

    errors.extend(validate_state(package_dir, manifest))
    errors.extend(validate_ledger(package_dir))
    errors.extend(validate_evidence(package_dir, manifest, outcome))
    return errors


def validate_state(package_dir: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    path = state_path(package_dir)
    if not path.exists():
        return [f"missing state file: {display_path(path)}"]
    state = load_json(path)
    label = display_path(path)
    if state.get("schema_version") != 1:
        errors.append(f"{label} schema_version must be 1")
    if state.get("work_package_id") != manifest["work_package_id"]:
        errors.append(f"{label} work_package_id does not match manifest")
    if state.get("state") not in STATES:
        errors.append(f"{label} has invalid state: {state.get('state')}")
    expected_digests = contract_digests(manifest)
    if state.get("contract_digests") != expected_digests:
        errors.append(f"{label} contract_digests are stale")
    return errors


def validate_evidence(package_dir: Path, manifest: dict[str, Any], outcome: dict[str, Any]) -> list[str]:
    path = package_dir / "evidence" / "manifest.json"
    if not path.exists():
        return []
    errors: list[str] = []
    evidence = load_json(path)
    claims = evidence.get("claims", [])
    claimed_ids = {claim.get("acceptance_id") for claim in claims if isinstance(claim, dict)}
    blocking_ids = {
        criterion.get("id")
        for criterion in outcome.get("acceptance_criteria", [])
        if criterion.get("criticality") == "blocking"
    }
    for criterion_id in sorted(blocking_ids - claimed_ids):
        errors.append(f"evidence missing blocking acceptance criterion: {criterion_id}")
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("evidence claim must be an object")
            continue
        artifact = claim.get("artifact")
        if artifact and not (package_dir / artifact).exists():
            errors.append(f"evidence artifact does not exist: {artifact}")
    if evidence.get("work_package_id") != manifest["work_package_id"]:
        errors.append("evidence manifest work_package_id does not match manifest")
    return errors


def ensure_transition(previous: str, next_state: str) -> None:
    if previous not in STATES:
        raise FactoryError(f"invalid current state: {previous}")
    if next_state not in STATES:
        raise FactoryError(f"invalid target state: {next_state}")
    if previous == next_state:
        return
    if next_state not in TRANSITIONS.get(previous, set()):
        raise FactoryError(f"illegal transition: {previous} -> {next_state}")


def update_state(
    package_dir: Path,
    *,
    next_state: str,
    actor: str,
    role: str,
    reason: str,
    idempotency_key: str | None,
    event_type: str,
    data: dict[str, Any] | None = None,
    artifacts: dict[str, str] | None = None,
) -> dict[str, Any]:
    state = load_state(package_dir)
    manifest = load_manifest(package_dir)
    previous_state = state["state"]
    input_hash = command_input_hash(
        event_type,
        {
            "work_package_id": manifest["work_package_id"],
            "next_state": next_state,
            "actor": actor,
            "role": role,
            "reason": reason,
            "data": data or {},
            "artifacts": artifacts or {},
        },
    )
    existing = find_idempotent_event(package_dir, idempotency_key, input_hash)
    if existing:
        return existing
    ensure_transition(previous_state, next_state)
    event = append_event(
        package_dir,
        work_package_id=manifest["work_package_id"],
        actor=actor,
        role=role,
        event_type=event_type,
        previous_state=previous_state,
        next_state=next_state,
        reason=reason,
        idempotency_key=idempotency_key,
        input_hash=input_hash,
        artifacts=artifacts,
        data=data,
    )
    state["previous_state"] = previous_state
    state["state"] = next_state
    state["updated_at"] = event["timestamp"]
    state["ledger_tail_hash"] = event["event_hash"]
    state["contract_digests"] = contract_digests(manifest)
    state["next_action"] = next_action(next_state)
    if data:
        if "claim" in data:
            state["claim"] = data["claim"]
        if "git" in data:
            state.setdefault("git", {}).update(data["git"])
        if "blockers" in data:
            state["blockers"] = data["blockers"]
    write_json_atomic(state_path(package_dir), state)
    return event


def next_action(state: str) -> str:
    actions = {
        "candidate": "Shape the outcome and build contract.",
        "shaping": "Finish contracts and submit Gate 1.",
        "awaiting_gate_1": "Collect authenticated Gate 1 approval or modification.",
        "approved": "Create a detailed task plan.",
        "planning": "Finish the bounded implementation plan.",
        "ready": "Claim the package in an isolated worktree.",
        "claimed": "Start implementation or release the claim.",
        "implementing": "Complete author implementation and checks.",
        "self_checked": "Open or update the draft PR for the exact head SHA.",
        "draft_pr_open": "Record CI for the frozen PR head.",
        "ci_pending": "Wait for required CI, then start independent verification.",
        "verifying": "Complete independent verification.",
        "remediation": "Fix verifier findings inside the approved contract.",
        "verified": "Prepare Gate 2 packet.",
        "awaiting_gate_2": "Collect product and technical Gate 2 approval.",
        "approved_to_merge": "Merge only if head, candidate tree, checks, and approvals still match.",
        "merged": "Record deploy or close as non-runtime work.",
        "deployed": "Start canary observation.",
        "observing": "Close after observation policy passes.",
        "closed": "No pending action.",
    }
    return actions.get(state, "Resolve this state according to policy.")


def gate_policy(project_data: dict[str, Any], risk: str, gate: int) -> list[str]:
    policy = project_data.get("gate_policy", {})
    risk_policy = policy.get(risk) or policy.get("default") or {}
    return risk_policy.get(f"gate_{gate}_approver_roles", [])


def markdown_bullets(items: list[Any], fallback: str = "None.") -> list[str]:
    if not items:
        return [fallback]
    return [f"- `{item}`" if isinstance(item, str) and "/" in item else f"- {item}" for item in items]


def command_by_id(project_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {command["id"]: command for command in project_data.get("commands", [])}


def gate_pr_title(project_data: dict[str, Any], package_dir: Path, gate: int) -> str:
    manifest = load_manifest(package_dir)
    prefix = "Contract approval" if gate == 1 else "Implementation approval"
    return f"Gate {gate}: {prefix} for {manifest['work_package_id']} - {manifest['title']}"


def acceptance_criteria_markdown(outcome: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for criterion in outcome.get("acceptance_criteria", []):
        lines.append(
            f"- **{criterion.get('id')}** "
            f"({criterion.get('criticality')}; oracle: `{criterion.get('oracle')}`): "
            f"{criterion.get('statement')}"
        )
        evidence = criterion.get("evidence_required", [])
        if evidence:
            lines.append(f"  Evidence expected: {', '.join(f'`{item}`' for item in evidence)}")
    return lines or ["No acceptance criteria defined."]


def required_checks_markdown(project_data: dict[str, Any], build: dict[str, Any]) -> list[str]:
    commands = command_by_id(project_data)
    lines: list[str] = []
    for check_id in build.get("required_checks", []):
        command = commands.get(check_id, {})
        description = command.get("description", "configured project check")
        command_text = command.get("command")
        lines.append(f"- **{check_id}**: {description}")
        if command_text:
            lines.append(f"  Command: `{command_text}`")
    return lines or ["No required checks configured."]


def gate_pr_body_markdown(project_data: dict[str, Any], package_dir: Path, gate: int) -> str:
    manifest = load_manifest(package_dir)
    state = load_state(package_dir)
    outcome_path = repo_path(manifest["outcome_contract"])
    build_path = repo_path(manifest["build_contract"])
    outcome = load_json(outcome_path)
    build = load_json(build_path)
    required_roles = gate_policy(project_data, manifest["risk"], gate)
    outcome_digest = sha256_file(outcome_path)
    build_digest = sha256_file(build_path)
    heading = "Gate 1 Contract Approval" if gate == 1 else "Gate 2 Implementation Approval"
    approval_meaning = (
        "Approving this PR authorizes agents to plan and implement this exact work package. "
        "It does not approve code or deployment."
        if gate == 1
        else "Approving this PR authorizes merge of the exact reviewed implementation, if required checks still pass."
    )
    lines = [
        f"# {heading}",
        "",
        f"**Work package:** `{manifest['work_package_id']}`",
        f"**Project:** `{project_data['project_slug']}`",
        f"**Title:** {manifest['title']}",
        f"**Current factory state:** `{state['state']}`",
        f"**Risk:** `{manifest['risk']}`",
        f"**Required independence:** `{manifest['independence']}`",
        f"**Required human approvers:** {', '.join(required_roles) if required_roles else 'none configured'}",
        "",
        "## What Approval Means",
        "",
        approval_meaning,
        "",
        "Approve only if the outcome, scope, tests, risk, and rollback below are acceptable.",
        "",
        "## Problem",
        "",
        outcome.get("problem", ""),
        "",
        "## Desired Outcome",
        "",
        outcome.get("desired_outcome", ""),
        "",
        "## Acceptance Criteria",
        "",
        *acceptance_criteria_markdown(outcome),
        "",
        "## Scope Boundaries",
        "",
        "**Allowed paths:**",
        "",
        *markdown_bullets(build.get("allowed_paths", [])),
        "",
        "**Forbidden paths:**",
        "",
        *markdown_bullets(build.get("forbidden_paths", [])),
        "",
        "## Non-Goals",
        "",
        *markdown_bullets(outcome.get("non_goals", [])),
        "",
        "## Required Checks",
        "",
        *required_checks_markdown(project_data, build),
        "",
        "## Security And Privacy Constraints",
        "",
        *markdown_bullets(build.get("security_privacy_constraints", [])),
        "",
        "## Rollout",
        "",
        build.get("rollout", ""),
        "",
        "## Rollback",
        "",
        build.get("rollback", ""),
        "",
        "## Optional OpenHands Review Prompt",
        "",
        "Comment this on the PR if you want an advisory agent review before human approval:",
        "",
        "```text",
        "@openhands Review this Gate contract for ambiguity, oversized scope, missing tests, risk misclassification, and rollback gaps. Do not implement code.",
        "```",
        "",
        "OpenHands feedback is advisory. Human approval is still the GitHub PR review.",
        "",
        "## Human Approval Checklist",
        "",
        "- [ ] Product owner agrees this is the right outcome.",
        "- [ ] Technical owner agrees the scope and tests are sufficient.",
        "- [ ] Risk and independence levels are acceptable.",
        "- [ ] Rollback is acceptable.",
        "- [ ] No blocking ambiguity remains.",
        "",
        "## Machine Record",
        "",
        "These files are for `factoryctl` validation and audit. Humans should not need to read them unless debugging the control plane.",
        "",
        f"- Outcome Contract: `{display_path(outcome_path)}`",
        f"- Outcome digest: `{outcome_digest}`",
        f"- Build Contract: `{display_path(build_path)}`",
        f"- Build digest: `{build_digest}`",
        f"- State: `{display_path(state_path(package_dir))}`",
        f"- Ledger: `{display_path(ledger_path(package_dir))}`",
        "",
        "## After This PR Is Approved And Merged",
        "",
        f"The factory recorder ingests the authenticated GitHub approval and advances `{manifest['work_package_id']}` to the next state.",
        "",
    ]
    return "\n".join(lines)


def gate_request_markdown(project_data: dict[str, Any], package_dir: Path, gate: int) -> str:
    manifest = load_manifest(package_dir)
    state = load_state(package_dir)
    outcome_path = repo_path(manifest["outcome_contract"])
    build_path = repo_path(manifest["build_contract"])
    required_roles = gate_policy(project_data, manifest["risk"], gate)
    lines = [
        f"# Gate {gate} Request: {manifest['work_package_id']}",
        "",
        f"- Project: {project_data['project_slug']}",
        f"- Title: {manifest['title']}",
        f"- Current state: {state['state']}",
        f"- Risk: {manifest['risk']}",
        f"- Independence: {manifest['independence']}",
        f"- Outcome contract: `{display_path(outcome_path)}`",
        f"- Outcome digest: `{sha256_file(outcome_path)}`",
        f"- Build contract: `{display_path(build_path)}`",
        f"- Build digest: `{sha256_file(build_path)}`",
        f"- Required approver roles: {', '.join(required_roles) if required_roles else 'none configured'}",
        "",
        "## Decision Options",
        "",
        "- `approve`: advance the package.",
        "- `modify`: return the package to shaping or remediation.",
        "- `reject`: stop this package.",
        "- `defer`: pause before approval.",
        "",
        "## Operator Instruction",
        "",
        "Open a GitHub Contract PR using the generated PR body. After approval and merge, ingest the authenticated source event with:",
        "",
        f"```bash\npython3 software-factory/cli/factoryctl.py ingest-gate {manifest['work_package_id']} --gate {gate} --source-event <github-source-event.json> --actor <factory-recorder>\n```",
        "",
    ]
    return "\n".join(lines)


def command_doctor(args: argparse.Namespace) -> int:
    errors: list[str] = []
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            errors.append("not inside a Git repository")
    except OSError as exc:
        errors.append(f"git unavailable: {exc}")

    for project_data in iter_project_configs(args.project):
        errors.extend(validate_project(project_data))
    if not iter_project_configs(args.project):
        errors.append("no project adapters found")

    print(f"factoryctl {VERSION}")
    print(f"repo: {REPO_ROOT}")
    print(f"factory: {FACTORY_ROOT}")
    print(f"projects: {len(iter_project_configs(args.project))}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("status: ok")
    return 0


def command_inventory(args: argparse.Namespace) -> int:
    rows = []
    for project_data, package_dir in iter_work_packages(args.project):
        manifest = load_manifest(package_dir)
        state = load_state(package_dir) if state_path(package_dir).exists() else {"state": "missing-state"}
        rows.append(
            {
                "project": project_data["project_slug"],
                "work_package_id": manifest["work_package_id"],
                "prd_id": manifest["prd_id"],
                "title": manifest["title"],
                "state": state.get("state"),
                "risk": manifest["risk"],
                "independence": manifest["independence"],
                "path": display_path(package_dir),
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("No work packages found.")
        return 0
    widths = {
        "project": max(len("project"), *(len(row["project"]) for row in rows)),
        "wp": max(len("work_package"), *(len(row["work_package_id"]) for row in rows)),
        "state": max(len("state"), *(len(str(row["state"])) for row in rows)),
        "risk": max(len("risk"), *(len(row["risk"]) for row in rows)),
    }
    print(f"{'project':{widths['project']}}  {'work_package':{widths['wp']}}  {'state':{widths['state']}}  {'risk':{widths['risk']}}  title")
    for row in rows:
        print(
            f"{row['project']:{widths['project']}}  "
            f"{row['work_package_id']:{widths['wp']}}  "
            f"{str(row['state']):{widths['state']}}  "
            f"{row['risk']:{widths['risk']}}  "
            f"{row['title']}"
        )
    return 0


def command_validate(args: argparse.Namespace) -> int:
    errors: list[str] = []
    checked = 0
    if args.work_package:
        project_data, package_dir = find_work_package(args.work_package, args.project)
        errors.extend(validate_project(project_data))
        errors.extend(validate_package(project_data, package_dir))
        checked = 1
    else:
        for project_data in iter_project_configs(args.project):
            errors.extend(validate_project(project_data))
            for _, package_dir in iter_work_packages(project_data["project_slug"]):
                errors.extend(validate_package(project_data, package_dir))
                checked += 1

    result = {"checked_packages": checked, "errors": errors, "ok": not errors}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"checked packages: {checked}")
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
        else:
            print("validation: ok")
    return 1 if errors else 0


def command_status(args: argparse.Namespace) -> int:
    project_data, package_dir = find_work_package(args.work_package, args.project)
    manifest = load_manifest(package_dir)
    state = load_state(package_dir)
    output = {
        "project": project_data["project_slug"],
        "manifest": {
            "work_package_id": manifest["work_package_id"],
            "title": manifest["title"],
            "risk": manifest["risk"],
            "independence": manifest["independence"],
        },
        "state": state,
        "ledger_tail_hash": ledger_tail_hash(package_dir),
        "package_path": display_path(package_dir),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def command_transition(args: argparse.Namespace) -> int:
    _, package_dir = find_work_package(args.work_package, args.project)
    artifacts: dict[str, str] = {}
    if args.evidence:
        evidence_path = repo_path(args.evidence)
        if not evidence_path.exists():
            raise FactoryError(f"evidence path does not exist: {args.evidence}")
        artifacts[display_path(evidence_path)] = sha256_file(evidence_path)
    event = update_state(
        package_dir,
        next_state=args.to,
        actor=args.actor,
        role=args.role,
        reason=args.reason,
        idempotency_key=args.idempotency_key,
        event_type="transition",
        artifacts=artifacts,
    )
    print(json.dumps({"event_id": event["event_id"], "event_hash": event["event_hash"]}, indent=2, sort_keys=True))
    return 0


def command_claim(args: argparse.Namespace) -> int:
    _, package_dir = find_work_package(args.work_package, args.project)
    state = load_state(package_dir)
    if state.get("state") != "ready":
        raise FactoryError(f"cannot claim from state {state.get('state')}; expected ready")
    lease_expires_at = now_plus(parse_duration(args.lease))
    claim = {
        "owner": args.actor,
        "claimed_at": utc_now(),
        "lease_expires_at": lease_expires_at,
        "branch": args.branch or f"factory/{args.work_package}",
        "worktree": args.worktree or f"../{args.work_package}",
    }
    event = update_state(
        package_dir,
        next_state="claimed",
        actor=args.actor,
        role=args.role,
        reason=args.reason,
        idempotency_key=args.idempotency_key,
        event_type="claim",
        data={"claim": claim},
    )
    print(json.dumps({"claim": claim, "event_hash": event["event_hash"]}, indent=2, sort_keys=True))
    return 0


def command_release(args: argparse.Namespace) -> int:
    _, package_dir = find_work_package(args.work_package, args.project)
    state = load_state(package_dir)
    claim = state.get("claim") or {}
    if state.get("state") != "claimed":
        raise FactoryError(f"cannot release from state {state.get('state')}; expected claimed")
    if claim.get("owner") != args.actor:
        raise FactoryError(f"claim is owned by {claim.get('owner')}; {args.actor} cannot release it")
    event = update_state(
        package_dir,
        next_state="ready",
        actor=args.actor,
        role=args.role,
        reason=args.reason,
        idempotency_key=args.idempotency_key,
        event_type="release",
        data={"claim": None},
    )
    state = load_state(package_dir)
    state.pop("claim", None)
    write_json_atomic(state_path(package_dir), state)
    print(json.dumps({"event_id": event["event_id"], "event_hash": event["event_hash"]}, indent=2, sort_keys=True))
    return 0


def command_submit_gate(args: argparse.Namespace) -> int:
    project_data, package_dir = find_work_package(args.work_package, args.project)
    request_path = package_dir / "gates" / f"gate-{args.gate}-request.md"
    pr_body_path = package_dir / "gates" / f"gate-{args.gate}-github-pr-body.md"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(gate_request_markdown(project_data, package_dir, args.gate), encoding="utf-8")
    pr_body_path.write_text(gate_pr_body_markdown(project_data, package_dir, args.gate), encoding="utf-8")
    manifest = load_manifest(package_dir)
    title = gate_pr_title(project_data, package_dir, args.gate)
    input_hash = command_input_hash(
        "submit-gate",
        {
            "work_package_id": args.work_package,
            "gate": args.gate,
            "request_path": display_path(request_path),
            "pr_body_path": display_path(pr_body_path),
            "title": title,
        },
    )
    artifacts = {
        display_path(request_path): sha256_file(request_path),
        display_path(pr_body_path): sha256_file(pr_body_path),
    }
    event = append_event(
        package_dir,
        work_package_id=manifest["work_package_id"],
        actor=args.actor,
        role=args.role,
        event_type="gate_request",
        previous_state=load_state(package_dir)["state"],
        next_state=load_state(package_dir)["state"],
        reason=f"submitted Gate {args.gate} request",
        idempotency_key=args.idempotency_key,
        input_hash=input_hash,
        artifacts=artifacts,
        data={"github_pr_title": title, "github_pr_body": display_path(pr_body_path)},
    )
    state = load_state(package_dir)
    state["updated_at"] = event["timestamp"]
    state["ledger_tail_hash"] = event["event_hash"]
    state.setdefault("gate_requests", {})[str(args.gate)] = {
        "title": title,
        "request": display_path(request_path),
        "github_pr_body": display_path(pr_body_path),
        "submitted_at": event["timestamp"],
    }
    write_json_atomic(state_path(package_dir), state)
    print(
        json.dumps(
            {
                "request": display_path(request_path),
                "github_pr_body": display_path(pr_body_path),
                "github_pr_title": title,
                "event_hash": event["event_hash"],
                "suggested_command": (
                    f"gh pr create --title {json.dumps(title)} "
                    f"--body-file {display_path(pr_body_path)}"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def command_ingest_gate(args: argparse.Namespace) -> int:
    project_data, package_dir = find_work_package(args.work_package, args.project)
    manifest = load_manifest(package_dir)
    source_path = repo_path(args.source_event)
    if not source_path.exists():
        raise FactoryError("MVP ingest supports source-event JSON paths only")
    source = load_json(source_path)
    decision = source.get("decision")
    if source.get("gate") != args.gate:
        raise FactoryError("source gate does not match --gate")
    if source.get("work_package_id") != args.work_package:
        raise FactoryError("source work_package_id does not match")
    if decision not in {"approve", "modify", "reject", "defer"}:
        raise FactoryError("gate decision must be approve, modify, reject, or defer")
    approvers = source.get("approvers", [])
    approver_roles = {approver.get("role") for approver in approvers if isinstance(approver, dict)}
    required_roles = set(gate_policy(project_data, manifest["risk"], args.gate))
    if decision == "approve" and not required_roles.issubset(approver_roles):
        missing = ", ".join(sorted(required_roles - approver_roles))
        raise FactoryError(f"approval missing required approver roles: {missing}")

    current_state = load_state(package_dir)["state"]
    if args.gate == 1:
        if current_state != "awaiting_gate_1":
            raise FactoryError(f"Gate 1 can be ingested only from awaiting_gate_1, got {current_state}")
        next_by_decision = {"approve": "approved", "modify": "shaping", "reject": "rejected", "defer": "deferred"}
    else:
        if current_state != "awaiting_gate_2":
            raise FactoryError(f"Gate 2 can be ingested only from awaiting_gate_2, got {current_state}")
        next_by_decision = {"approve": "approved_to_merge", "modify": "remediation", "reject": "rejected", "defer": "blocked"}

    receipt = {
        "schema_version": 1,
        "gate": args.gate,
        "work_package_id": args.work_package,
        "decision": decision,
        "recorded_at": utc_now(),
        "recorded_by": actor_identity(args.actor, args.role),
        "source": source,
        "source_sha256": sha256_file(source_path),
        "contract_digests": contract_digests(manifest),
        "ledger_tail_before": ledger_tail_hash(package_dir),
        "authority_mode": source.get("authority_mode", "bootstrap-local-unverified"),
    }
    receipt_path = package_dir / "gates" / f"gate-{args.gate}-receipt.json"
    write_json_atomic(receipt_path, receipt)
    artifacts = {
        display_path(source_path): sha256_file(source_path),
        display_path(receipt_path): sha256_file(receipt_path),
    }
    event = update_state(
        package_dir,
        next_state=next_by_decision[decision],
        actor=args.actor,
        role=args.role,
        reason=source.get("rationale") or f"Gate {args.gate} decision: {decision}",
        idempotency_key=args.idempotency_key,
        event_type=f"gate_{args.gate}_decision",
        artifacts=artifacts,
        data={"decision": decision, "authority_mode": receipt["authority_mode"]},
    )
    receipt["ledger_tail_after"] = event["event_hash"]
    write_json_atomic(receipt_path, receipt)
    print(json.dumps({"receipt": display_path(receipt_path), "event_hash": event["event_hash"]}, indent=2, sort_keys=True))
    return 0


def command_record_verdict(args: argparse.Namespace) -> int:
    _, package_dir = find_work_package(args.work_package, args.project)
    report_path = repo_path(args.report)
    report = load_json(report_path)
    if report.get("work_package_id") != args.work_package:
        raise FactoryError("verification report work_package_id does not match")
    state = load_state(package_dir)
    claim_owner = (state.get("claim") or {}).get("owner")
    verifier_id = report.get("verifier", {}).get("id")
    if claim_owner and verifier_id == claim_owner:
        raise FactoryError("verifier identity must differ from claim owner")
    recommendation = report.get("recommendation")
    if recommendation == "APPROVE":
        next_state_value = "verified"
    elif recommendation in {"COMMENT", "REQUEST_CHANGES"}:
        next_state_value = "remediation"
    else:
        raise FactoryError("verification recommendation must be APPROVE, COMMENT, or REQUEST_CHANGES")
    event = update_state(
        package_dir,
        next_state=next_state_value,
        actor=args.actor,
        role=args.role,
        reason=f"recorded verification verdict: {recommendation}",
        idempotency_key=args.idempotency_key,
        event_type="verification_verdict",
        artifacts={display_path(report_path): sha256_file(report_path)},
        data={"recommendation": recommendation},
    )
    print(json.dumps({"event_id": event["event_id"], "event_hash": event["event_hash"]}, indent=2, sort_keys=True))
    return 0


def command_select_next(args: argparse.Namespace) -> int:
    candidates = []
    rank_by_state = {"awaiting_gate_1": 0, "candidate": 1, "shaping": 2, "approved": 3, "ready": 4}
    rank_by_risk = {"R3": 0, "R2": 1, "R1": 2, "R0": 3}
    for project_data, package_dir in iter_work_packages(args.project):
        manifest = load_manifest(package_dir)
        state = load_state(package_dir) if state_path(package_dir).exists() else {"state": "missing-state"}
        if state.get("state") in {"closed", "rejected", "cancelled", "superseded"}:
            continue
        if state.get("claim"):
            continue
        candidates.append(
            (
                rank_by_state.get(state.get("state"), 99),
                rank_by_risk.get(manifest.get("risk"), 99),
                manifest["work_package_id"],
                {
                    "project": project_data["project_slug"],
                    "work_package_id": manifest["work_package_id"],
                    "title": manifest["title"],
                    "state": state.get("state"),
                    "risk": manifest["risk"],
                    "next_action": state.get("next_action"),
                    "path": display_path(package_dir),
                },
            )
        )
    candidates.sort(key=lambda row: row[:3])
    result = {"shadow": args.shadow, "recommendation": candidates[0][3] if candidates else None}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_generate_boards(args: argparse.Namespace) -> int:
    written = []
    for project_data in iter_project_configs(args.project):
        rows_by_board: dict[str, list[dict[str, Any]]] = {board: [] for board in BOARD_BUCKETS}
        for _, package_dir in iter_work_packages(project_data["project_slug"]):
            manifest = load_manifest(package_dir)
            state = load_state(package_dir) if state_path(package_dir).exists() else {"state": "missing-state"}
            board = next(
                (name for name, states in BOARD_BUCKETS.items() if state.get("state") in states),
                "backlog",
            )
            rows_by_board[board].append({"manifest": manifest, "state": state, "path": package_dir})
        board_dir = project_data["_path"].parent / "control" / "boards"
        board_dir.mkdir(parents=True, exist_ok=True)
        for board, rows in rows_by_board.items():
            lines = [f"# Factory {board.replace('-', ' ').title()}", ""]
            if not rows:
                lines.append("_No work packages._")
            for row in sorted(rows, key=lambda item: item["manifest"]["work_package_id"]):
                manifest = row["manifest"]
                state = row["state"]
                lines.extend(
                    [
                        f"## {manifest['work_package_id']} - {manifest['title']}",
                        "",
                        f"- State: `{state.get('state')}`",
                        f"- Risk: `{manifest['risk']}`",
                        f"- Independence: `{manifest['independence']}`",
                        f"- Path: `{display_path(row['path'])}`",
                        f"- Next action: {state.get('next_action', '')}",
                        "",
                    ]
                )
            output_path = board_dir / f"{board}.md"
            output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            written.append(display_path(output_path))
    print(json.dumps({"written": written}, indent=2, sort_keys=True))
    return 0


def command_digest(args: argparse.Namespace) -> int:
    path = repo_path(args.path)
    if not path.exists():
        raise FactoryError(f"path does not exist: {args.path}")
    print(json.dumps({"path": display_path(path), "sha256": sha256_file(path)}, indent=2, sort_keys=True))
    return 0


def command_create(args: argparse.Namespace) -> int:
    project_data = project_config(args.project)
    package_dir = package_root(project_data) / args.prd / args.work_package
    if package_dir.exists() and not args.force:
        raise FactoryError(f"work package already exists: {display_path(package_dir)}")
    package_dir.mkdir(parents=True, exist_ok=True)
    title = args.title or args.work_package
    manifest = {
        "schema_version": 1,
        "work_package_id": args.work_package,
        "prd_id": args.prd,
        "title": title,
        "contract_revision": 1,
        "outcome_contract": display_path(package_dir / "outcome-contract.json"),
        "build_contract": display_path(package_dir / "build-contract.json"),
        "risk": args.risk,
        "independence": args.independence,
        "dependencies": [],
        "acceptance_criteria": ["AC-001"],
        "allowed_paths": [],
        "forbidden_paths": [],
        "max_remediation_cycles": 3,
    }
    outcome = {
        "schema_version": 1,
        "work_package_id": args.work_package,
        "prd": {"id": args.prd, "path": project_data["paths"].get("main_prd", "")},
        "problem": "TODO: describe the observable problem.",
        "desired_outcome": "TODO: describe the user-visible or operator-visible outcome.",
        "target_users": [],
        "journey_refs": [],
        "requirement_refs": [],
        "acceptance_criteria": [
            {
                "id": "AC-001",
                "statement": "TODO: define a falsifiable acceptance criterion.",
                "oracle": "manual-review",
                "evidence_required": ["review-note"],
                "criticality": "blocking",
            }
        ],
        "invariants": [],
        "non_goals": [],
        "success_metrics": [],
        "ambiguities": ["TODO: remove before Gate 1."],
        "failure_and_rollback_outcome": "TODO: define failure and rollback behavior.",
    }
    build = {
        "schema_version": 1,
        "work_package_id": args.work_package,
        "architecture_refs": project_data["paths"].get("architecture", []),
        "allowed_paths": [],
        "forbidden_paths": [],
        "interfaces_changed": [],
        "security_privacy_constraints": [],
        "migration": {"required": False, "strategy": "none", "rollback": "revert implementation"},
        "observability": [],
        "required_checks": [],
        "adversarial_scenarios": [],
        "rollout": "normal protected merge",
        "rollback": "revert implementation",
        "risk": {
            "level": args.risk,
            "reasons": [],
            "required_independence": args.independence,
            "required_approver_roles": gate_policy(project_data, args.risk, 1),
        },
        "budgets": {"max_remediation_cycles": 3, "max_scope_expansion": "none"},
    }
    write_json_atomic(package_dir / "manifest.json", manifest)
    write_json_atomic(package_dir / "outcome-contract.json", outcome)
    write_json_atomic(package_dir / "build-contract.json", build)
    state = {
        "schema_version": 1,
        "work_package_id": args.work_package,
        "state": "shaping",
        "previous_state": None,
        "updated_at": utc_now(),
        "contract_digests": contract_digests(manifest),
        "git": {},
        "claim": None,
        "attempt": 0,
        "next_action": next_action("shaping"),
        "blockers": ["Remove TODOs and blocking ambiguities before Gate 1."],
    }
    write_json_atomic(package_dir / "state.json", state)
    input_hash = command_input_hash("create", {"work_package_id": args.work_package, "prd": args.prd})
    append_event(
        package_dir,
        work_package_id=args.work_package,
        actor=args.actor,
        role=args.role,
        event_type="create",
        previous_state=None,
        next_state="shaping",
        reason="created work-package scaffold",
        idempotency_key=args.idempotency_key,
        input_hash=input_hash,
    )
    print(json.dumps({"created": display_path(package_dir)}, indent=2, sort_keys=True))
    return 0


def add_common_package_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("work_package")
    parser.add_argument("--project", default=None)


def add_actor_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--actor", default=os.environ.get("FACTORY_ACTOR", "local:operator"))
    parser.add_argument("--role", default=os.environ.get("FACTORY_ROLE", "operator"))
    parser.add_argument("--reason", default="operator command")
    parser.add_argument("--idempotency-key", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factoryctl", description="AI-native software factory control plane")
    parser.add_argument("--version", action="version", version=f"factoryctl {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="check factory installation")
    doctor.add_argument("--project", default=None)
    doctor.set_defaults(func=command_doctor)

    inventory = subparsers.add_parser("inventory", help="list project work packages")
    inventory.add_argument("--project", default=None)
    inventory.add_argument("--json", action="store_true")
    inventory.set_defaults(func=command_inventory)

    validate = subparsers.add_parser("validate", help="validate contracts, state, ledger, and evidence")
    validate.add_argument("work_package", nargs="?")
    validate.add_argument("--project", default=None)
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=command_validate)

    status = subparsers.add_parser("status", help="show current package state")
    add_common_package_args(status)
    status.set_defaults(func=command_status)

    transition = subparsers.add_parser("transition", help="apply a guarded state transition")
    add_common_package_args(transition)
    transition.add_argument("--to", required=True)
    transition.add_argument("--evidence")
    add_actor_args(transition)
    transition.set_defaults(func=command_transition)

    claim = subparsers.add_parser("claim", help="claim a ready work package")
    add_common_package_args(claim)
    claim.add_argument("--lease", default="4h")
    claim.add_argument("--branch")
    claim.add_argument("--worktree")
    add_actor_args(claim)
    claim.set_defaults(func=command_claim)

    release = subparsers.add_parser("release", help="release a claim back to ready")
    add_common_package_args(release)
    add_actor_args(release)
    release.set_defaults(func=command_release)

    submit_gate = subparsers.add_parser("submit-gate", help="write a gate request and GitHub PR body")
    add_common_package_args(submit_gate)
    submit_gate.add_argument("--gate", type=int, choices=[1, 2], required=True)
    add_actor_args(submit_gate)
    submit_gate.set_defaults(func=command_submit_gate)

    ingest_gate = subparsers.add_parser("ingest-gate", help="ingest a gate source event JSON")
    add_common_package_args(ingest_gate)
    ingest_gate.add_argument("--gate", type=int, choices=[1, 2], required=True)
    ingest_gate.add_argument("--source-event", required=True)
    add_actor_args(ingest_gate)
    ingest_gate.set_defaults(func=command_ingest_gate)

    verdict = subparsers.add_parser("record-verdict", help="record independent verification report")
    add_common_package_args(verdict)
    verdict.add_argument("report")
    add_actor_args(verdict)
    verdict.set_defaults(func=command_record_verdict)

    select_next = subparsers.add_parser("select-next", help="deterministically rank the next package")
    select_next.add_argument("--project", default=None)
    select_next.add_argument("--shadow", action="store_true")
    select_next.set_defaults(func=command_select_next)

    boards = subparsers.add_parser("generate-boards", help="render factory board markdown views")
    boards.add_argument("--project", default=None)
    boards.set_defaults(func=command_generate_boards)

    digest = subparsers.add_parser("digest", help="calculate a sha256 digest")
    digest.add_argument("path")
    digest.set_defaults(func=command_digest)

    create = subparsers.add_parser("create", help="create a work-package scaffold")
    create.add_argument("prd")
    create.add_argument("work_package")
    create.add_argument("--project", default="pkms")
    create.add_argument("--title")
    create.add_argument("--risk", default="R1")
    create.add_argument("--independence", default="I1")
    create.add_argument("--force", action="store_true")
    add_actor_args(create)
    create.set_defaults(func=command_create)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FactoryError as exc:
        print(f"factoryctl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
