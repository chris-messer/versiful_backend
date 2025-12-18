#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <env> <terraform args...>"
  echo "Example: $(basename "$0") dev plan"
  exit 1
}

if [ $# -lt 2 ]; then
  usage
fi

ENVIRONMENT="$1"; shift

if ! [[ "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
  echo "ENVIRONMENT must be dev|staging|prod (got '$ENVIRONMENT')" >&2
  exit 1
fi

BACKEND_FILE="backend.${ENVIRONMENT}.hcl"
TFVARS_FILE="${ENVIRONMENT}.tfvars"

if [ ! -f "$BACKEND_FILE" ]; then
  echo "Missing backend config: $BACKEND_FILE" >&2
  exit 1
fi

if [ ! -f "$TFVARS_FILE" ]; then
  echo "Missing tfvars file: $TFVARS_FILE" >&2
  exit 1
fi

echo "==> Initializing backend with $BACKEND_FILE"
terraform init -backend-config="$BACKEND_FILE" -reconfigure >/dev/null

echo "==> Running: terraform $* -var-file=$TFVARS_FILE"
terraform "$@" -var-file="$TFVARS_FILE"

