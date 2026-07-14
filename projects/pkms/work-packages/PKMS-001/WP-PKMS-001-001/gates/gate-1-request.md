# Gate 1 Request: WP-PKMS-001-001

- Project: pkms
- Title: Converge service-layer tenant resolution with ABAC guard
- Current state: awaiting_gate_1
- Risk: R2
- Independence: I2
- Outcome contract: `software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/outcome-contract.json`
- Outcome digest: `sha256:7b487bc1cee82b8dcb167baacb75c56ec48127bbcf8fb99886618a658cf89923`
- Build contract: `software-factory/projects/pkms/work-packages/PKMS-001/WP-PKMS-001-001/build-contract.json`
- Build digest: `sha256:d964d21848f24fc67c2fe7eccbe136d1e38b696123eca074e3211dc247e0e013`
- Required approver roles: product-owner, technical-owner

## Decision Options

- `approve`: advance the package.
- `modify`: return the package to shaping or remediation.
- `reject`: stop this package.
- `defer`: pause before approval.

## Operator Instruction

Open a GitHub Contract PR using the generated PR body. After approval and merge, ingest the authenticated source event with:

```bash
python3 software-factory/cli/factoryctl.py ingest-gate WP-PKMS-001-001 --gate 1 --source-event <github-source-event.json> --actor <factory-recorder>
```
