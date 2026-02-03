# PostHog User Tracking Implementation Plan

## Date
2026-02-03

## Goal
Implement proper PostHog user identification across all channels (web, SMS) using stable user IDs with searchable person properties.

---

## ID Strategy Overview

### Primary Identifier: `userId` (DynamoDB UUID)
**Format:** `019c200b-f248-7253-8869-e0dc2fe874e6`

**Why:**
- ✅ Immutable - never changes even if user updates email or phone
- ✅ Consistent across all channels (web, SMS, future)
- ✅ Matches DynamoDB primary key
- ✅ PostHog best practice for stable identification

### Person Properties (Searchable in PostHog)
```javascript
{
  email: "user@example.com",
  phone_number: "+15551234567",
  first_name: "John",
  last_name: "Doe",
  plan: "free|paid",
  is_subscribed: true|false,
  bible_version: "KJV",
  response_style: "conversational",
  registration_status: "registered|unregistered",
  channel: "web|sms",
  created_at: "2024-01-15T10:30:00Z"
}
```

**Benefits:**
- Search by email: `email = "user@example.com"`
- Search by phone: `phone_number = "+15551234567"`
- Filter by plan: `is_subscribed = true`
- Human-readable in PostHog dashboard

---

## User Journeys

### Journey 1: Web User Signs Up

```
1. Landing Page (Anonymous)
   distinct_id: auto-generated UUID by PostHog (e.g., "018d-xxxx-xxxx")
   Events: pageview, button clicks
   
2. User Signs Up (Email/Password or OAuth)
   a. Backend creates user → returns userId (DynamoDB UUID)
   b. Frontend calls:
      posthog.identify(userId, {
        email: "user@example.com",
        first_name: "John",
        plan: "free",
        is_subscribed: false,
        registration_status: "registered",
        channel: "web"
      })
   c. Link anonymous events:
      const anonymousId = posthog.get_distinct_id();
      posthog.alias(userId, anonymousId);
   
3. All Future Events
   distinct_id: userId
   All events automatically tagged with email, phone (if added), etc.
```

### Journey 2: Unregistered User Texts Service

```
1. First Text (No Account)
   Phone: +15551234567
   
   Backend logic:
   a. Check sms-usage table → no userId found
   b. Create PostHog identity:
      distinct_id: "anon_sms_5551234567"
      
   c. Set person properties:
      posthog.identify("anon_sms_5551234567", {
        phone_number: "+15551234567",
        registration_status: "unregistered",
        channel: "sms",
        first_seen_at: "2024-01-15T10:30:00Z"
      })
   
   d. All LLM traces use this distinct_id
   
2. User Registers on Web Later
   a. User signs up at versiful.io
   b. User adds phone number in welcome form
   c. Backend links SMS history:
      posthog.alias(userId, "anon_sms_5551234567")
   
   Result: All past SMS events now appear under user's profile!
```

### Journey 3: Registered User Texts Service

```
1. Text from Known Phone
   Phone: +15551234567
   
   Backend logic:
   a. Check sms-usage table → userId found!
   b. Fetch user profile from DynamoDB
   c. Use real userId as distinct_id:
      distinct_id: "019c200b-f248-7253-8869-e0dc2fe874e6"
      
   d. Ensure person properties are current:
      posthog.identify(userId, {
        email: "user@example.com",
        phone_number: "+15551234567",
        first_name: "John",
        last_name: "Doe",
        plan: "free",
        is_subscribed: false,
        bible_version: "KJV",
        registration_status: "registered",
        channel: "sms"
      })
   
   e. All LLM traces use userId as distinct_id
   
Result: SMS events appear alongside web events in same user profile!
```

### Journey 4: User Texts First, Then Registers

```
1. Day 1: Text from +15551234567 (unregistered)
   distinct_id: "anon_sms_5551234567"
   Properties: { phone_number: "+15551234567", registration_status: "unregistered" }
   Events: 5 SMS conversations
   
2. Day 3: User registers on web with different phone initially
   distinct_id: userId "019c..."
   Properties: { email: "user@example.com", phone_number: "+15559999999" }
   Events: web pageviews, account creation
   
3. Day 5: User updates phone to +15551234567
   Backend detects phone was used for SMS before
   Backend calls: posthog.alias(userId, "anon_sms_5551234567")
   
Result: All 5 SMS conversations from Day 1 now merged into user profile!
```

---

## Implementation Details

### Frontend Changes

#### 1. SignIn.jsx & Callback.jsx
```javascript
// After successful login/signup
if (userData && posthog) {
  const userId = userData.userId;
  const anonymousId = posthog.get_distinct_id();
  
  // Identify user with full profile
  posthog.identify(userId, {
    email: userData.email,
    phone_number: userData.phoneNumber, // if exists
    first_name: userData.firstName,
    last_name: userData.lastName,
    plan: userData.plan || 'free',
    is_subscribed: userData.isSubscribed || false,
    bible_version: userData.bibleVersion,
    registration_status: 'registered',
    channel: 'web',
    created_at: userData.createdAt
  });
  
  // Link anonymous events ONLY if this was a new signup
  if (anonymousId !== userId && anonymousId.includes('-')) {
    console.log('Linking anonymous web events to user');
    posthog.alias(userId, anonymousId);
  }
}
```

#### 2. WelcomeForm.jsx (Phone Number Added)
```javascript
// After user adds phone number
if (posthog && userData && userData.userId && phoneNumber) {
  const phoneDigits = phoneNumber.replace(/\D/g, '');
  const anonSmsId = `anon_sms_${phoneDigits}`;
  
  // Check if this phone was used for SMS before registration
  // If so, link those events
  console.log('Linking potential SMS history to user account');
  posthog.alias(userData.userId, anonSmsId);
  
  // Update person properties with phone
  posthog.identify(userData.userId, {
    phone_number: phoneNumber,
    // ... other properties
  });
}
```

#### 3. AuthContext.jsx (On Page Load for Logged-In Users)
```javascript
// When checking login state (don't alias here, just update properties)
if (userData && posthog) {
  posthog.identify(userData.userId, {
    email: userData.email,
    phone_number: userData.phoneNumber,
    first_name: userData.firstName,
    last_name: userData.lastName,
    plan: userData.plan || 'free',
    is_subscribed: userData.isSubscribed || false,
    bible_version: userData.bibleVersion,
    registration_status: 'registered',
    channel: 'web'
  });
}
```

### Backend Changes

#### 1. sms_handler.py
```python
import re
from posthog import Posthog

# Initialize PostHog
posthog = Posthog(
    os.environ.get('POSTHOG_API_KEY'),
    host='https://us.i.posthog.com'
)

def _identify_sms_user(phone_number: str, user_id: str = None, user_profile: dict = None):
    """
    Identify user in PostHog for SMS activity
    
    Args:
        phone_number: Full phone number (e.g., "+15551234567")
        user_id: DynamoDB userId if registered
        user_profile: Full user profile from DynamoDB
    
    Returns:
        distinct_id to use for PostHog events
    """
    phone_digits = re.sub(r'\D', '', phone_number)  # e.g., "5551234567"
    
    if user_id and user_profile:
        # REGISTERED USER
        distinct_id = user_id
        
        properties = {
            'email': user_profile.get('email'),
            'phone_number': phone_number,
            'first_name': user_profile.get('firstName'),
            'last_name': user_profile.get('lastName'),
            'plan': user_profile.get('plan', 'free'),
            'is_subscribed': user_profile.get('isSubscribed', False),
            'bible_version': user_profile.get('bibleVersion'),
            'registration_status': 'registered',
            'channel': 'sms',
        }
        
        logger.info(f"Identifying registered SMS user: {user_id}")
    else:
        # UNREGISTERED USER
        distinct_id = f"anon_sms_{phone_digits}"
        
        properties = {
            'phone_number': phone_number,
            'registration_status': 'unregistered',
            'channel': 'sms',
            'first_seen_at': datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Identifying unregistered SMS user: {distinct_id}")
    
    # Identify in PostHog
    try:
        posthog.identify(
            distinct_id=distinct_id,
            properties=properties
        )
    except Exception as e:
        logger.error(f"Failed to identify user in PostHog: {str(e)}")
    
    return distinct_id

def handler(event, context):
    # ... existing code ...
    
    # After evaluating usage
    decision = _evaluate_usage(from_num_normalized)
    user_id = decision.get("user_profile", {}).get("userId") if decision.get("user_profile") else None
    user_profile = decision.get("user_profile")
    
    # Identify user in PostHog
    distinct_id = _identify_sms_user(from_num_normalized, user_id, user_profile)
    
    # Pass distinct_id to chat handler
    chat_result = _invoke_chat_handler(
        thread_id=from_num_normalized,
        message=body,
        user_id=user_id,
        phone_number=from_num_normalized,
        posthog_distinct_id=distinct_id  # NEW PARAMETER
    )
    
    # ... rest of handler ...
```

#### 2. agent_service.py
```python
def _create_posthog_callback(
    self,
    thread_id: str,
    channel: str,
    phone_number: str = None,
    user_id: str = None,
    posthog_distinct_id: str = None,  # NEW PARAMETER
    trace_id: str = None
) -> Optional[CallbackHandler]:
    """
    Create a PostHog CallbackHandler with proper user identification
    
    Args:
        thread_id: Thread identifier
        channel: "sms" or "web"
        phone_number: Phone number for SMS
        user_id: User ID (DynamoDB UUID) for registered users
        posthog_distinct_id: Pre-computed distinct_id from sms_handler
        trace_id: Trace ID
    """
    if not self.posthog:
        return None
    
    # Determine session_id based on channel
    if channel == 'sms' and phone_number:
        session_id = re.sub(r'\D', '', phone_number)
    elif channel == 'web' and thread_id:
        session_id = thread_id
    else:
        session_id = thread_id
    
    # Use provided distinct_id or determine from user_id
    if posthog_distinct_id:
        distinct_id = posthog_distinct_id
    elif user_id:
        distinct_id = user_id
    else:
        # Fallback for web anonymous users
        distinct_id = None  # Let PostHog auto-generate
    
    try:
        callback_handler = CallbackHandler(
            client=self.posthog,
            distinct_id=distinct_id,  # Now properly set!
            trace_id=trace_id,
            properties={
                "conversation_id": session_id,
                "$ai_session_id": session_id,
                "channel": channel
            },
            privacy_mode=False
        )
        logger.info(
            f"Created PostHog callback - trace_id: {trace_id}, conversation_id: {session_id}, "
            f"distinct_id: {distinct_id}, channel: {channel}"
        )
        return callback_handler
    except Exception as e:
        logger.error(f"Failed to create PostHog callback handler: {str(e)}")
        return None
```

#### 3. users/helpers.py (Link SMS to User)
```python
from posthog import Posthog
import re

def link_sms_history_to_user(phone_number: str, user_id: str):
    """
    Link any previous SMS activity to a newly registered user
    
    Called when:
    - User adds phone number to their account
    - User registers with a phone that was previously used
    
    Args:
        phone_number: Full phone number (e.g., "+15551234567")
        user_id: DynamoDB userId
    """
    try:
        posthog = Posthog(
            os.environ.get('POSTHOG_API_KEY'),
            host='https://us.i.posthog.com'
        )
        
        phone_digits = re.sub(r'\D', '', phone_number)
        anon_sms_id = f"anon_sms_{phone_digits}"
        
        logger.info(f"Linking SMS history from {anon_sms_id} to user {user_id}")
        
        # Alias anonymous SMS events to user account
        posthog.alias(
            distinct_id=user_id,
            alias=anon_sms_id
        )
        
        logger.info(f"Successfully linked SMS history to user {user_id}")
        
        # Flush to ensure alias is sent
        posthog.flush()
        
    except Exception as e:
        logger.error(f"Failed to link SMS history: {str(e)}")

# Call this in ensure_sms_usage_record after linking phone to userId
def ensure_sms_usage_record(phone_number: str, user_id: str):
    # ... existing DynamoDB logic ...
    
    # Link any SMS history to this user
    link_sms_history_to_user(phone_number, user_id)
```

---

## PostHog Usage Examples

### Find User by Email
```
PostHog Dashboard → People → Filter:
email = "user@example.com"
```

### Find User by Phone
```
PostHog Dashboard → People → Filter:
phone_number = "+15551234567"
```

### View All Unregistered SMS Users
```
Filter:
registration_status = "unregistered"
AND channel = "sms"
```

### View User's Complete Journey
```
1. Search for user by email or phone
2. Click on their profile
3. See all events: web pageviews, SMS conversations, LLM traces
4. All linked via userId as distinct_id
```

---

## Testing Plan

### Test 1: New Web Signup
1. Visit site anonymously (note PostHog ID in console)
2. Sign up with email
3. Check PostHog: Should see user with userId, email property, and linked anonymous events

### Test 2: Unregistered SMS User
1. Text from new number: +15551111111
2. Check PostHog: Should see `anon_sms_5551111111` with phone_number property
3. Verify LLM traces are tagged to this ID

### Test 3: SMS Then Register
1. Text from +15552222222 (unregistered)
2. Register on web, add phone +15552222222
3. Check PostHog: SMS events should now appear under userId

### Test 4: Registered User Texts
1. Register on web with email
2. Add phone +15553333333
3. Text from +15553333333
4. Check PostHog: SMS traces should use userId, same profile as web events

---

## Implementation Order

1. ✅ **Backend SMS identification** (sms_handler.py)
2. ✅ **Backend LLM tracing** (agent_service.py)
3. ✅ **Backend SMS history linking** (users/helpers.py)
4. ✅ **Frontend signup identification** (SignIn.jsx, Callback.jsx)
5. ✅ **Frontend phone linking** (WelcomeForm.jsx)
6. ✅ **Testing & validation**

---

## Benefits Summary

✅ **Stable Identity**: Use UUID, never lose track of users  
✅ **Cross-Channel Tracking**: Same userId for web + SMS  
✅ **Human-Readable**: Search by email/phone in PostHog  
✅ **Anonymous SMS Support**: Unregistered users can text and upgrade later  
✅ **Historical Linking**: SMS events before registration are preserved  
✅ **Future-Proof**: Can add more channels (mobile app, etc.) using same ID

---

## Next Steps

Ready to implement? I can help with:
1. Update backend SMS handler with identification logic
2. Update agent_service to accept distinct_id parameter
3. Update frontend identification with proper aliasing
4. Add SMS history linking when phone is added
5. Test the complete flow

What would you like to tackle first?

