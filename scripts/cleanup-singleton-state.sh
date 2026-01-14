#!/usr/bin/env bash
set -euo pipefail

# Script to remove singleton resources from Terraform state
# Run this for each environment BEFORE applying the fixed Terraform code

usage() {
  echo "Usage: $(basename "$0") <environment>"
  echo "Example: $(basename "$0") dev"
  echo ""
  echo "This script removes the problematic singleton resources from Terraform state"
  echo "The resources will remain in AWS but won't be managed by Terraform anymore"
  exit 1
}

if [ $# -ne 1 ]; then
  usage
fi

ENVIRONMENT="$1"

if ! [[ "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
  echo "ERROR: Environment must be dev, staging, or prod (got '$ENVIRONMENT')" >&2
  exit 1
fi

echo "=============================================="
echo "Removing Singleton Resources from $ENVIRONMENT State"
echo "=============================================="
echo ""

# Initialize with the correct backend
echo "==> Initializing backend for $ENVIRONMENT..."
terraform init -backend-config="backend.${ENVIRONMENT}.hcl" -reconfigure > /dev/null

echo ""
echo "==> Creating state backup..."
BACKUP_FILE="state-backup-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).json"
terraform state pull > "$BACKUP_FILE"
echo "    Backup saved to: $BACKUP_FILE"

echo ""
echo "==> Removing problematic resources from state..."
echo ""

# List of resources to remove
RESOURCES=(
  "module.lambdas.aws_api_gateway_account.account_settings"
  "module.lambdas.aws_iam_policy_attachment.api_gateway_logs_policy"
  "module.lambdas.aws_iam_role.api_gateway_cloudwatch_role"
  "module.lambdas.aws_cloudwatch_log_group.api_gateway_log_group"
)

REMOVED_COUNT=0
SKIPPED_COUNT=0

for resource in "${RESOURCES[@]}"; do
  echo -n "  Checking: $resource ... "
  
  # Check if resource exists in state
  if terraform state list | grep -q "^${resource}$"; then
    terraform state rm "$resource" > /dev/null 2>&1
    echo "✓ REMOVED"
    ((REMOVED_COUNT++))
  else
    echo "⊗ NOT FOUND (already removed or never existed)"
    ((SKIPPED_COUNT++))
  fi
done

echo ""
echo "=============================================="
echo "Summary:"
echo "  Environment:      $ENVIRONMENT"
echo "  Removed:          $REMOVED_COUNT resources"
echo "  Already removed:  $SKIPPED_COUNT resources"
echo "  Backup file:      $BACKUP_FILE"
echo "=============================================="
echo ""

if [ $REMOVED_COUNT -gt 0 ]; then
  echo "✅ State cleanup complete!"
  echo ""
  echo "Next steps:"
  echo "  1. Review the changes with: ../scripts/tf-env.sh $ENVIRONMENT plan"
  echo "  2. Apply the changes with:  ../scripts/tf-env.sh $ENVIRONMENT apply"
else
  echo "ℹ️  No resources were removed (already cleaned or migration already done)"
  echo ""
  echo "You can proceed with: ../scripts/tf-env.sh $ENVIRONMENT plan"
fi

echo ""

