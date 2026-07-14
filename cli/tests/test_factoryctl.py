from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FACTORYCTL_PATH = REPO_ROOT / "software-factory" / "cli" / "factoryctl.py"


def load_factoryctl():
    spec = importlib.util.spec_from_file_location("factoryctl_under_test", FACTORYCTL_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FactoryCtlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_factoryctl()
        self.tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp.name) / "repo"
        self.factory_root = self.repo_root / "software-factory"
        shutil.copytree(REPO_ROOT / "software-factory", self.factory_root)
        for path in [
            "README.md",
            "AGENTS.md",
            "CLAUDE.md",
            "agent.md",
            "backend/ARCHITECTURE.md",
            "backend/CLAUDE.md",
            "product/01-csea-pkms-prd.md",
            "product/PRD-inventory.md",
            "product/open-questions.md",
            "product/user-journeys.md",
            "tasks/backlog.md",
        ]:
            target = self.repo_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# Fixture for {path}\n", encoding="utf-8")
        self.module.REPO_ROOT = self.repo_root
        self.module.FACTORY_ROOT = self.factory_root
        self.module.PROJECTS_ROOT = self.factory_root / "projects"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = self.module.main(list(args))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def package_dir(self) -> Path:
        return (
            self.factory_root
            / "projects"
            / "pkms"
            / "work-packages"
            / "PKMS-001"
            / "WP-PKMS-001-001"
        )

    def write_gate_source(self, roles: list[str]) -> Path:
        source = {
            "schema_version": 1,
            "gate": 1,
            "work_package_id": "WP-PKMS-001-001",
            "decision": "approve",
            "authority_mode": "test-local",
            "approvers": [
                {"actor": f"human:{role}", "role": role, "source": "unit-test"} for role in roles
            ],
            "rationale": "unit test approval",
        }
        source_path = self.package_dir() / "gates" / "test-gate-source.json"
        source_path.write_text(json.dumps(source), encoding="utf-8")
        return source_path

    def test_validate_seed_package(self) -> None:
        exit_code, stdout, stderr = self.run_cli("validate", "--json")
        self.assertEqual(exit_code, 0, stderr)
        result = json.loads(stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["checked_packages"], 1)

    def test_illegal_transition_fails(self) -> None:
        exit_code, _stdout, stderr = self.run_cli(
            "transition",
            "WP-PKMS-001-001",
            "--project",
            "pkms",
            "--to",
            "claimed",
            "--actor",
            "codex:test",
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("illegal transition", stderr)

    def test_submit_gate_updates_ledger_tail(self) -> None:
        exit_code, _stdout, stderr = self.run_cli(
            "submit-gate",
            "WP-PKMS-001-001",
            "--project",
            "pkms",
            "--gate",
            "1",
            "--actor",
            "codex:test",
        )
        self.assertEqual(exit_code, 0, stderr)
        state = json.loads((self.package_dir() / "state.json").read_text(encoding="utf-8"))
        ledger_events = [
            json.loads(line)
            for line in (self.package_dir() / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(state["ledger_tail_hash"], ledger_events[-1]["event_hash"])

    def test_submit_gate_writes_github_pr_body(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            "submit-gate",
            "WP-PKMS-001-001",
            "--project",
            "pkms",
            "--gate",
            "1",
            "--actor",
            "codex:test",
        )
        self.assertEqual(exit_code, 0, stderr)
        result = json.loads(stdout)
        self.assertIn("github_pr_body", result)
        self.assertIn("gh pr create", result["suggested_command"])
        body = (self.repo_root / result["github_pr_body"]).read_text(encoding="utf-8")
        self.assertIn("# Gate 1 Contract Approval", body)
        self.assertIn("## Problem", body)
        self.assertIn("## Desired Outcome", body)
        self.assertIn("## Acceptance Criteria", body)
        self.assertIn("@openhands Review this Gate contract", body)
        self.assertIn("Humans should not need to read them", body)

    def test_gate_approval_requires_all_roles(self) -> None:
        source_path = self.write_gate_source(["product-owner"])
        exit_code, _stdout, stderr = self.run_cli(
            "ingest-gate",
            "WP-PKMS-001-001",
            "--project",
            "pkms",
            "--gate",
            "1",
            "--source-event",
            str(source_path),
            "--actor",
            "codex:test",
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("missing required approver roles", stderr)

    def test_gate_approval_advances_to_approved(self) -> None:
        source_path = self.write_gate_source(["product-owner", "technical-owner"])
        exit_code, stdout, stderr = self.run_cli(
            "ingest-gate",
            "WP-PKMS-001-001",
            "--project",
            "pkms",
            "--gate",
            "1",
            "--source-event",
            str(source_path),
            "--actor",
            "codex:test",
        )
        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("gate-1-receipt.json", stdout)
        state = json.loads((self.package_dir() / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "approved")


if __name__ == "__main__":
    unittest.main()
