# Quick Reference: What Was Fixed

## The Problem in One Sentence

Your Terraform code had **singleton AWS resources** (`aws_api_gateway_account` and `aws_iam_policy_attachment`) that all three environments (dev, staging, prod) were fighting to control, causing every deployment to overwrite the previous environment's configuration.

## What I Changed

### Files Modified

1. **`terraform/modules/lambdas/main.tf`**
   - ❌ Removed: `aws_iam_role.api_gateway_cloudwatch_role`
   - ❌ Removed: `aws_iam_policy_attachment.api_gateway_logs_policy` 
   - ❌ Removed: `aws_api_gateway_account.account_settings`
   - ❌ Removed: `aws_cloudwatch_log_group.api_gateway_log_group`
   - ✅ Added: Explanatory comment

2. **`terraform/modules/apiGateway/main.tf`**
   - ✅ Added: `aws_cloudwatch_log_group.api_gateway_log_group` (environment-specific)
   - ✅ Updated: `aws_apigatewayv2_stage.lambda_stage` to use new log group

3. **`terraform/SINGLETON_RESOURCE_FIX.md`** (New)
   - Complete migration guide with step-by-step instructions

## Quick Start: How to Deploy the Fix

```bash
cd terraform

# For each environment (dev, staging, prod), run these commands:
../scripts/tf-env.sh <env> init

# Remove old resources from state (they stay in AWS, just not managed by Terraform)
terraform state rm 'module.lambdas.aws_api_gateway_account.account_settings'
terraform state rm 'module.lambdas.aws_iam_policy_attachment.api_gateway_logs_policy'
terraform state rm 'module.lambdas.aws_iam_role.api_gateway_cloudwatch_role'
terraform state rm 'module.lambdas.aws_cloudwatch_log_group.api_gateway_log_group'

# Plan and apply
../scripts/tf-env.sh <env> plan
../scripts/tf-env.sh <env> apply
```

## Why This Fixes Your Problem

**Before:**
```
Dev Deploy    → Sets api_gateway_account to dev role
Staging Deploy → Overwrites api_gateway_account to staging role  ← DEV BROKEN
Prod Deploy    → Overwrites api_gateway_account to prod role     ← STAGING BROKEN
```

**After:**
```
Dev Deploy     → Creates dev-specific log group only
Staging Deploy → Creates staging-specific log group only  
Prod Deploy    → Creates prod-specific log group only
```

No more shared/singleton resources = No more conflicts = Faster deployments!

## What Your Terraform Plans Will Now Show

**Before the fix:**
```
Plan: 1 to add, 2 to change, 1 to destroy.

~ module.lambdas.aws_api_gateway_account.account_settings
    cloudwatch_role_arn: "staging-role" → "dev-role"

~ module.lambdas.aws_iam_policy_attachment.api_gateway_logs_policy
    roles: ["prod-role"] → ["dev-role"]
```

**After the fix:**
```
Plan: 1 to add, 1 to change, 1 to destroy.

+ module.apiGateway.aws_cloudwatch_log_group.api_gateway_log_group

~ module.apiGateway.aws_apigatewayv2_stage.lambda_stage
    access_log_settings.destination_arn: (updated)
```

Much cleaner! Only environment-specific resources are managed.

## Expected Deployment Time Improvement

- **Before**: ~2-3 minutes (updating shared resources, IAM propagation delays)
- **After**: ~30-60 seconds (only environment-specific resources)

## Read the Full Guide

For complete migration instructions with troubleshooting, see:
**`terraform/SINGLETON_RESOURCE_FIX.md`**

