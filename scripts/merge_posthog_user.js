#!/usr/bin/env node
/**
 * Manually merge a PostHog user's anonymous events into their identified profile
 * 
 * Usage:
 *   node merge_posthog_user.js <user_id> <anonymous_id>
 * 
 * Example:
 *   node merge_posthog_user.js c4c874f8-60c1-7083-5446-8bb0b8de5ddb 019bb8d9-e5b8-74d2-814b-b81a6b0c16c3
 */

const https = require('https');

// PostHog configuration
const POSTHOG_API_KEY = 'phc_9TcKpbVhdwIyOv8NjEjr8UnKNaK6bKeiOBBrJoi2wEG';
const POSTHOG_HOST = 'us.i.posthog.com';

// Get arguments
const [userId, anonymousId] = process.argv.slice(2);

if (!userId || !anonymousId) {
  console.error('❌ Error: Missing required arguments');
  console.log('\nUsage:');
  console.log('  node merge_posthog_user.js <user_id> <anonymous_id>');
  console.log('\nExample:');
  console.log('  node merge_posthog_user.js c4c874f8-60c1-7083-5446-8bb0b8de5ddb 019bb8d9-e5b8-74d2-814b-b81a6b0c16c3');
  console.log('\nHow to find these IDs:');
  console.log('  1. Go to PostHog → Persons');
  console.log('  2. Search for the user by email');
  console.log('  3. Click on their profile');
  console.log('  4. Look for "Distinct IDs" section');
  console.log('  5. userId = the Cognito ID (non-UUID looking)');
  console.log('  6. anonymousId = the UUID (e.g., 019bb8d9-...)');
  process.exit(1);
}

console.log('🔗 Merging PostHog user...');
console.log('   User ID:', userId);
console.log('   Anonymous ID:', anonymousId);
console.log('');

// Create the merge event
const event = {
  api_key: POSTHOG_API_KEY,
  event: '$merge_dangerously',
  distinct_id: userId,
  properties: {
    alias: anonymousId
  },
  timestamp: new Date().toISOString()
};

const postData = JSON.stringify(event);

const options = {
  hostname: POSTHOG_HOST,
  port: 443,
  path: '/capture/',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(postData)
  }
};

const req = https.request(options, (res) => {
  let data = '';

  res.on('data', (chunk) => {
    data += chunk;
  });

  res.on('end', () => {
    if (res.statusCode === 200) {
      console.log('✅ Success! User merged in PostHog');
      console.log('   All events from', anonymousId);
      console.log('   are now linked to', userId);
      console.log('');
      console.log('💡 Verify in PostHog:');
      console.log('   1. Go to PostHog → Persons');
      console.log('   2. Search for the user by email');
      console.log('   3. Check that all events are now shown');
    } else {
      console.error('❌ Error:', res.statusCode);
      console.error('Response:', data);
    }
  });
});

req.on('error', (error) => {
  console.error('❌ Request failed:', error.message);
});

req.write(postData);
req.end();

