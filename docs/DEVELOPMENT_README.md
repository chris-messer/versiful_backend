# Development & Testing

## 📚 Documentation

- **[Quick Reference](docs/QUICK_REFERENCE.md)** - One-page cheat sheet for daily workflow
- **[Development Workflow](docs/DEVELOPMENT_WORKFLOW.md)** - Complete guide to feature development, PRs, and deployments
- **[CI/CD Testing Setup](docs/CI_CD_TESTING.md)** - Detailed CI/CD testing configuration and troubleshooting
- **[CI/CD Setup Summary](docs/CI_CD_SETUP_SUMMARY.md)** - Quick start guide for CI/CD

## 🚀 Quick Start

### Daily Development
```bash
# Start new feature
git checkout dev && git pull
git checkout -b feature/my-feature

# Code and test frequently
pytest tests/unit -v -m unit

# Before committing
pytest tests/integration -v -m integration

# Push and create PR
git push origin feature/my-feature
gh pr create --base dev
```

### CI/CD Pipeline

**On Pull Request:**
- ✅ Unit tests (fast, mocked)
- ✅ Integration tests (fast, mocked)

**After Merge to dev/staging/prod:**
- ✅ Unit tests
- ✅ Integration tests  
- ✅ E2E tests (against real AWS environment)
- ✅ Smoke tests

## 🧪 Testing

### Test Types

| Type | Marker | When | Speed | Command |
|------|--------|------|-------|---------|
| Unit | `@pytest.mark.unit` | Always | ⚡ Seconds | `pytest tests/unit -v -m unit` |
| Integration | `@pytest.mark.integration` | Before commit | 🏃 1-2 min | `pytest tests/integration -v -m integration` |
| E2E | `@pytest.mark.e2e` | Rarely/Auto | 🐌 5-10 min | `pytest tests/e2e -v -m e2e` |

### Running Tests Locally

```bash
# All unit tests
pytest tests/unit -v -m unit

# All integration tests
pytest tests/integration -v -m integration

# Specific test file
pytest tests/unit/auth/test_handler.py -v

# With coverage
pytest tests/unit -v --cov=lambdas --cov-report=term-missing

# E2E tests (requires environment variables)
export ENVIRONMENT=dev
export API_BASE_URL=https://api.dev.versiful.io
pytest tests/e2e -v -m e2e
```

## 🌍 Environments

- **dev** → `https://api.dev.versiful.io`
- **staging** → `https://api.staging.versiful.io`  
- **prod** → `https://api.versiful.io`

## 🔀 Branch Strategy

```
feature/* ───→ dev ───→ staging ───→ main (prod)
```

- **feature/**: Individual features
- **dev**: Active development, E2E tests run here
- **staging**: Pre-production validation
- **main/prod**: Production

## 📖 New to the Project?

1. Read **[Quick Reference](docs/QUICK_REFERENCE.md)** (5 min)
2. Skim **[Development Workflow](docs/DEVELOPMENT_WORKFLOW.md)** (15 min)
3. Set up your environment (see below)
4. Run your first tests: `pytest tests/unit -v`
5. Create your first feature branch!

## Need Help?

- Check the docs in `docs/`
- Ask the team
- Review existing PRs for examples

