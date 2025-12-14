# Shared Terraform root (per-environment configs)

This directory is intended to replace the duplicated `dev/staging/prod` roots.
Use it with per-environment backend and tfvars files, e.g.:

```
terraform -chdir=terraform init -backend-config=backend.dev.hcl -reconfigure
terraform -chdir=terraform plan -var-file=dev.tfvars
```

Notes:
- Prod apex DNS/ACM resources (formerly `environments/prod/parent_dns.tf`) are now included here, guarded by `environment == "prod"`.
- `*.tfvars` remain gitignored; keep secrets out of version control.

