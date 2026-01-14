# Bible Version Preference Feature

## Overview
Users can now specify their preferred Bible version during registration, and this preference is automatically used when the chat agent provides Scripture references in both SMS and Web chat interactions.

## Implementation

### Problem
Previously, users could set a preferred Bible version in their profile during registration, but this preference was never actually used by the chat system. The LLM would respond with verses from various translations without considering the user's preference.

### Solution
Implemented a system to fetch the user's Bible version preference and inject it into the LLM prompt for every chat interaction.

## Changes Made

### 1. Chat Handler (`lambdas/chat/chat_handler.py`)

#### Added Helper Function
```python
def get_user_bible_version(user_id: str) -> Optional[str]:
    """Fetch user's preferred bible version from DynamoDB"""
```

This function queries the users DynamoDB table to retrieve the `bibleVersion` attribute for a given user.

#### Modified `process_chat_message()` Function
- Fetches the user's Bible version preference when `user_id` is available
- For SMS from unregistered users, attempts to look up the user by phone number
- Passes the `bible_version` parameter to the agent service

#### Added Environment Variable
- `USERS_TABLE`: Reference to the users DynamoDB table

### 2. Agent Service (`lambdas/chat/agent_service.py`)

#### Modified `process_message()` Method
- Added `bible_version` parameter to method signature
- Passes bible version to the LLM response generator

#### Modified `_generate_llm_response()` Method
- Added `bible_version` parameter
- When a bible version is specified, appends an instruction to the system prompt:
  ```
  IMPORTANT: When citing Bible verses, always use the {bible_version} translation. 
  The user has specifically requested this version.
  ```
- This instruction is injected dynamically for each request, ensuring the LLM uses the correct translation

### 3. Agent Configuration (`lambdas/chat/agent_config.yaml`)

#### Updated System Prompts
Both the main `system_prompt` and `sms_system_prompt` now include guidance about Bible translations:

```yaml
- When quoting Scripture, use the Bible translation the user has requested. If they have 
  specified a preferred version (like KJV, NIV, ESV, etc.), always cite verses from that 
  version. This is important to them.
```

This provides baseline guidance to the LLM, which is then reinforced with the dynamic injection when a specific version is provided.

### 4. Terraform Configuration (`terraform/modules/lambdas/_chat.tf`)

#### Added Environment Variable
Added `USERS_TABLE` to the Chat Lambda's environment variables:
```hcl
USERS_TABLE = "${var.environment}-${var.project_name}-users"
```

This allows the Chat Lambda to access the users table to fetch Bible version preferences.

## How It Works

### Flow Diagram

```
User sends message (SMS or Web)
    ↓
SMS Handler / Web Handler invokes Chat Handler
    ↓
Chat Handler:
  1. Extracts user_id from event
  2. Calls get_user_bible_version(user_id)
  3. DynamoDB query to users table
  4. Retrieves bibleVersion attribute
    ↓
Agent Service:
  1. Receives bible_version parameter
  2. If bible_version exists:
     - Appends "IMPORTANT: Use {bible_version}" to system prompt
  3. Sends prompt + history to OpenAI
    ↓
OpenAI returns response with verses in requested translation
    ↓
Response saved and returned to user
```

### SMS Flow
For SMS users:
1. SMS Handler receives message with phone number
2. Invokes Chat Handler with `phone_number` and `user_id` (if known)
3. Chat Handler:
   - If `user_id` provided, fetches bible version directly
   - If no `user_id`, scans users table by phone number to find user and their preference
4. Preference used in LLM prompt

### Web Flow
For web users:
1. Web Handler receives message with JWT token
2. Extracts `user_id` from authorizer context
3. Invokes Chat Handler with `user_id` and `session_id`
4. Chat Handler fetches bible version for that user
5. Preference used in LLM prompt

## Supported Bible Versions

The system supports any Bible version the user specifies. Common versions include:
- KJV (King James Version)
- NIV (New International Version)
- ESV (English Standard Version)
- NKJV (New King James Version)
- NLT (New Living Translation)
- NASB (New American Standard Bible)
- And many others...

See `versiful-frontend/src/constants/bibleVersions.jsx` for the full list available in the registration form.

## Database Schema

### Users Table
The users table contains:
```
userId (PK)
bibleVersion: String (e.g., "KJV", "NIV")
phoneNumber: String
firstName: String
lastName: String
... other fields ...
```

Users set their `bibleVersion` during registration via the Welcome Form or can update it in Settings.

## IAM Permissions

The Chat Lambda already has DynamoDB read permissions on the users table through the `dynamodb_access` IAM policy attached to the Lambda execution role:

```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:Query",
    "dynamodb:Scan"
  ],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/${environment}-${project_name}-users",
    "arn:aws:dynamodb:*:*:table/${environment}-${project_name}-users/*"
  ]
}
```

## Testing

### Manual Testing

#### Test Web Chat Flow
1. Log in to the web application
2. Go to Settings → Personalization
3. Change Bible version (e.g., to "NIV")
4. Go to Chat page
5. Send a message asking for a Bible verse (e.g., "I'm feeling anxious")
6. Verify the response includes verses cited in NIV format
7. Change Bible version to KJV in Settings
8. Send another message in a new chat session
9. Verify verses are now in KJV format

#### Test SMS Flow
1. Ensure a user is registered with a phone number and Bible version set
2. Send an SMS to the Versiful number
3. Check CloudWatch logs for the Chat Lambda
4. Verify log shows: "Using bible version {VERSION} for user {USER_ID}"
5. Verify the SMS response contains verses in the requested version

### Automated Testing

#### Unit Tests
```python
# Test get_user_bible_version()
def test_get_user_bible_version():
    user_id = "test-user-123"
    version = get_user_bible_version(user_id)
    assert version == "KJV"

# Test process_chat_message() with bible version
def test_process_chat_with_bible_version():
    result = process_chat_message(
        thread_id="test-thread",
        message="I need encouragement",
        channel="web",
        user_id="test-user-123"
    )
    assert result['success'] == True
    # Verify logs show bible version was fetched and used
```

#### Integration Tests
```python
# Test end-to-end SMS flow with bible version
def test_sms_with_bible_version():
    # Setup: Create test user with NIV preference
    # Send SMS message
    # Verify response contains NIV verse
    pass

# Test end-to-end web flow with bible version
def test_web_chat_with_bible_version():
    # Setup: Create session with user who has ESV preference
    # Send chat message
    # Verify response contains ESV verse
    pass
```

## Deployment

### Deployment Steps
1. **Backend Changes**:
   ```bash
   cd terraform
   terraform plan -var-file=dev.tfvars
   terraform apply -var-file=dev.tfvars
   ```
   This will:
   - Update the Chat Lambda with new code
   - Add USERS_TABLE environment variable
   - Deploy changes to AWS

2. **Verify Deployment**:
   - Check Lambda environment variables in AWS Console
   - Verify USERS_TABLE is set correctly
   - Test with a known user account

3. **Monitor**:
   - Check CloudWatch logs for bible version fetch messages
   - Monitor for any errors related to DynamoDB access

## Rollback Plan

If issues occur:
1. Revert code changes in `chat_handler.py` and `agent_service.py`
2. Redeploy Lambda:
   ```bash
   terraform apply -var-file=dev.tfvars
   ```
3. The system will fall back to default behavior (no bible version preference)

## Future Enhancements

### Possible Improvements
1. **Caching**: Cache user preferences in Lambda memory to reduce DynamoDB calls
2. **Default Version**: Set a system-wide default Bible version for users who haven't specified
3. **Version Validation**: Validate that the user's preferred version exists/is supported
4. **Parallel Versions**: Allow users to see verses in multiple translations side-by-side
5. **Analytics**: Track which Bible versions are most popular among users
6. **Smart Fallback**: If LLM doesn't have a specific translation, gracefully fall back to a common one

## Performance Impact

### Minimal Overhead
- **DynamoDB Query**: ~10-20ms per request
- **User Lookup by Phone**: ~50-100ms (only for unregistered SMS users)
- **Memory**: No significant impact, bible version is just a string
- **Cost**: Negligible (DynamoDB queries are very cheap)

### Optimization Opportunities
If performance becomes a concern:
1. Cache user preferences in Lambda global scope
2. Use DynamoDB GetItem instead of Scan for phone lookups (requires GSI)
3. Pass bible version from SMS/Web handlers if they already have user data

## Troubleshooting

### Common Issues

**Issue**: Bible version not being applied
- **Check**: CloudWatch logs for "Using bible version X for user Y"
- **Fix**: Verify user has bibleVersion set in DynamoDB

**Issue**: DynamoDB access denied
- **Check**: Lambda execution role has dynamodb:GetItem permission
- **Fix**: Verify IAM policy includes users table ARN

**Issue**: Phone number lookup failing for SMS
- **Check**: CloudWatch logs for "Error looking up user by phone"
- **Fix**: Verify phone number normalization matches what's in DynamoDB

**Issue**: LLM not respecting version preference
- **Check**: The prompt injection is working (logs show bible version)
- **Note**: LLM may occasionally use wrong version; this is a model limitation
- **Workaround**: Could add post-processing to verify version, but may be overkill

## Documentation References

- User Registration: `versiful-frontend/src/components/welcome/WelcomeForm.jsx`
- Bible Versions List: `versiful-frontend/src/constants/bibleVersions.jsx`
- Settings Page: `versiful-frontend/src/components/settings/PersonalizationSettings.jsx`
- Chat Architecture: `docs/LANGCHAIN_CHAT_IMPLEMENTATION.md`
- Users Lambda: `lambdas/users/users_handler.py`

