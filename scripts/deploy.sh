#!/usr/bin/env bash
# Plan/apply the account-entry StackSet through its delegated administrator.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
: "${AWS_PROFILE:?Set AWS_PROFILE to the registered delegated administrator profile}"
: "${EXPECTED_AWS_ACCOUNT_ID:?Set EXPECTED_AWS_ACCOUNT_ID to that account ID}"
actual=$(aws sts get-caller-identity --query Account --output text)
if [[ "$actual" != "$EXPECTED_AWS_ACCOUNT_ID" ]]; then
  printf 'Wrong AWS account: expected %s, got %s\n' "$EXPECTED_AWS_ACCOUNT_ID" "$actual" >&2
  exit 1
fi
mkdir -p .local
case "${1:-plan}" in
  plan)
    terraform init -input=false -lockfile=readonly
    terraform validate
    terraform plan -input=false -out=.local/onboarding.tfplan
    ;;
  apply)
    [[ -f .local/onboarding.tfplan ]] || { echo 'Run the plan step first.' >&2; exit 1; }
    terraform apply -input=false .local/onboarding.tfplan
    python3 scripts/verify.py
    ;;
  *) echo 'Usage: scripts/deploy.sh [plan|apply]' >&2; exit 1 ;;
esac
