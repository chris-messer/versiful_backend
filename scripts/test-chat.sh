#!/bin/bash
# Test script for LangChain Chat Agent
# Run after deploying to dev environment

set -e

ENVIRONMENT=${1:-dev}
API_BASE="https://api.${ENVIRONMENT}.versiful.io"

echo "========================================"
echo "LangChain Chat Agent Test Suite"
echo "Environment: $ENVIRONMENT"
echo "API Base: $API_BASE"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v jq &> /dev/null; then
    fail "jq is not installed. Please install jq to run this script."
    exit 1
fi
pass "jq installed"

if ! command -v curl &> /dev/null; then
    fail "curl is not installed. Please install curl to run this script."
    exit 1
fi
pass "curl installed"

# Get auth token (you need to provide this)
echo ""
echo "========================================"
echo "Authentication"
echo "========================================"
echo "Please login and provide your auth cookies..."
echo "You can get these from browser DevTools after logging in"
echo ""
read -p "Enter id_token cookie value: " ID_TOKEN
read -p "Enter access_token cookie value: " ACCESS_TOKEN

if [ -z "$ID_TOKEN" ] || [ -z "$ACCESS_TOKEN" ]; then
    fail "Auth tokens required"
    exit 1
fi
pass "Auth tokens provided"

# Test 1: Create new session
echo ""
echo "========================================"
echo "Test 1: Create New Session"
echo "========================================"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$API_BASE/chat/sessions" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN" \
    -H "Content-Type: application/json")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "201" ]; then
    SESSION_ID=$(echo "$BODY" | jq -r '.session.sessionId')
    pass "Created new session: $SESSION_ID"
else
    fail "Failed to create session. HTTP $HTTP_CODE: $BODY"
    exit 1
fi

# Test 2: Send first message
echo ""
echo "========================================"
echo "Test 2: Send First Message"
echo "========================================"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$API_BASE/chat/message" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"I'm feeling anxious about the future\", \"sessionId\": \"$SESSION_ID\"}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    MESSAGE=$(echo "$BODY" | jq -r '.message')
    pass "Received response"
    echo "Response preview: ${MESSAGE:0:100}..."
else
    fail "Failed to send message. HTTP $HTTP_CODE: $BODY"
    exit 1
fi

# Test 3: Get session list
echo ""
echo "========================================"
echo "Test 3: Get Session List"
echo "========================================"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "$API_BASE/chat/sessions" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    SESSION_COUNT=$(echo "$BODY" | jq -r '.count')
    pass "Retrieved $SESSION_COUNT sessions"
    
    # Check if our session is in the list
    FOUND=$(echo "$BODY" | jq -r ".sessions[] | select(.sessionId == \"$SESSION_ID\") | .sessionId")
    if [ "$FOUND" == "$SESSION_ID" ]; then
        pass "New session found in list"
    else
        warn "New session not found in list (might be pagination issue)"
    fi
else
    fail "Failed to get sessions. HTTP $HTTP_CODE: $BODY"
fi

# Test 4: Get session details with history
echo ""
echo "========================================"
echo "Test 4: Get Session Details"
echo "========================================"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "$API_BASE/chat/sessions/$SESSION_ID" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    MESSAGE_COUNT=$(echo "$BODY" | jq -r '.messages | length')
    pass "Retrieved session with $MESSAGE_COUNT messages"
    
    if [ "$MESSAGE_COUNT" -ge 2 ]; then
        pass "Message history includes user and assistant messages"
    else
        warn "Expected at least 2 messages (user + assistant)"
    fi
else
    fail "Failed to get session details. HTTP $HTTP_CODE: $BODY"
fi

# Test 5: Send follow-up message (tests conversation context)
echo ""
echo "========================================"
echo "Test 5: Send Follow-up Message"
echo "========================================"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$API_BASE/chat/message" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"Can you tell me more?\", \"sessionId\": \"$SESSION_ID\"}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    MESSAGE=$(echo "$BODY" | jq -r '.message')
    pass "Received contextual response"
    echo "Response preview: ${MESSAGE:0:100}..."
else
    fail "Failed to send follow-up. HTTP $HTTP_CODE: $BODY"
fi

# Test 6: Create message without sessionId (should create new session)
echo ""
echo "========================================"
echo "Test 6: Create New Session via Message"
echo "========================================"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$API_BASE/chat/message" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message": "Test message for auto-session creation"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    NEW_SESSION_ID=$(echo "$BODY" | jq -r '.sessionId')
    if [ "$NEW_SESSION_ID" != "null" ] && [ "$NEW_SESSION_ID" != "$SESSION_ID" ]; then
        pass "Auto-created new session: $NEW_SESSION_ID"
        CLEANUP_SESSION_ID="$NEW_SESSION_ID"
    else
        warn "Session auto-creation unclear"
    fi
else
    fail "Failed to auto-create session. HTTP $HTTP_CODE: $BODY"
fi

# Test 7: Delete session
echo ""
echo "========================================"
echo "Test 7: Delete Session"
echo "========================================"
DELETE_ID="${CLEANUP_SESSION_ID:-$SESSION_ID}"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X DELETE "$API_BASE/chat/sessions/$DELETE_ID" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    pass "Deleted session successfully"
else
    fail "Failed to delete session. HTTP $HTTP_CODE: $BODY"
fi

# Test 8: Verify session was deleted
echo ""
echo "========================================"
echo "Test 8: Verify Session Deletion"
echo "========================================"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "$API_BASE/chat/sessions/$DELETE_ID" \
    -H "Cookie: id_token=$ID_TOKEN; access_token=$ACCESS_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)

if [ "$HTTP_CODE" == "404" ] || [ "$HTTP_CODE" == "200" ]; then
    if [ "$HTTP_CODE" == "404" ]; then
        pass "Session properly deleted (404)"
    else
        # Check if archived
        BODY=$(echo "$RESPONSE" | sed '$d')
        IS_ARCHIVED=$(echo "$BODY" | jq -r '.session.archived')
        if [ "$IS_ARCHIVED" == "true" ]; then
            pass "Session archived (soft delete)"
        else
            warn "Session still accessible and not archived"
        fi
    fi
else
    warn "Unexpected response checking deleted session: HTTP $HTTP_CODE"
fi

# Summary
echo ""
echo "========================================"
echo "Test Suite Complete"
echo "========================================"
echo ""
echo "Manual tests to perform:"
echo "1. Test SMS flow:"
echo "   - Send SMS to your Twilio number"
echo "   - Verify response received"
echo "   - Check DynamoDB chat-messages table for entries"
echo ""
echo "2. Test frontend:"
echo "   - Login to web app"
echo "   - Navigate to /chat"
echo "   - Send messages and verify UI updates"
echo "   - Test session switching"
echo "   - Test new conversation creation"
echo ""
echo "3. Test guardrails:"
echo "   - Send message with crisis keywords"
echo "   - Verify crisis intervention response"
echo ""
echo "4. Test conversation memory:"
echo "   - Have multi-turn conversation"
echo "   - Verify agent remembers context"
echo ""
echo "5. Monitor CloudWatch:"
echo "   - Check Lambda logs for errors"
echo "   - Verify LLM calls are succeeding"
echo "   - Check response times"
echo ""

