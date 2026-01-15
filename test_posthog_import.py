#!/usr/bin/env python3
"""
Test script to verify PostHog LangChain integration availability
"""
import sys

print("Python version:", sys.version)
print("\nTesting PostHog imports...")

try:
    import posthog
    print(f"✅ posthog module found: {posthog.__file__}")
    print(f"   Version: {posthog.version.VERSION}")
except ImportError as e:
    print(f"❌ Cannot import posthog: {e}")
    sys.exit(1)

print("\nChecking posthog.ai module...")
try:
    import posthog.ai
    print(f"✅ posthog.ai module found: {posthog.ai.__file__}")
except ImportError as e:
    print(f"❌ Cannot import posthog.ai: {e}")
    print("\nListing posthog module contents:")
    import posthog
    print(dir(posthog))
    sys.exit(1)

print("\nChecking posthog.ai.langchain...")
try:
    from posthog.ai.langchain import CallbackHandler
    print(f"✅ posthog.ai.langchain.CallbackHandler found!")
    print(f"   CallbackHandler: {CallbackHandler}")
    
    # Try to instantiate it
    from posthog import Posthog
    client = Posthog("test_key", host="https://us.i.posthog.com")
    handler = CallbackHandler(
        client=client,
        distinct_id="test_user"
    )
    print(f"✅ Successfully created CallbackHandler instance: {handler}")
    
except ImportError as e:
    print(f"❌ Cannot import CallbackHandler: {e}")
    print("\nListing posthog.ai module contents:")
    import posthog.ai
    print(dir(posthog.ai))
    sys.exit(1)
except Exception as e:
    print(f"❌ Error creating CallbackHandler: {e}")
    sys.exit(1)

print("\n✅ All tests passed! PostHog LangChain integration is available.")

