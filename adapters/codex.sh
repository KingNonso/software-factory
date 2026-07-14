#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <station-prompt.md> <work-package-id> [extra codex args...]" >&2
  exit 2
fi

prompt_path="$1"
work_package_id="$2"
shift 2

if [[ ! -f "$prompt_path" ]]; then
  echo "missing prompt: $prompt_path" >&2
  exit 2
fi

echo "Codex adapter prepared for ${work_package_id}."
echo "Prompt: ${prompt_path}"
echo "Run Codex with this prompt and submit structured output back through factoryctl."
echo "Extra args: $*"
