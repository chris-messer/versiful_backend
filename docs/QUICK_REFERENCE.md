# Quick Reference Card

## Daily Workflow - One Page

### 🚀 Start New Feature
```bash
git checkout dev && git pull
git checkout -b feature/my-feature
```

### 💻 Development Loop
```bash
# 1. Code
vim lambdas/...

# 2. Test (run frequently!)
pytest tests/unit -v -m unit

# 3. Test integrations (before commit)
pytest tests/integration -v -m integration

# 4. Commit
git add .
git commit -m "feat: what you did"
```

### 📤 Create PR
```bash
git push origin feature/my-feature
gh pr create --base dev --head feature/my-feature
```

### ⚙️ CI/CD Runs Automatically
```
PR:    Unit + Integration tests only (fast)
Merge: Unit + Integration + E2E tests (against environment)
```

### ✅ After Merge
```bash
git checkout dev && git pull
git branch -d feature/my-feature
```

---

## Testing Quick Reference

| Test Type | When to Run | Speed | Cost | Command |
|-----------|-------------|-------|------|---------|
| Unit | Always, every change | ⚡ Fast (seconds) | Free | `pytest tests/unit -v -m unit` |
| Integration | Before commits | 🏃 Medium (1-2 min) | Free | `pytest tests/integration -v -m integration` |
| E2E | Rarely, only when needed | 🐌 Slow (5-10 min) | 💰 Costs $ | `pytest tests/e2e -v -m e2e` |

---

## Branch Strategy

```
feature/x ───┐
feature/y ───┼──→ dev ──→ staging ──→ main (prod)
feature/z ───┘
```

- **feature/***: Your work
- **dev**: Integration, auto E2E tests
- **staging**: Pre-prod validation
- **main/prod**: Production

---

## Commit Message Format

```
<type>: <summary>

<body (optional)>
```

**Types:** feat, fix, refactor, test, docs, chore

**Examples:**
```
feat: Add email validation
fix: Correct token expiry bug
refactor: Extract auth logic to helper
test: Add edge cases for user creation
```

---

## Common Commands

```bash
# Status
git status
pytest tests/unit -v

# Sync with dev
git checkout dev && git pull

# Update feature branch
git checkout feature/name
git merge origin/dev

# Clean up
git branch -d feature/name
git fetch --prune
```

---

## When Tests Fail

### PR Failed ❌
```bash
# Check what failed in GitHub Actions
# Run locally:
pytest tests/unit -v
# Fix and push
git add . && git commit -m "fix: ..." && git push
```

### E2E Failed After Merge ❌
```bash
# Run locally against dev
export ENVIRONMENT=dev
pytest tests/e2e -v
# Create fix PR
git checkout -b fix/e2e-issue
```

---

## Environment Variables for Local E2E

```bash
export ENVIRONMENT=dev
export API_BASE_URL=https://api.dev.versiful.io
export USER_POOL_ID=us-east-1_xxxxx
export USER_POOL_CLIENT_ID=xxxxxxxxx
export TEST_USER_EMAIL=test@example.com
export TEST_USER_PASSWORD=xxxxx
```

---

## Golden Rules

1. ✅ **Always** work on feature branches
2. ✅ **Always** run unit tests before committing
3. ✅ **Always** wait for CI before merging
4. ✅ **Never** commit secrets or credentials
5. ✅ **Never** force push to dev/staging/prod
6. ⚠️ **Rarely** run E2E tests locally ($$)

---

## Help & Resources

- **Full workflow**: `docs/DEVELOPMENT_WORKFLOW.md`
- **CI/CD setup**: `docs/CI_CD_TESTING.md`
- **Quick start**: `docs/CI_CD_SETUP_SUMMARY.md`
- **Ask team**: Questions welcome!

---

## Typical Day Timeline

```
09:00  git checkout dev && git pull
09:15  git checkout -b feature/new-thing
       
10:00  # Coding...
       pytest tests/unit -v  (run frequently)
       
12:00  pytest tests/integration -v
       git commit -m "feat: added X"
       
14:00  git push origin feature/new-thing
       gh pr create
       
14:30  CI passes ✅, request review
15:00  Address feedback, push again
       
16:00  Merge to dev
       E2E tests run automatically ✅
       
16:15  git checkout dev && git pull
```

**Keep it simple. Test often. Ship fast.** 🚀

