#!/usr/bin/env python3
"""
Quick and dirty script to send SMS via Twilio
Usage: python send_sms.py <to_phone_number> <message>
Example: python send_sms.py +15551234567 "Hello from Versiful!"
"""
import sys
import os
import boto3
import json
from twilio.rest import Client

# Versiful phone numbers by environment
VERSIFUL_PHONE_DEV = "+18336811158"
VERSIFUL_PHONE_PROD = "+18888671394"

def get_secrets(environment='dev'):
    """Fetch Twilio secrets from AWS Secrets Manager"""
    secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
    secret_name = f"{environment}-versiful_secrets"
    
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Error fetching secrets: {e}")
        raise

def send_sms(to_number, message, environment='dev'):
    """Send SMS via Twilio"""
    # Get Twilio credentials
    secrets = get_secrets(environment)
    account_sid = secrets.get("twilio_account_sid")
    auth_token = secrets.get("twilio_auth")
    
    if not account_sid or not auth_token:
        raise ValueError("Twilio credentials not found in secrets")
    
    # Select phone number based on environment
    from_phone = VERSIFUL_PHONE_PROD if environment == 'prod' else VERSIFUL_PHONE_DEV
    
    # Initialize Twilio client
    client = Client(account_sid, auth_token)
    
    # Send message
    try:
        twilio_message = client.messages.create(
            from_=from_phone,
            body=message,
            to=to_number
        )
        print(f"✅ Message sent successfully!")
        print(f"   To: {to_number}")
        print(f"   From: {from_phone}")
        print(f"   SID: {twilio_message.sid}")
        print(f"   Status: {twilio_message.status}")
        return twilio_message.sid
    except Exception as e:
        print(f"❌ Failed to send SMS: {str(e)}")
        raise

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python send_sms.py <to_phone_number> <message> [environment]")
        print("Example: python send_sms.py +15551234567 'Hello from Versiful!' dev")
        print("\nEnvironment defaults to 'dev' (options: dev, staging, prod)")
        sys.exit(1)
    
    to_phone = sys.argv[1]
    message_text = sys.argv[2]
    env = sys.argv[3] if len(sys.argv) > 3 else 'dev'
    
    print(f"📱 Sending SMS...")
    print(f"   Environment: {env}")
    send_sms(to_phone, message_text, env)

