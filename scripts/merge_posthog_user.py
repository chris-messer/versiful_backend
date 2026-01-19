#!/usr/bin/env python3
"""
Manually merge a PostHog user's anonymous events into their identified profile

Usage:
    python merge_posthog_user.py <user_id> <anonymous_id>

Example:
    python merge_posthog_user.py c4c874f8-60c1-7083-5446-8bb0b8de5ddb 019bb8d9-e5b8-74d2-814b-b81a6b0c16c3
"""

import sys
import requests
from datetime import datetime

# PostHog configuration
POSTHOG_API_KEY = 'phc_9TcKpbVhdwIyOv8NjEjr8UnKNaK6bKeiOBBrJoi2wEG'
POSTHOG_HOST = 'https://us.i.posthog.com'

def merge_user(user_id: str, anonymous_id: str):
    """Merge anonymous events into identified user profile"""
    
    print('🔗 Merging PostHog user...')
    print(f'   User ID: {user_id}')
    print(f'   Anonymous ID: {anonymous_id}')
    print('')
    
    # Create the merge event
    event = {
        'api_key': POSTHOG_API_KEY,
        'event': '$merge_dangerously',
        'distinct_id': user_id,
        'properties': {
            'alias': anonymous_id
        },
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    # Send to PostHog
    response = requests.post(
        f'{POSTHOG_HOST}/capture/',
        json=event,
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code == 200:
        print('✅ Success! User merged in PostHog')
        print(f'   All events from {anonymous_id}')
        print(f'   are now linked to {user_id}')
        print('')
        print('💡 Verify in PostHog:')
        print('   1. Go to PostHog → Persons')
        print('   2. Search for the user by email')
        print('   3. Check that all events are now shown')
    else:
        print(f'❌ Error: {response.status_code}')
        print(f'Response: {response.text}')
        sys.exit(1)

def main():
    if len(sys.argv) != 3:
        print('❌ Error: Missing required arguments\n')
        print('Usage:')
        print('  python merge_posthog_user.py <user_id> <anonymous_id>\n')
        print('Example:')
        print('  python merge_posthog_user.py c4c874f8-60c1-7083-5446-8bb0b8de5ddb 019bb8d9-e5b8-74d2-814b-b81a6b0c16c3\n')
        print('How to find these IDs:')
        print('  1. Go to PostHog → Persons')
        print('  2. Search for the user by email')
        print('  3. Click on their profile')
        print('  4. Look for "Distinct IDs" section')
        print('  5. userId = the Cognito ID (non-UUID looking)')
        print('  6. anonymousId = the UUID (e.g., 019bb8d9-...)')
        sys.exit(1)
    
    user_id = sys.argv[1]
    anonymous_id = sys.argv[2]
    
    merge_user(user_id, anonymous_id)

if __name__ == '__main__':
    main()

