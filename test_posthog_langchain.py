#!/usr/bin/env python3
"""
Test PostHog LangChain integration using EXACT code from official docs:
https://posthog.com/docs/llm-analytics/installation/langchain
"""

import logging
import uuid

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from posthog.ai.langchain import CallbackHandler
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from posthog import Posthog

# Initialize PostHog - EXACT from docs
posthog = Posthog(
    "phc_9TcKpbVhdwIyOv8NjEjr8UnKNaK6bKeiOBBrJoi2wEG",
    host="https://us.i.posthog.com",
    debug=True  # Enable debug mode
)

logger.info("PostHog client initialized")

# Generate unique IDs for this test run
trace_id = str(uuid.uuid4())
conversation_id = str(uuid.uuid4())
session_id = str(uuid.uuid4())

logger.info(f"Test IDs - trace_id: {trace_id}, conversation_id: {conversation_id}, session_id: {session_id}")

# Create callback handler - EXACT code from docs
callback_handler = CallbackHandler(
    client=posthog,
    distinct_id="user_123",  # optional
    trace_id=trace_id,  # optional - using UUID
    properties={
        "conversation_id": conversation_id,  # optional - using UUID
        "$ai_session_id": session_id  # Testing session ID
    },
    groups={"company": "company_id_in_your_db"},  # optional
    privacy_mode=False  # optional
)

logger.info("CallbackHandler created")

# Create prompt and model - EXACT code from docs
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    ("user", "{input}")
])

# Get OpenAI API key from environment or secrets
import os
import json
import boto3

def get_openai_key():
    """Get OpenAI API key from AWS Secrets Manager"""
    secret_name = "dev-versiful_secrets"
    region_name = "us-east-1"
    
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(get_secret_value_response['SecretString'])
        return secret.get('gpt') or secret.get('openai_api_key')
    except Exception as e:
        print(f"Error getting secret: {e}")
        return None

openai_api_key = get_openai_key()
if not openai_api_key:
    print("Could not get OpenAI API key from secrets")
    exit(1)

model = ChatOpenAI(openai_api_key=openai_api_key)
chain = prompt | model

# Execute the chain with the callback handler - EXACT code from docs
response = chain.invoke(
    {"input": "Tell me a joke about programming"},
    config={"callbacks": [callback_handler]}
)

print("\n=== Response ===")
print(response.content)

# Flush PostHog events before script exits
print("\n=== Flushing PostHog events ===")
posthog.flush()
print("PostHog events flushed")

print("\n=== Test Complete ===")
print("Check PostHog dashboard at: https://us.i.posthog.com")
print("Go to: LLM Analytics -> Traces")
print(f"Look for trace_id: {trace_id}")
print(f"Look for conversation_id: {conversation_id}")
print(f"Look for session_id: {session_id}")
print("Look for distinct_id: user_123")

