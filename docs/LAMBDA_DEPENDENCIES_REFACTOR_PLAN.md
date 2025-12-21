# Lambda Dependencies Refactoring Plan

## Executive Summary

Current issue: The shared lambda layer is ~76MB uncompressed with all dependencies, which when combined with AWS Powertools layer exceeds the 250MB Lambda limit.

**Solution**: Create function-specific dependency packages instead of a single shared layer.

---

## Current Dependency Analysis

### Lambda Functions Overview

| Function | Primary Dependencies | Size Concern |
|----------|---------------------|--------------|
| **SMS** | twilio, openai (via requests), boto3 | HIGH - needs heavy deps |
| **Auth** | jwt, requests, boto3 | MEDIUM |
| **Users** | boto3 only | LOW - stdlib mostly |
| **Authorizer** | jwt, requests | MEDIUM |
| **CORS** | None | NONE - stdlib only |

### Current Shared Layer (`lambdas/layer/requirements.txt`)
```
requests         # 472 KB + dependencies (urllib3, charset_normalizer, etc.)
twilio           # 26 MB (LARGEST - only used by SMS)
openai==1.39.0   # 4 MB + heavy dependencies (pydantic, aiohttp, etc.)
exceptiongroup   # Small
cryptography     # 22 MB (SECOND LARGEST - JWT dependency)
```

**Total Layer Size**: ~76 MB uncompressed, ~17.4 MB compressed

### Dependency Usage by Function

#### SMS Function
- ✅ **twilio** - Required for Twilio messaging (`from twilio.rest import Client`)
- ✅ **requests** - Used for OpenAI API calls (helpers.py lines 86, 129)
- ❌ **openai SDK** - NOT actually imported! Using raw REST API calls
- ✅ **boto3** - AWS SDK (DynamoDB, Secrets Manager)

#### Auth Function  
- ✅ **jwt** - JWT token handling
- ✅ **requests** - Cognito token exchange
- ✅ **boto3** - Cognito client
- ⚠️ **cryptography** - Indirect dependency of jwt[crypto]

#### Users Function
- ✅ **boto3** - DynamoDB operations
- ❌ No other external dependencies needed

#### Authorizer Function
- ✅ **jwt** - JWT verification (`from jwt import PyJWKClient`)
- ✅ **requests** - Fetch JWKS keys
- ⚠️ **cryptography** - Indirect dependency of jwt[crypto]

#### CORS Function
- ❌ No external dependencies - stdlib only

---

## Deployment Strategy

**Direct Zip Upload**: All functions will be deployed via direct zip upload (not S3) since all are well under the 50 MB limit.

## Recommended Architecture

### Option A: Function-Specific Layers (RECOMMENDED)

Create separate layers for different dependency profiles:

#### 1. **Core Layer** (Small - ~5 MB)
**Used by**: Auth, Authorizer, (optionally SMS if needed)
```
requests==2.31.0
urllib3
charset-normalizer
certifi
idna
```

#### 2. **JWT Layer** (Medium - ~25 MB)  
**Used by**: Auth, Authorizer
```
PyJWT[crypto]==2.8.0
cryptography
cffi
pycparser
```

#### 3. **SMS-Specific Layer** (Large - ~27 MB)
**Used by**: SMS only
```
twilio==9.0.0+
```

#### 4. **No Layer Needed**
- **Users**: Package boto3 directly (already in Lambda runtime)
- **CORS**: No dependencies

### Layer Assignment Matrix

| Function | Core Layer | JWT Layer | SMS Layer | Function-Only Deps | Total Size |
|----------|-----------|-----------|-----------|-------------------|------------|
| SMS | ✓ | ✗ | ✓ | boto3 (runtime) | ~32 MB |
| Auth | ✓ | ✓ | ✗ | boto3 (runtime) | ~30 MB |
| Users | ✗ | ✗ | ✗ | boto3 (runtime) | <1 MB |
| Authorizer | ✓ | ✓ | ✗ | - | ~30 MB |
| CORS | ✗ | ✗ | ✗ | - | <1 KB |

**Result**: All functions well under 250 MB limit ✅

---

### Option B: Per-Function Packaging (ALTERNATIVE)

Package each function with only its required dependencies (no shared layers):

| Function | Dependencies | Estimated Size |
|----------|--------------|----------------|
| SMS | twilio + requests | ~27 MB |
| Auth | jwt + cryptography + requests | ~25 MB |
| Users | boto3 (runtime) | <1 MB |
| Authorizer | jwt + cryptography + requests | ~25 MB |
| CORS | - | <1 KB |

**Pros**: 
- Simple to manage
- No layer version coordination
- Each function is independent

**Cons**:
- Duplicate dependencies across functions
- Slower deployments (larger zips)

---

## Key Findings & Optimizations

### 1. **OpenAI SDK Not Needed! 🎉**
The SMS function uses raw HTTP requests to OpenAI API, not the SDK:
```python
# Current code uses requests directly
url = "https://api.openai.com/v1/chat/completions"
response = requests.post(url, headers=headers, ...)
```

**Action**: Remove `openai==1.39.0` from requirements (saves 4 MB + 12 MB dependencies)

### 2. **Twilio is SMS-Only**
26 MB `twilio` package is only used by SMS function.

**Action**: Move to SMS-specific layer

### 3. **Cryptography is JWT Dependency**
22 MB `cryptography` is required for `PyJWT[crypto]` but only needed by Auth and Authorizer.

**Action**: Move to JWT-specific layer

### 4. **Boto3 in Lambda Runtime**
Boto3 is included in Lambda Python runtime - no need to package it.

**Action**: Remove from all layers, use runtime version

---

## Implementation Plan

### Phase 1: Clean Up Current Shared Layer ✅
1. Remove `openai==1.39.0` (not actually used)
2. Remove `exceptiongroup` (not needed for Python 3.9+)
3. Test SMS function still works with raw requests

### Phase 2: Create Specialized Layers ✅

#### Create `lambdas/layers/core/requirements.txt`
```
requests==2.31.0
```

#### Create `lambdas/layers/jwt/requirements.txt`
```
PyJWT[crypto]==2.8.0
cryptography
```

#### Create `lambdas/layers/sms/requirements.txt`
```
twilio>=9.0.0
```

### Phase 3: Update Terraform Configuration ✅

Update `terraform/modules/lambdas/` to:
1. Define three new layer resources (core, jwt, sms)
2. Assign layers to functions:
   - SMS: core + sms layers
   - Auth: core + jwt layers  
   - Authorizer: core + jwt layers
   - Users: no layers
   - CORS: no layers

### Phase 4: Testing & Validation ✅
1. Deploy to dev environment
2. Test each endpoint:
   - [ ] SMS inbound messages
   - [ ] Auth callback flow
   - [ ] Users CRUD operations
   - [ ] JWT authorization
   - [ ] CORS preflight
3. Monitor Lambda metrics (cold start, execution time)

### Phase 5: Cleanup ✅
1. Remove old `lambdas/layer/` directory
2. Update documentation
3. Commit changes to `refactor/lambda-dependencies` branch

---

## File Structure After Refactor

```
lambdas/
├── layers/
│   ├── core/
│   │   └── requirements.txt (requests only)
│   ├── jwt/
│   │   └── requirements.txt (PyJWT[crypto], cryptography)
│   └── sms/
│       └── requirements.txt (twilio)
├── auth/
│   ├── auth_handler.py
│   └── (no deps file - uses layers)
├── users/
│   ├── users_handler.py
│   ├── helpers.py
│   └── (no deps - boto3 from runtime)
├── sms/
│   ├── sms_handler.py
│   ├── helpers.py
│   └── (no deps file - uses layers)
├── authorizer/
│   └── jwt_authorizer.py
└── cors/
    └── cors_handler.py
```

---

## Size Estimates After Refactor

### Layer Sizes (compressed)
- **Core Layer**: ~2 MB
- **JWT Layer**: ~8 MB  
- **SMS Layer**: ~10 MB

### Function Sizes (with layers, uncompressed runtime total)
- **SMS**: ~12 MB (well under limit ✅)
- **Auth**: ~10 MB (well under limit ✅)
- **Users**: <1 MB (well under limit ✅)
- **Authorizer**: ~10 MB (well under limit ✅)
- **CORS**: <1 KB (well under limit ✅)

**Maximum combined size**: ~12 MB << 250 MB limit

---

## Rollback Plan

If issues arise:
1. Revert to dev branch
2. Keep current S3-based SMS deployment (73 MB self-contained)
3. Continue using existing layer configuration

---

## Success Criteria

- [ ] All Lambda functions deploy successfully
- [ ] All functions under 50 MB total (comfortable margin)
- [ ] No layer size limit errors
- [ ] All API endpoints functional
- [ ] Cold start times < 3 seconds
- [ ] No runtime import errors

---

## Next Steps

1. **Review this plan** with team
2. **Start with Phase 1** (cleanup) - lowest risk
3. **Build layers** in Phase 2
4. **Test in dev** before prod deployment
5. **Monitor metrics** after deployment

---

## Questions to Address

1. Do we want to keep AWS Powertools layer for observability?
   - If yes, factor its ~80 MB into calculations
   - If no, remove from all functions

2. Should we consider Lambda container images for SMS?
   - Allows up to 10 GB
   - More flexible dependency management
   - Slightly longer cold starts

3. Python runtime version strategy?
   - Current: mixed (Python 3.9 vs 3.11)
   - Recommendation: standardize on Python 3.11

---

**Document Version**: 1.0  
**Created**: 2025-12-21  
**Branch**: refactor/lambda-dependencies  
**Status**: Planning Complete - Ready for Implementation

