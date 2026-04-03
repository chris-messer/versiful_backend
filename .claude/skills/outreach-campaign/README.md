# Outreach Campaign Skill

This skill helps you create and execute SMS outreach campaigns for Versiful users.

## Quick Start

When you want to run an outreach campaign, simply say:
- "Create an outreach campaign for registered non-subscribers"
- "Message unregistered users who have texted us"
- "Run an outreach campaign"

## What This Skill Does

1. **Analyzes** user segments based on registration and engagement
2. **Generates** personalized messages following Versiful best practices
3. **Creates** CSV files for review
4. **Executes** campaigns with proper DynamoDB logging
5. **Reports** success/failure statistics

## Workflow

### Step 1: Analysis
The skill will analyze your target segment and generate a markdown report showing:
- User details and message history
- Days since last contact
- Proposed personalized messages
- Engagement-based segmentation

### Step 2: CSV Generation
A CSV file is created with:
- Phone numbers
- First names (when available)
- Engagement levels
- Personalized messages

### Step 3: Review
You review the CSV and can:
- Exclude specific users
- Modify messages
- Adjust targeting

### Step 4: Execution
After your approval, the skill will:
- Send SMS via Twilio
- Log all outbound messages to DynamoDB
- Link messages to user profiles
- Report success/failure stats

## User Segments

### Registered Non-Subscribers
Users who:
- Created an account (`isRegistered = true`)
- Never subscribed (`isSubscribed = false`)
- Haven't opted out (`skipMarketing != true`)
- Signed up more than 1 day ago

### Unregistered Texters
Users who:
- Sent SMS to Versiful
- Never created an account
- Aren't spam/test accounts
- Haven't texted today (exclude same-day)

## Message Templates

Messages are personalized based on engagement level:

**High Engagement (3+ messages):**
- Acknowledge their questions
- Emphasize personalization
- Warm, engaging tone

**Medium Engagement (2 messages):**
- Acknowledge time gap
- Simple value proposition
- Open invitation

**Low Engagement (1 message):**
- Very light touch
- Focus on availability
- Low-pressure invitation

## Safety Features

- Always requires user confirmation before sending
- Respects `skipMarketing` flags
- Excludes toll-free numbers
- Rate limits to 1 message per second
- Logs all outbound messages for audit trail
- Links messages to user IDs when possible

## Environment Requirements

Before running campaigns, ensure:
```bash
export SECRET_ARN="arn:aws:secretsmanager:us-east-1:018908982481:secret:prod-versiful_secrets-1xcowv"
```

## Scripts Included

All scripts are in the `scripts/` directory:

- **analyze_registered_users.py** - Analyze registered non-subscribers
- **analyze_unregistered_texters.py** - Analyze unregistered SMS users
- **generate_csv.py** - Generate campaign CSV files
- **send_campaign.py** - Execute campaigns from CSV

## Reference Materials

See the `references/` directory for:

- **messaging-guidelines.md** - Best practices for outreach messages
- **dynamodb-schema.md** - DynamoDB table schemas and query patterns
- **example-campaigns.md** - Examples of successful campaigns

## Example Usage

```
User: "Create an outreach campaign for registered users who haven't subscribed"

Skill:
1. Analyzes prod-versiful-users table
2. Queries message history for each user
3. Generates user_outreach_plan.md with analysis
4. Creates outreach_messages.csv for review
5. Waits for your approval
6. Executes campaign with send_campaign.py
7. Reports results
```

## Manual Script Usage

You can also run the scripts directly:

```bash
# Analyze registered users
python .claude/skills/outreach-campaign/scripts/analyze_registered_users.py > user_outreach_plan.md

# Analyze unregistered texters
python .claude/skills/outreach-campaign/scripts/analyze_unregistered_texters.py > unregistered_plan.md

# Generate CSV (registered)
python .claude/skills/outreach-campaign/scripts/generate_csv.py --segment registered --output outreach.csv

# Generate CSV (unregistered)
python .claude/skills/outreach-campaign/scripts/generate_csv.py --segment unregistered --output unregistered.csv

# Send campaign
python .claude/skills/outreach-campaign/scripts/send_campaign.py outreach.csv
```

## Best Practices

1. **Always identify as "it's Versiful!"** - Users don't have our number saved
2. **Acknowledge time gaps** - "It's been a while since we last connected"
3. **Personalize when possible** - Use first names if available
4. **Keep messages concise** - Under 320 characters when possible
5. **Review before sending** - Manually check the CSV for spam/test accounts
6. **Track results** - Monitor reply rates and registrations

## Compliance

All campaigns:
- Identify sender (Versiful)
- Provide opt-out method (STOP)
- Respect user preferences (skipMarketing)
- Follow SMS best practices
- Log all communications

## Metrics to Track

After running campaigns, track:
- Reply rate (target: >15%)
- Registration conversion (target: >5%)
- STOP rate (target: <2%)
- Time to reply
- Sentiment of replies
