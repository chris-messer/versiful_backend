# Terraform Singleton Resource Fix

## Problem Summary

Your Terraform deployment had a critical issue where **singleton AWS resources** were being fought over by multiple environments (dev, staging, prod). This caused:

- ❌ Slow deployments (resources constantly being updated between environments)
- ❌ Configuration conflicts (last-deployed environment "wins")
- ❌ Potential logging failures across environments
- ❌ State file conflicts

## Root Cause

Two resources were incorrectly shared across all environments:

1. **`aws_api_gateway_account`** - This is a **singleton per AWS account per region**
2. **`aws_iam_policy_attachment`** - This globally attaches policies to roles

When deploying:
- Dev deployment → sets CloudWatch role to `dev-versiful-APIGatewayCloudWatchLogsRole`
- Staging deployment → **overwrites** to `staging-versiful-APIGatewayCloudWatchLogsRole`
- Prod deployment → **overwrites** to `prod-versiful-APIGatewayCloudWatchLogsRole`

Each environment was fighting over the same global AWS resource!

## The Fix

### What Changed

**Removed from `modules/lambdas/main.tf`:**
- `aws_iam_role.api_gateway_cloudwatch_role` (environment-specific role)
- `aws_iam_policy_attachment.api_gateway_logs_policy` (singleton attachment)
- `aws_api_gateway_account.account_settings` (singleton account config)
- `aws_cloudwatch_log_group.api_gateway_log_group` (moved to apiGateway module)

**Added to `modules/apiGateway/main.tf`:**
- `aws_cloudwatch_log_group.api_gateway_log_group` (environment-specific log group)
- Updated stage configuration to reference the new log group

### Why This Works

API Gateway v2 (HTTP API) doesn't need `aws_api_gateway_account` - that's for REST APIs. Your infrastructure uses HTTP API (`aws_apigatewayv2_api`), which:
- Handles logging per-stage via `access_log_settings`
- Doesn't require account-level CloudWatch role configuration
- Each environment gets its own isolated log group

## Migration Steps

### Step 1: Backup Current State (IMPORTANT!)

```bash
cd terraform

# Backup all environment states
terraform init -backend-config=backend.dev.hcl
terraform state pull > dev-state-backup-$(date +%Y%m%d).json

terraform init -backend-config=backend.staging.hcl -reconfigure
terraform state pull > staging-state-backup-$(date +%Y%m%d).json

terraform init -backend-config=backend.prod.hcl -reconfigure
terraform state pull > prod-state-backup-$(date +%Y%m%d).json
```

### Step 2: Remove Resources from State (Per Environment)

You need to remove the problematic resources from Terraform state **before** applying. These resources will remain in AWS but Terraform will stop managing them.

**For Dev:**
```bash
../scripts/tf-env.sh dev init

# Remove the singleton resources
terraform state rm 'module.lambdas.aws_api_gateway_account.account_settings'
terraform state rm 'module.lambdas.aws_iam_policy_attachment.api_gateway_logs_policy'
terraform state rm 'module.lambdas.aws_iam_role.api_gateway_cloudwatch_role'
terraform state rm 'module.lambdas.aws_cloudwatch_log_group.api_gateway_log_group'

# Verify they're gone
terraform state list | grep api_gateway
```

**For Staging:**
```bash
../scripts/tf-env.sh staging init

terraform state rm 'module.lambdas.aws_api_gateway_account.account_settings'
terraform state rm 'module.lambdas.aws_iam_policy_attachment.api_gateway_logs_policy'
terraform state rm 'module.lambdas.aws_iam_role.api_gateway_cloudwatch_role'
terraform state rm 'module.lambdas.aws_cloudwatch_log_group.api_gateway_log_group'
```

**For Prod:**
```bash
../scripts/tf-env.sh prod init

terraform state rm 'module.lambdas.aws_api_gateway_account.account_settings'
terraform state rm 'module.lambdas.aws_iam_policy_attachment.api_gateway_logs_policy'
terraform state rm 'module.lambdas.aws_iam_role.api_gateway_cloudwatch_role'
terraform state rm 'module.lambdas.aws_cloudwatch_log_group.api_gateway_log_group'
```

### Step 3: Plan and Apply Changes (Per Environment)

**Start with Dev (safest):**
```bash
../scripts/tf-env.sh dev plan
```

You should see:
- ✅ `module.apiGateway.aws_cloudwatch_log_group.api_gateway_log_group` will be **created**
- ✅ `module.apiGateway.aws_apigatewayv2_stage.lambda_stage` will be **updated** (new log group reference)
- ✅ NO changes to `aws_api_gateway_account` or `aws_iam_policy_attachment`
- ✅ The CloudFront invalidation resource replacement (normal)

If it looks good:
```bash
../scripts/tf-env.sh dev apply
```

**Then Staging:**
```bash
../scripts/tf-env.sh staging plan
../scripts/tf-env.sh staging apply
```

**Finally Prod:**
```bash
../scripts/tf-env.sh prod plan
../scripts/tf-env.sh prod apply
```

### Step 4: Verify Logging Still Works

After each deployment, verify that API Gateway logs are still being written:

```bash
# Check the new log group exists and has recent logs
aws logs describe-log-streams \
  --log-group-name "/aws/api-gateway/dev-versiful" \
  --order-by LastEventTime \
  --descending \
  --max-items 5
```

### Step 5: Optional Cleanup (After All Environments Deployed)

Once all environments are successfully deployed, you can optionally clean up the orphaned AWS resources:

```bash
# Delete old IAM roles (if you want to clean up)
aws iam detach-role-policy \
  --role-name dev-versiful-APIGatewayCloudWatchLogsRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs

aws iam delete-role --role-name dev-versiful-APIGatewayCloudWatchLogsRole

# Repeat for staging and prod roles...
```

## Expected Improvements

After this fix:

✅ **Faster Deployments**: No more fighting over shared resources  
✅ **Cleaner Plans**: Only environment-specific changes shown  
✅ **Isolated Environments**: Each environment truly independent  
✅ **Better Logging**: Environment-specific log groups make debugging easier  
✅ **No More State Conflicts**: Each environment manages its own resources  

## Troubleshooting

### "Resource already exists" error

If you see an error about a resource already existing, it means the `terraform state rm` command wasn't run. Go back to Step 2.

### "Cannot find resource in state"

If `terraform state rm` says it can't find the resource, it might already be removed or in a different module path. Use `terraform state list` to find the exact path.

### Logs not appearing in CloudWatch

1. Check the log group exists:
   ```bash
   aws logs describe-log-groups --log-group-name-prefix "/aws/api-gateway/"
   ```

2. Verify API Gateway stage configuration:
   ```bash
   aws apigatewayv2 get-stage --api-id <your-api-id> --stage-name dev
   ```

3. Make a test API call and check if logs appear within 1-2 minutes

## Questions?

If you encounter issues:
1. Check your state backups from Step 1
2. Review the Terraform plan output carefully
3. Deploy to dev first to test the changes
4. Don't proceed to prod until dev and staging are verified

## Technical Notes

- API Gateway v2 (HTTP API) != API Gateway v1 (REST API)
- HTTP APIs don't need `aws_api_gateway_account` configuration
- The `access_log_settings` in the stage resource is all you need for logging
- CloudWatch Logs permissions are handled via API Gateway's service-linked role

