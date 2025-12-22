#!/bin/bash

# Test chat API endpoints
API_BASE="https://api.dev.versiful.io"

echo "Testing chat endpoints..."
echo ""

# Get test user credentials
TEST_EMAIL="${1:-testuser12345@example.com}"
TEST_PASSWORD="${2:-abc.12345!}"

echo "1. Logging in with test user..."
LOGIN_RESPONSE=$(curl -s -c cookies.txt -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

echo "Login response: $LOGIN_RESPONSE"
echo ""

echo "2. Testing GET /chat/sessions..."
SESSIONS_RESPONSE=$(curl -s -b cookies.txt "$API_BASE/chat/sessions")
echo "Sessions response: $SESSIONS_RESPONSE"
echo ""

echo "3. Testing POST /chat/message (new conversation)..."
MESSAGE_RESPONSE=$(curl -s -b cookies.txt -X POST "$API_BASE/chat/message" \
  -H "Content-Type: application/json" \
  -d '{"message":"I am feeling lost and confused"}')

echo "Message response: $MESSAGE_RESPONSE"
echo ""

# Clean up
rm -f cookies.txt

echo "Test complete!"

