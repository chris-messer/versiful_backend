# Development Workflow Guide

## Overview

This guide outlines the recommended development workflow for versiful-backend, from feature development through production deployment.

## Branch Strategy

```
main (prod)     ──────●────────●────────●──────→  Production releases
                      │        │        │
staging         ──────●────────●────────●──────→  Pre-production testing
                      │        │        │
dev             ──●───●───●────●───●────●──────→  Active development
                  │   │   │    │   │    │
feature branches  ●   ●   ●    ●   ●    ●       Feature development
```

### Branch Purposes

- **`main`** (or `prod`): Production code, always stable
- **`staging`**: Pre-production environment, mirrors prod setup
- **`dev`**: Development environment, where features integrate
- **`feature/*`**: Individual feature branches (e.g., `feature/user-auth`, `tf-refactor`)

## Daily Development Workflow

### 1. Start a New Feature

```bash
# Make sure you're on latest dev
git checkout dev
git pull origin dev

# Create feature branch from dev
git checkout -b feature/my-awesome-feature

# OR if fixing a bug
git checkout -b fix/bug-description
```

**Naming conventions:**
- Features: `feature/short-description`
- Bugs: `fix/bug-description`
- Refactoring: `refactor/what-you-changed`
- Infrastructure: `infra/what-infrastructure`

### 2. Develop Locally

```bash
# Make changes to your code
vim lambdas/auth/auth_handler.py

# Run unit tests frequently (fast!)
pytest tests/unit -v -m unit

# Run integration tests when you change interactions
pytest tests/integration -v -m integration

# Run specific test file
pytest tests/unit/auth/test_handler.py -v

# Run with coverage
pytest tests/unit -v --cov=lambdas/auth --cov-report=term-missing
```

**Testing philosophy:**
- **Unit tests**: Run constantly (every save ideally)
- **Integration tests**: Run before committing
- **E2E tests**: Run manually only when needed locally

### 3. Local E2E Testing (Optional, when needed)

Only run E2E tests locally when you need to test against real AWS resources:

```bash
# Set up environment
export ENVIRONMENT=dev
export API_BASE_URL=https://api.dev.versiful.io
export USER_POOL_ID=<your-dev-pool-id>
export USER_POOL_CLIENT_ID=<your-dev-client-id>
export TEST_USER_EMAIL=<test-email>
export TEST_USER_PASSWORD=<test-password>

# Run E2E tests
pytest tests/e2e -v -m e2e

# Or specific test
pytest tests/e2e/test_auth.py::test_login_flow -v
```

⚠️ **Note**: E2E tests cost money (AWS resources) and are slower. Use sparingly during development.

### 4. Commit Your Changes

```bash
# Check what changed
git status
git diff

# Stage changes
git add lambdas/auth/auth_handler.py
git add tests/unit/auth/test_handler.py

# Commit with descriptive message
git commit -m "feat: Add email validation to auth handler

- Add email format validation
- Add tests for edge cases
- Update error messages"
```

**Commit message format:**
```
<type>: <short summary>

<detailed description if needed>
<what changed and why>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code change without feature/fix
- `test`: Adding/updating tests
- `docs`: Documentation only
- `chore`: Maintenance tasks

### 5. Push and Create PR

```bash
# Push feature branch to remote
git push origin feature/my-awesome-feature

# Create PR using GitHub CLI
gh pr create --base dev --head feature/my-awesome-feature --title "Add email validation" --body "
## Changes
- Added email validation to auth handler
- Added comprehensive test coverage

## Testing
- ✅ All unit tests pass
- ✅ All integration tests pass
- ⏳ E2E tests will run after merge

## Screenshots/Logs
(if applicable)
"
```

**Or via GitHub UI:**
1. Go to repository on GitHub
2. Click "Pull requests" → "New pull request"
3. Base: `dev`, Compare: `feature/my-awesome-feature`
4. Fill out PR template
5. Request reviewers

### 6. Wait for CI/CD (Automatic)

**What happens automatically:**
```
1. GitHub Actions triggers
   ├─ Run unit tests (~1-2 min)
   ├─ Run integration tests (~2-3 min)
   └─ Report status on PR ✅ or ❌

2. You see results in PR
   ├─ All checks passed → ✅ Ready for review
   └─ Some checks failed → ❌ Fix and push again
```

### 7. Address Review Feedback

```bash
# Make requested changes
vim lambdas/auth/auth_handler.py

# Test locally
pytest tests/unit/auth -v

# Commit and push
git add .
git commit -m "fix: Address review feedback - improve error handling"
git push origin feature/my-awesome-feature

# CI/CD runs again automatically
```

### 8. Merge to Dev

Once approved:

```bash
# Option 1: Via GitHub UI
# Click "Merge pull request" → "Squash and merge"

# Option 2: Via GitHub CLI
gh pr merge --squash --delete-branch

# Option 3: Manually
git checkout dev
git pull origin dev
git merge --squash feature/my-awesome-feature
git commit -m "feat: Add email validation (#123)"
git push origin dev
git branch -d feature/my-awesome-feature
```

**After merge to dev:**
```
Automatic CI/CD triggers:
├─ Unit tests ✅
├─ Integration tests ✅
└─ E2E tests against DEV environment ✅
   (Tests real AWS resources in dev)
```

### 9. Update Local Dev Branch

```bash
# Switch to dev and update
git checkout dev
git pull origin dev

# Clean up feature branch locally
git branch -d feature/my-awesome-feature
```

## Promoting Through Environments

### Dev → Staging (Weekly or as needed)

```bash
# Make sure dev is stable and all tests pass
# Check GitHub Actions - all green? ✅

# Create PR from dev to staging
git checkout staging
git pull origin staging
gh pr create --base staging --head dev --title "Deploy week of 2025-01-15"

# After approval and merge:
# CI/CD runs E2E tests against STAGING environment
```

**Staging criteria:**
- All dev E2E tests passing
- Feature complete and ready for broader testing
- Manual QA completed (if applicable)

### Staging → Prod (Weekly/Bi-weekly)

```bash
# Staging has been tested and validated
# All staging E2E tests passing

# Create PR from staging to prod/main
git checkout main  # or prod
git pull origin main
gh pr create --base main --head staging --title "Production release v1.2.0"

# Add release notes
# After approval and merge:
# CI/CD runs E2E tests against PROD environment
```

**Production criteria:**
- All staging tests passing
- Manual QA approval
- Product owner approval
- Release notes prepared
- Rollback plan ready

## Testing Strategy by Stage

### During Development (Feature Branch)
```bash
# Run frequently:
✅ Unit tests (pytest tests/unit -v -m unit)

# Run before committing:
✅ Integration tests (pytest tests/integration -v -m integration)

# Run only when necessary:
⚠️  Local E2E tests (expensive, slow)
```

### In PR (Automated)
```
✅ Unit tests - GitHub Actions
✅ Integration tests - GitHub Actions
❌ E2E tests - NOT run (save costs, faster feedback)
```

### After Merge to Dev/Staging/Prod (Automated)
```
✅ Unit tests - GitHub Actions
✅ Integration tests - GitHub Actions
✅ E2E tests - GitHub Actions (against that environment)
✅ Smoke tests - GitHub Actions (health checks)
```

## Common Workflows

### Hotfix to Production

When you need to fix prod ASAP:

```bash
# Branch from main/prod (not dev!)
git checkout main
git pull origin main
git checkout -b hotfix/critical-bug

# Make minimal fix
# Test thoroughly
pytest tests/unit -v
pytest tests/integration -v

# Create PR directly to main/prod
gh pr create --base main --head hotfix/critical-bug

# After merge, backport to staging and dev
git checkout staging
git cherry-pick <hotfix-commit-sha>
git push origin staging

git checkout dev
git cherry-pick <hotfix-commit-sha>
git push origin dev
```

### Working on Multiple Features

```bash
# Save work in progress
git stash save "WIP: feature X"

# Switch to other feature
git checkout feature/other-feature
# ... work on it ...

# Come back
git checkout feature/my-feature
git stash pop
```

### Syncing Feature Branch with Latest Dev

```bash
# Your feature branch is behind dev
git checkout feature/my-feature
git fetch origin

# Option 1: Merge (preserves history)
git merge origin/dev

# Option 2: Rebase (cleaner history)
git rebase origin/dev
# Resolve conflicts if any
git push --force-with-lease origin feature/my-feature
```

## Terraform Deployments (per environment)

- Always run Terraform through the helper to bind backend + vars to the target env:
  - `cd terraform`
  - `./scripts/tf-env.sh dev plan` (or `staging` / `prod`)
  - `./scripts/tf-env.sh dev apply`
- The script reconfigures the backend each run, so you don’t accidentally push staging into the dev state key.
- If you run Terraform manually, you must pass both `-backend-config=backend.<env>.hcl -reconfigure` **and** `-var-file=<env>.tfvars`, and ensure `var.environment` matches the env name.

## Best Practices

### ✅ Do's

- **Commit often** - Small, logical commits are easier to review
- **Pull before pushing** - Avoid conflicts
- **Write tests first** - TDD when possible
- **Run tests before pushing** - Catch issues early
- **Keep PRs focused** - One feature per PR
- **Update documentation** - If you change behavior
- **Clean up branches** - Delete after merge
- **Review your own PR first** - Catch obvious issues

### ❌ Don'ts

- **Don't commit secrets** - Use environment variables
- **Don't force push to shared branches** - Only to your feature branches
- **Don't merge without tests** - Wait for CI to pass
- **Don't skip code review** - Even for "small" changes
- **Don't commit commented-out code** - Delete it (Git remembers)
- **Don't work directly on dev/staging/prod** - Always use feature branches
- **Don't run E2E tests constantly locally** - Expensive!

## Troubleshooting

### PR Checks Failed

```bash
# Pull latest changes
git pull origin dev

# Run tests locally
pytest tests/ -v

# Check specific failure
pytest tests/unit/auth/test_handler.py::test_that_failed -vv

# Fix issue, commit, push
git add .
git commit -m "fix: Address test failure"
git push origin feature/my-feature
```

### Merge Conflicts

```bash
# Update your branch with latest dev
git checkout feature/my-feature
git fetch origin
git merge origin/dev

# Git will show conflicts
# Edit conflicted files
vim conflicted_file.py

# Mark as resolved
git add conflicted_file.py
git commit -m "Merge dev into feature branch"
git push origin feature/my-feature
```

### E2E Tests Failing After Merge

```bash
# Check GitHub Actions logs
# Look for specific error

# Run locally against dev environment
export ENVIRONMENT=dev
pytest tests/e2e/test_that_failed.py -vv

# Fix issue on new branch
git checkout -b fix/e2e-test-failure
# ... fix ...
git push origin fix/e2e-test-failure
gh pr create --base dev --head fix/e2e-test-failure
```

## Quick Reference

### Most Used Commands

```bash
# Start work
git checkout dev && git pull && git checkout -b feature/name

# Check status
git status
pytest tests/unit -v

# Commit
git add . && git commit -m "feat: description"

# Push and create PR
git push origin feature/name
gh pr create --base dev

# After merge
git checkout dev && git pull
```

### Useful Git Aliases

Add to `~/.gitconfig`:

```ini
[alias]
    co = checkout
    br = branch
    st = status
    cm = commit -m
    aa = add --all
    lg = log --oneline --graph --decorate
    sync = !git checkout dev && git pull origin dev
```

## Summary

Your typical day:

1. 🌅 **Morning**: `git checkout dev && git pull`
2. 🔨 **Work**: Create feature branch, code, test (unit/integration)
3. 💾 **Commit**: Small, logical commits with good messages
4. 🚀 **PR**: Push, create PR, wait for CI, address feedback
5. ✅ **Merge**: Squash merge to dev, E2E tests run automatically
6. 🔄 **Repeat**: Move to next feature

**Key principle**: Keep the feedback loop tight - test early, test often, get code reviewed quickly!

