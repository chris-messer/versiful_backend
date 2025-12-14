#!/bin/bash
# Helper script to set up GitHub secrets and variables for CI/CD
# Usage: ./scripts/setup-github-cicd.sh

set -e

REPO="your-username/versiful-backend"  # UPDATE THIS
ENVIRONMENT=$1

if [ -z "$ENVIRONMENT" ]; then
    echo "Usage: $0 <dev|staging|prod>"
    exit 1
fi

echo "🔧 Setting up CI/CD configuration for $ENVIRONMENT environment..."

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed. Install it with: brew install gh"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub. Run: gh auth login"
    exit 1
fi

# Get Terraform outputs for the environment
cd terraform

echo "📋 Getting configuration from Terraform..."

# You'll need to select the right workspace or tfvars file
# Adjust this based on your Terraform setup
USER_POOL_ID=$(terraform output -raw cognito_user_pool_id 2>/dev/null || echo "")
USER_POOL_CLIENT_ID=$(terraform output -raw cognito_user_pool_client_id 2>/dev/null || echo "")

if [ -z "$USER_POOL_ID" ]; then
    echo "⚠️  Could not get USER_POOL_ID from Terraform. You'll need to set it manually."
    echo "   Get it from AWS Console → Cognito → User Pools"
    read -p "Enter USER_POOL_ID (or press Enter to skip): " USER_POOL_ID
fi

if [ -z "$USER_POOL_CLIENT_ID" ]; then
    echo "⚠️  Could not get USER_POOL_CLIENT_ID from Terraform. You'll need to set it manually."
    echo "   Get it from AWS Console → Cognito → User Pools → App clients"
    read -p "Enter USER_POOL_CLIENT_ID (or press Enter to skip): " USER_POOL_CLIENT_ID
fi

cd ..

# Determine API base URL based on environment
case $ENVIRONMENT in
    dev)
        API_BASE_URL="https://api.dev.versiful.io"
        ;;
    staging)
        API_BASE_URL="https://api.staging.versiful.io"
        ;;
    prod)
        API_BASE_URL="https://api.versiful.io"
        ;;
esac

echo ""
echo "📝 Configuration to set:"
echo "   API_BASE_URL: $API_BASE_URL"
echo "   USER_POOL_ID: $USER_POOL_ID"
echo "   USER_POOL_CLIENT_ID: $USER_POOL_CLIENT_ID"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Create environment if it doesn't exist (gh cli v2.0+)
echo "🌍 Creating environment '$ENVIRONMENT'..."
gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    "/repos/$REPO/environments/$ENVIRONMENT" \
    || echo "Environment may already exist"

# Set environment variables
echo "📊 Setting environment variables..."

gh variable set API_BASE_URL \
    --env $ENVIRONMENT \
    --body "$API_BASE_URL" \
    --repo $REPO

if [ -n "$USER_POOL_ID" ]; then
    gh variable set USER_POOL_ID \
        --env $ENVIRONMENT \
        --body "$USER_POOL_ID" \
        --repo $REPO
fi

if [ -n "$USER_POOL_CLIENT_ID" ]; then
    gh variable set USER_POOL_CLIENT_ID \
        --env $ENVIRONMENT \
        --body "$USER_POOL_CLIENT_ID" \
        --repo $REPO
fi

# Set secrets (will prompt for input)
echo ""
echo "🔐 Setting secrets (you'll be prompted for values)..."
echo "   Press Ctrl+D on an empty line when done entering the secret"
echo ""

read -p "Enter TEST_USER_EMAIL: " TEST_USER_EMAIL
if [ -n "$TEST_USER_EMAIL" ]; then
    echo "$TEST_USER_EMAIL" | gh secret set TEST_USER_EMAIL \
        --env $ENVIRONMENT \
        --repo $REPO
fi

echo "Enter TEST_USER_PASSWORD (input hidden):"
read -s TEST_USER_PASSWORD
if [ -n "$TEST_USER_PASSWORD" ]; then
    echo "$TEST_USER_PASSWORD" | gh secret set TEST_USER_PASSWORD \
        --env $ENVIRONMENT \
        --repo $REPO
fi

echo ""
echo "✅ Done! Environment '$ENVIRONMENT' is configured."
echo ""
echo "📝 Next steps:"
echo "   1. Set repository-level secrets (if not already done):"
echo "      gh secret set AWS_ACCESS_KEY_ID --repo $REPO"
echo "      gh secret set AWS_SECRET_ACCESS_KEY --repo $REPO"
echo ""
echo "   2. Create a test user in Cognito:"
echo "      aws cognito-idp admin-create-user \\"
echo "        --user-pool-id $USER_POOL_ID \\"
echo "        --username $TEST_USER_EMAIL \\"
echo "        --user-attributes Name=email,Value=$TEST_USER_EMAIL Name=email_verified,Value=true \\"
echo "        --message-action SUPPRESS"
echo ""
echo "      aws cognito-idp admin-set-user-password \\"
echo "        --user-pool-id $USER_POOL_ID \\"
echo "        --username $TEST_USER_EMAIL \\"
echo "        --password <your-test-password> \\"
echo "        --permanent"
echo ""
echo "   3. Repeat for other environments: $0 <dev|staging|prod>"

