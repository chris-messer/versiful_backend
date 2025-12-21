# Lambda Deployment Strategy - Zip-Based Direct Upload

## Overview

All Versiful lambdas will be deployed using **direct zip upload** (not S3) as all functions are well under the 50 MB limit.

## Current State Analysis

### Lambda Size Limits
- **Direct Zip Upload**: 50 MB limit (what we'll use ✅)
- **S3 Upload**: 250 MB uncompressed limit
- **Combined Code + Layers**: 250 MB uncompressed limit

### Current Function Sizes

| Function | Code Size | Deployment Method | Status |
|----------|-----------|-------------------|--------|
| SMS | ~36 KB | Direct Zip | ✅ Works |
| Auth | ~20 KB | Direct Zip | ✅ Works |
| Users | ~15 KB | Direct Zip | ✅ Works |
| Authorizer | ~10 KB | Direct Zip | ✅ Works |
| CORS | ~1 KB | Direct Zip | ✅ Works |

**All functions are tiny without dependencies!** The issue was trying to add layers that exceeded the combined limit.

## Refactoring Strategy

### Phase 1: Deploy Without Layers (IMMEDIATE)
Remove all layers temporarily and verify functions work with bundled dependencies.

```hcl
resource "aws_lambda_function" "sms_function" {
  function_name    = "${var.environment}-sms_function"
  handler          = "sms_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.sms_zip.output_path
  source_code_hash = data.archive_file.sms_zip.output_base64sha256
  # NO LAYERS - will be added after refactor
  timeout          = 30
}
```

**Expected Result**: All functions deploy and work (they did before we added the layer)

### Phase 2: Create Right-Sized Layers

After confirming Phase 1 works, create optimized layers:

#### Layer 1: Core Dependencies (~2 MB compressed)
```txt
requests==2.31.0
```
**Used by**: SMS, Auth, Authorizer

#### Layer 2: JWT Dependencies (~8 MB compressed)
```txt
PyJWT[crypto]==2.8.0
cryptography
```
**Used by**: Auth, Authorizer

#### Layer 3: SMS Dependencies (~10 MB compressed)
```txt
twilio>=9.0.0
```
**Used by**: SMS only

### Phase 3: Gradual Layer Addition

Add layers one at a time, testing after each:

1. **Test Core Layer**: Add to Auth function first (smallest)
   - Deploy, test, verify size < 250 MB
   
2. **Test JWT Layer**: Add to Auth function
   - Deploy, test, verify size < 250 MB
   
3. **Test SMS Layer**: Add core + sms to SMS function
   - Deploy, test, verify size < 250 MB

## Deployment Size Projections

### Without Layers (Phase 1)
```
SMS:        36 KB code only        = 36 KB      ✅
Auth:       20 KB code only        = 20 KB      ✅
Users:      15 KB code only        = 15 KB      ✅
Authorizer: 10 KB code only        = 10 KB      ✅
CORS:        1 KB code only        =  1 KB      ✅
```

### With Optimized Layers (Phase 3)
```
SMS:        36 KB + 2 MB + 10 MB   = ~12 MB     ✅ << 250 MB
Auth:       20 KB + 2 MB + 8 MB    = ~10 MB     ✅ << 250 MB
Users:      15 KB + 0 layers       = ~15 KB     ✅ << 250 MB
Authorizer: 10 KB + 2 MB + 8 MB    = ~10 MB     ✅ << 250 MB
CORS:        1 KB + 0 layers       =  ~1 KB     ✅ << 250 MB
```

## Key Optimizations Discovered

### 1. OpenAI SDK Not Needed ⚡
The SMS function uses raw `requests.post()` to call OpenAI API, not the SDK:

```python
# Current implementation - NO openai SDK needed!
url = "https://api.openai.com/v1/chat/completions"
response = requests.post(url, headers=headers, data=json.dumps(data))
```

**Savings**: 4 MB + 12 MB dependencies (pydantic, aiohttp, etc.) = **16 MB saved**

### 2. Twilio is SMS-Only 🎯
26 MB `twilio` package only used by SMS function.

**Action**: Separate SMS layer - don't burden other functions

### 3. Cryptography is JWT-Only 🔐
22 MB `cryptography` only needed by Auth and Authorizer (PyJWT dependency).

**Action**: Separate JWT layer - Users and CORS don't need it

### 4. Boto3 in Runtime 🏃
Boto3 included in Lambda Python runtime - don't need to package it.

**Action**: Remove from all requirements.txt files

## Terraform Configuration Changes

### Before (Problematic)
```hcl
layers = [
  aws_lambda_layer_version.shared_dependencies.arn,           # 17 MB compressed, 220 MB uncompressed
  "arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python39-x86_64:6"  # ~80 MB uncompressed
]
# Total: ~306 MB > 250 MB limit ❌
```

### After (Optimized)
```hcl
# SMS Function
layers = [
  aws_lambda_layer_version.core.arn,    # ~2 MB uncompressed
  aws_lambda_layer_version.sms.arn      # ~10 MB uncompressed
]
# Total: ~12 MB << 250 MB limit ✅

# Auth Function  
layers = [
  aws_lambda_layer_version.core.arn,    # ~2 MB uncompressed
  aws_lambda_layer_version.jwt.arn      # ~8 MB uncompressed
]
# Total: ~10 MB << 250 MB limit ✅
```

## Testing Checklist

### Phase 1 Testing (No Layers)
- [ ] SMS function receives and responds to messages
- [ ] Auth callback flow completes successfully
- [ ] Users CRUD operations work
- [ ] JWT authorization validates correctly
- [ ] CORS preflight responds properly

### Phase 2 Testing (With Layers)
- [ ] Core layer imports work (requests)
- [ ] JWT layer imports work (PyJWT, cryptography)
- [ ] SMS layer imports work (twilio)
- [ ] No import errors in CloudWatch logs
- [ ] Cold start times acceptable (< 5 seconds)
- [ ] No "exceeds maximum size" errors

## Rollback Procedure

If any phase fails:

1. **Phase 1 failure**: Revert to dev branch
2. **Phase 2/3 failure**: Keep Phase 1 (no layers) - still functional
3. Emergency: All functions work without layers (current approach)

## File Structure

### Current (To Clean Up)
```
lambdas/
├── layer/                           # ❌ TOO LARGE - will delete
│   ├── requirements.txt
│   ├── layer.zip (22 MB)
│   └── python/ (76 MB uncompressed)
```

### After Refactor
```
lambdas/
├── layers/
│   ├── core/
│   │   ├── requirements.txt         # requests only
│   │   └── python/ (built by TF)
│   ├── jwt/
│   │   ├── requirements.txt         # PyJWT[crypto], cryptography
│   │   └── python/ (built by TF)
│   └── sms/
│       ├── requirements.txt         # twilio
│       └── python/ (built by TF)
├── auth/
│   └── auth_handler.py              # Direct zip upload
├── users/
│   ├── users_handler.py             # Direct zip upload
│   └── helpers.py
├── sms/
│   ├── sms_handler.py               # Direct zip upload
│   └── helpers.py
├── authorizer/
│   └── jwt_authorizer.py            # Direct zip upload
└── cors/
    └── cors_handler.py              # Direct zip upload
```

## Python Runtime Strategy

**Recommendation**: Standardize on **Python 3.11** for all functions

- Better performance
- Improved error messages
- Consistent runtime environment
- Latest boto3 version

**Current Status**: Mixed (some 3.9, some 3.11) - will standardize

## Success Metrics

- ✅ All functions < 50 MB total (code + layers)
- ✅ No S3 deployment needed
- ✅ Deploy time < 30 seconds per function
- ✅ Cold start < 3 seconds
- ✅ No import errors
- ✅ All endpoints functional

## Next Actions

1. ✅ Created refactor branch: `refactor/lambda-dependencies`
2. ⏳ Remove layers from SMS function config (in progress)
3. ⏳ Test SMS deployment without layers
4. ⏳ Apply terraform to dev
5. ⏳ Verify all endpoints work
6. ⏳ Create new layer structure
7. ⏳ Gradually add back optimized layers

---

**Branch**: `refactor/lambda-dependencies`  
**Status**: Phase 1 - Remove Layers  
**Risk Level**: Low (can always revert to no layers)  
**Expected Completion**: 1-2 hours

