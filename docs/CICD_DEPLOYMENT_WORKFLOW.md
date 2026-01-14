# Versiful CI/CD Deployment Workflow

This document outlines the complete deployment process for both backend (Terraform) and frontend (GitHub Actions CI/CD) changes.

## Table of Contents
- [Branch Naming Conventions](#branch-naming-conventions)
- [Deployment Process Overview](#deployment-process-overview)
- [Backend Deployment (Terraform)](#backend-deployment-terraform)
- [Frontend Deployment (CI/CD)](#frontend-deployment-cicd)
- [Full Deployment Workflows](#full-deployment-workflows)
- [Quick Reference Commands](#quick-reference-commands)

---

## Branch Naming Conventions

Use consistent branch names across both repositories when changes touch both frontend and backend:

| Type | Branch Prefix | Example |
|------|---------------|---------|
| New Features | `feature/` | `feature/getting-started-page` |
| Bug Fixes | `fix/` | `fix/auth-callback-error` |
| Refactoring | `refactor/` | `refactor/user-service` |
| Infrastructure | `infra/` | `infra/add-sms-usage-tracking` |
| Chores | `chore/` | `chore/update-dependencies` |
| Documentation | `docs/` | `docs/deployment-guide` |
| Tests | `test/` | `test/add-auth-tests` |

**Important:** When changes affect both frontend and backend, use the **same branch name** in both repositories.

---

## Deployment Process Overview

### Backend (Terraform)
- **No staging branch** - Use dev branch for staging deployments
- Terraform changes applied via `scripts/tf-env.sh` wrapper
- Manual deployment to each environment

### Frontend (GitHub Actions)
- **Automated CI/CD** on branch push
- Branch → Environment mapping:
  - `dev` → dev environment
  - `staging` → staging environment  
  - `main` → production environment

---

## Backend Deployment (Terraform)

### Directory Structure
```
versiful-backend/
├── terraform/
│   ├── scripts/
│   │   └── tf-env.sh      # Terraform wrapper script
│   ├── dev.tfvars
│   ├── staging.tfvars
│   └── prod.tfvars
```

### 1. Create Feature Branch & Make Changes

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend

# Create and checkout feature branch
git checkout -b feature/your-feature-name

# Make your changes...
# Edit files as needed

# Stage and commit changes
git add .
git commit -m "feat: descriptive commit message"

# Push branch to remote
git push origin feature/your-feature-name
```

### 2. Deploy to Dev

```bash
# Merge feature branch to dev
git checkout dev
git pull origin dev
git merge feature/your-feature-name
git push origin feature/your-feature-name  # Push feature branch for reference

# Apply changes to dev environment
cd terraform
../scripts/tf-env.sh dev apply

# Or plan first to review changes
../scripts/tf-env.sh dev plan
../scripts/tf-env.sh dev apply
```

### 3. Deploy to Staging

**Note:** Backend has no staging branch - deploy staging from dev branch

```bash
# Still on dev branch
cd terraform
../scripts/tf-env.sh staging apply

# Or plan first
../scripts/tf-env.sh staging plan
../scripts/tf-env.sh staging apply
```

### 4. Deploy to Production

```bash
# Merge dev to main
git checkout main
git pull origin main
git merge dev
git push origin main

# Apply to production
cd terraform
../scripts/tf-env.sh prod apply

# Or plan first
../scripts/tf-env.sh prod plan
../scripts/tf-env.sh prod apply
```

**Note:** Backend always goes dev → main (no staging branch in git, but can deploy to staging environment from dev branch).

---

## Frontend Deployment (CI/CD)

### Directory Structure
```
versiful-frontend/
├── .github/
│   └── workflows/
│       └── deploy.yml    # CI/CD configuration
```

### 1. Create Feature Branch & Make Changes

```bash
cd /Users/christopher.messer/WebstormProjects/versiful-frontend

# Create and checkout feature branch (same name as backend if applicable)
git checkout -b feature/your-feature-name

# Make your changes...
# Edit files as needed

# Stage and commit changes
git add .
git commit -m "feat: descriptive commit message"

# Push branch to remote
git push origin feature/your-feature-name
```

### 2. Deploy to Dev

```bash
# Merge feature branch to dev
git checkout dev
git pull origin dev
git merge feature/your-feature-name

# Push - CI/CD automatically deploys to dev
git push origin dev
```

**✅ Automatic:** GitHub Actions builds and deploys to dev environment automatically.

### 3. Deploy to Staging

```bash
# Merge dev to staging
git checkout staging
git pull origin staging
git merge dev

# Push - CI/CD automatically deploys to staging
git push origin staging
```

**✅ Automatic:** GitHub Actions builds and deploys to staging environment automatically.

### 4. Deploy to Production

```bash
# Merge staging to main
git checkout main
git pull origin main
git merge staging

# Push - CI/CD automatically deploys to production
git push origin main
```

**✅ Automatic:** GitHub Actions builds and deploys to production environment automatically.

---

## Full Deployment Workflows

### Workflow 1: Dev Only (Testing Phase)

Use this when you want to test changes in dev before promoting.

**Backend:**
```bash
cd versiful-backend
git checkout -b feature/my-feature
# Make changes
git add . && git commit -m "feat: my feature"
git push origin feature/my-feature

# Merge to dev and deploy
git checkout dev
git merge feature/my-feature
git push origin dev
cd terraform
../scripts/tf-env.sh dev apply
```

**Frontend:**
```bash
cd versiful-frontend
git checkout -b feature/my-feature
# Make changes
git add . && git commit -m "feat: my feature"
git checkout dev
git merge feature/my-feature
git push origin dev  # Auto-deploys to dev
```

**Test in dev, then proceed to staging/prod when ready.**

---

### Workflow 2: Dev → Staging → Prod (Small Updates, No Testing)

Use this for small, low-risk changes that don't require testing between environments.

#### Backend:
```bash
cd versiful-backend
git checkout -b fix/small-update
# Make changes
git add . && git commit -m "fix: small update"
git push origin fix/small-update

# Merge to dev and deploy to dev
git checkout dev
git merge fix/small-update
git push origin dev
cd terraform
../scripts/tf-env.sh dev apply

# Deploy to staging (from dev branch)
../scripts/tf-env.sh staging apply

# Merge dev to main and deploy to prod
cd ..
git checkout main
git merge dev
git push origin main
cd terraform
../scripts/tf-env.sh prod apply
```

#### Frontend:
```bash
cd versiful-frontend
git checkout -b fix/small-update
# Make changes
git add . && git commit -m "fix: small update"

# Deploy to dev
git checkout dev
git merge fix/small-update
git push origin dev  # Auto-deploys

# Deploy to staging
git checkout staging
git merge dev
git push origin staging  # Auto-deploys

# Deploy to production
git checkout main
git merge staging
git push origin main  # Auto-deploys
```

---

### Workflow 3: Full Cycle with Testing (Recommended for Major Changes)

Use this for significant features or changes that need validation at each stage.

#### Backend:
```bash
cd versiful-backend
git checkout -b feature/major-feature
# Make changes
git add . && git commit -m "feat: major feature"
git push origin feature/major-feature

# Merge to dev and deploy to dev
git checkout dev
git merge feature/major-feature
git push origin dev
cd terraform
../scripts/tf-env.sh dev apply

# ⏸️ TEST IN DEV ENVIRONMENT

# Deploy to staging (from dev branch)
../scripts/tf-env.sh staging apply

# ⏸️ TEST IN STAGING ENVIRONMENT

# Merge dev to main and deploy to prod
cd ..
git checkout main
git merge dev
git push origin main
cd terraform
../scripts/tf-env.sh prod apply

# ⏸️ VERIFY IN PRODUCTION
```

#### Frontend:
```bash
cd versiful-frontend
git checkout -b feature/major-feature
# Make changes
git add . && git commit -m "feat: major feature"

# Deploy to dev
git checkout dev
git merge feature/major-feature
git push origin dev  # Auto-deploys

# ⏸️ TEST IN DEV ENVIRONMENT

# Deploy to staging
git checkout staging
git merge dev
git push origin staging  # Auto-deploys

# ⏸️ TEST IN STAGING ENVIRONMENT

# Deploy to production
git checkout main
git merge staging
git push origin main  # Auto-deploys

# ⏸️ VERIFY IN PRODUCTION
```

---

## Quick Reference Commands

### Backend (Terraform)

```bash
# Create branch
git checkout -b <type>/<description>

# Commit changes
git add .
git commit -m "<type>: <message>"
git push origin <branch-name>

# Merge to dev
git checkout dev
git merge <branch-name>
git push origin dev

# Deploy to environments
cd terraform
../scripts/tf-env.sh dev plan       # Review dev changes
../scripts/tf-env.sh dev apply      # Deploy to dev
../scripts/tf-env.sh staging apply  # Deploy to staging (from dev branch)

# Merge dev to main for prod
cd ..
git checkout main
git merge dev
git push origin main
cd terraform
../scripts/tf-env.sh prod apply     # Deploy to prod (from main branch)
```

### Frontend (CI/CD)

```bash
# Create branch
git checkout -b <type>/<description>

# Commit changes
git add .
git commit -m "<type>: <message>"

# Deploy to dev
git checkout dev
git merge <branch-name>
git push origin dev                 # ✅ Auto-deploys

# Deploy to staging
git checkout staging
git merge dev
git push origin staging             # ✅ Auto-deploys

# Deploy to production
git checkout main
git merge staging
git push origin main                # ✅ Auto-deploys
```

---

## Environment URLs

| Environment | Frontend URL | Backend API URL |
|-------------|--------------|-----------------|
| **Dev** | https://dev.versiful.io | https://api.dev.versiful.io |
| **Staging** | https://staging.versiful.io | https://api.staging.versiful.io |
| **Production** | https://versiful.io | https://api.versiful.io |

---

## Important Notes

### Backend Considerations
- **Always use `tf-env.sh` wrapper** - Never run terraform commands directly
- **No staging branch in git** - Only dev and main branches exist
- **Staging deploys from dev** - Deploy to staging environment using dev branch code
- **Production deploys from main** - Always merge dev → main before deploying to production
- **Branch flow**: `feature branch → dev → main`
- **Manual deployments** - Each environment must be deployed explicitly using tf-env.sh
- **Plan before apply** - Review changes with `plan` before `apply` for production

### Frontend Considerations
- **Automated deployments** - Push triggers automatic build and deploy
- **Must go through staging** - Always merge dev → staging → main (never skip staging)
- **Never merge feature branches to main** - Feature branches should only merge to dev, then flow through staging
- **Branch protection** - Main, staging, and dev branches should have protection rules
- **Build time** - Deployment takes ~2-5 minutes per environment
- **Rollback** - If needed, revert the merge commit and push

### General Best Practices
- **Same branch names** - Use identical names when touching both repos
- **Commit messages** - Follow conventional commits format (`feat:`, `fix:`, `chore:`, etc.)
- **Test before prod** - Always test in dev/staging before production
- **One environment at a time** - Don't skip environments unless you're certain
- **Keep branches synced** - Regularly merge main back into long-lived feature branches

---

## Troubleshooting

### Backend Issues

**Problem:** Terraform state lock
```bash
# Force unlock (use with caution)
cd terraform
terraform force-unlock <LOCK_ID>
```

**Problem:** Changes not applying
```bash
# Refresh state and retry
../scripts/tf-env.sh dev refresh
../scripts/tf-env.sh dev apply
```

### Frontend Issues

**Problem:** Build failing in CI/CD
- Check GitHub Actions logs in repository
- Look for dependency or linting errors
- Ensure all environment variables are set in GitHub Secrets

**Problem:** Deployment not updating
- Check CloudFront invalidation completed
- May take 5-10 minutes for CDN cache to clear
- Force refresh in browser (Cmd+Shift+R or Ctrl+Shift+R)

---

## Common Scenarios

### Hotfix to Production

When you need to fix a critical bug in production quickly:

```bash
# Backend
cd versiful-backend
git checkout main
git checkout -b fix/critical-hotfix
# Make fix
git add . && git commit -m "fix: critical production issue"
git push origin fix/critical-hotfix
git checkout main
git merge fix/critical-hotfix
git push origin main
cd terraform
../scripts/tf-env.sh prod apply

# Frontend
cd versiful-frontend
git checkout main
git checkout -b fix/critical-hotfix
# Make fix
git add . && git commit -m "fix: critical production issue"
git checkout main
git merge fix/critical-hotfix
git push origin main  # Auto-deploys
```

Then backport to dev (and staging for frontend):
```bash
# Backend: backport to dev
git checkout dev
git merge main
git push origin dev

# Frontend: backport to staging and dev
git checkout staging
git merge main
git push origin staging

git checkout dev
git merge staging
git push origin dev
```

### Reverting a Deployment

**Frontend (Easy):**
```bash
git revert <commit-hash>
git push origin <branch>  # Auto-deploys reverted version
```

**Backend (Manual):**
```bash
git revert <commit-hash>
git push origin main
cd terraform
../scripts/tf-env.sh prod apply
```

---

**Last Updated:** 2026-01-14  
**Maintainer:** Development Team

