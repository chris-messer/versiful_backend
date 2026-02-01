# Free Trial Implementation - 3 Message Limit for Web Chat

## Overview
Implemented a free trial system that allows non-subscribed users to test the web chat with a 3-message limit per conversation thread, while hiding their conversation history until they subscribe.

## Security Architecture
**Defense in Depth:** Both frontend and backend enforce the limits to provide good UX while maintaining security.

### Frontend Enforcement (UX Layer)
- **Purpose:** Provide immediate feedback and good user experience
- **Location:** `versiful-frontend/src/pages/Chat.jsx`
- **Limitations:** Can be bypassed by savvy users via DevTools

### Backend Enforcement (Security Layer)
- **Purpose:** Actual enforcement - prevents bypassing frontend restrictions
- **Location:** `versiful-backend/lambdas/chat/web_handler.py`
- **Method:** Validates subscription status and message count from DynamoDB before processing

## Changes Made

### Frontend (`versiful-frontend/src/pages/Chat.jsx`)

1. **Free Trial Tracking**
   - Added `FREE_TRIAL_MESSAGE_LIMIT` constant (set to 3)
   - Tracks `userMessageCount` in current thread
   - Reads `user.isSubscribed` from AuthContext

2. **Sidebar Changes for Free Users**
   - Replaces conversation history with a subscription banner
   - Banner includes:
     - Info about 3-message limit
     - "Subscribe Now" CTA button → `/subscription`
     - Reassurance that conversations are saved
   - No session loading for non-subscribed users

3. **Message Input Restrictions**
   - Input disabled when limit reached
   - Placeholder changes to "Subscribe to continue chatting..."
   - Submit button disabled at limit

4. **Visual Feedback**
   - Message counter: "Free trial: X / 3 messages used" (shown between messages 1-2)
   - Warning banner when limit hit (yellow alert box)
   - Clear CTAs to subscribe

5. **Error Handling**
   - Gracefully handles 403 responses from backend
   - Removes optimistically added message if backend rejects

### Backend (`versiful-backend/lambdas/chat/web_handler.py`)

1. **Subscription Validation**
   - Added to `handle_post_message()` function
   - Fetches user info via `get_user_info()` from `chat_handler`
   - Checks `is_subscribed` flag from DynamoDB

2. **Message Counting**
   - For non-subscribed users, retrieves message history
   - Counts only `user` role messages (excludes assistant responses)
   - Enforces 3-message limit per thread

3. **Security Response**
   - Returns 403 Forbidden when limit exceeded
   - Error message: "Free trial limit reached. Please subscribe to continue chatting."
   - Prevents message processing entirely

## User Experience Flow

### Free Trial User (isSubscribed: false)
1. Sign in → Navigate to `/chat`
2. Sidebar shows subscription banner (no history)
3. Can create new conversations
4. Can send up to 3 messages per conversation
5. See message counter: "1 / 3 messages used", "2 / 3 messages used"
6. After 3rd message: Warning banner appears
7. Input disabled, prompts to subscribe
8. Backend blocks any attempts to send more messages (security)

### Subscribed User (isSubscribed: true)
1. Sign in → Navigate to `/chat`
2. Sidebar shows full conversation history
3. Can create unlimited conversations
4. Unlimited messages per conversation
5. No counters or warnings shown
6. All previously hidden conversations become visible

## Testing

### Frontend Testing (localhost)
```bash
cd /Users/christopher.messer/WebstormProjects/versiful-frontend
npm run dev
```

Test scenarios:
1. **Free user flow:**
   - Sign in with user where `isSubscribed: false`
   - Check sidebar shows subscription banner
   - Send 3 messages, observe counter
   - Verify 4th message is blocked by UI
   - Try DevTools manipulation (should be blocked by backend)

2. **Subscribed user flow:**
   - Update user to `isSubscribed: true`
   - Verify sidebar shows history
   - Verify no message limits

### Backend Testing
The backend validation will automatically block free users at the API level, even if they bypass frontend restrictions.

## Database Schema
No schema changes required. Uses existing fields:
- `users` table: `isSubscribed` (boolean), `plan` (string)
- `chat-messages` table: `role` field to count user messages
- `chat-sessions` table: existing structure

## Deployment Notes
1. **Frontend:** Deploy frontend first (backwards compatible)
2. **Backend:** Deploy backend Lambda after testing
3. **No migrations needed:** Uses existing DynamoDB schema

## Security Considerations
✅ **Backend validates all requests** - Cannot be bypassed
✅ **Reads from DynamoDB** - Source of truth for subscription status
✅ **Counts actual messages** - Cannot be spoofed via API
✅ **Returns proper HTTP codes** - 403 for rate limiting
✅ **Frontend provides UX** - But doesn't rely on it for security

## Future Enhancements
- [ ] Track message counts globally (across all threads) for more sophisticated limits
- [ ] Time-based free trials (e.g., "7 days unlimited")
- [ ] Add analytics to track conversion from free → paid
- [ ] A/B test different free trial limits (3 vs 5 vs 10 messages)


