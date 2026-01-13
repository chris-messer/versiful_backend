# vCard Auto-Generation

## Overview

The vCard file (`versiful-contact.vcf`) is automatically generated and deployed by Terraform based on the `versiful_phone` variable in each environment's `.tfvars` file.

## How It Works

1. **Phone number is defined** in environment-specific `.tfvars` files:
   - `dev.tfvars`: `versiful_phone = "+18336811158"`
   - `staging.tfvars`: `versiful_phone = "+18335961548"`
   - `prod.tfvars`: `versiful_phone = "+18888671394"`

2. **Terraform generates vCard** with the correct phone number using the `local.vcard_content` local value in `modules/s3/main.tf`

3. **Terraform uploads to S3** via the `aws_s3_object.vcard` resource

4. **vCard is accessible** at:
   - Dev: `https://dev.versiful.io/versiful-contact.vcf`
   - Staging: `https://staging.versiful.io/versiful-contact.vcf`
   - Prod: `https://versiful.io/versiful-contact.vcf`

## Changing the Phone Number

To change the phone number for any environment:

1. **Update the `.tfvars` file**:
   ```bash
   # Edit the appropriate file
   vim terraform/dev.tfvars      # for dev
   vim terraform/staging.tfvars  # for staging
   vim terraform/prod.tfvars     # for prod
   ```

2. **Update the versiful_phone value**:
   ```hcl
   versiful_phone = "+18881234567"  # Your new number
   ```

3. **Apply Terraform changes**:
   ```bash
   cd terraform
   terraform plan -var-file=dev.tfvars      # Review changes
   terraform apply -var-file=dev.tfvars     # Apply changes
   ```

4. **Terraform will automatically**:
   - Detect the phone number change (via the `etag` in the S3 object resource)
   - Regenerate the vCard with the new phone number
   - Upload the new vCard to S3
   - Invalidate CloudFront cache (if applicable)

## What Gets Updated

When you change `versiful_phone`:
- ✅ vCard file with new phone number
- ✅ `config.json` with formatted phone displays
- ✅ Lambda environment variables (for SMS sending)

## Manual Verification

After applying changes, verify the vCard:
```bash
# Check the phone number in the vCard
curl https://dev.versiful.io/versiful-contact.vcf | grep TEL
```

Expected output:
```
TEL;TYPE=CELL:+18881234567
```

## Welcome SMS Flow

1. User registers and enters their phone number
2. Backend calls `send_welcome_sms()` from `lambdas/shared/sms_notifications.py`
3. Welcome SMS is sent via Twilio with vCard attachment
4. vCard URL points to environment-specific S3 file
5. User receives SMS with correct Versiful phone number in the contact card

## Files Involved

- **Terraform**: `terraform/modules/s3/main.tf` (lines 74-115)
- **Variables**: `terraform/variables.tf` (versiful_phone)
- **Environment configs**: `terraform/*.tfvars`
- **Backend code**: `lambdas/shared/sms_notifications.py`

## Troubleshooting

If welcome messages show wrong phone number:
1. Check which `.tfvars` file was used in last apply
2. Verify S3 file: `curl https://{env}.versiful.io/versiful-contact.vcf`
3. Check Terraform state: `terraform show | grep versiful_phone`
4. Re-apply if needed: `terraform apply -var-file={env}.tfvars`

