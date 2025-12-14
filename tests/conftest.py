import sys
import os
import pytest
from dotenv import load_dotenv

# Add project root to sys.path for module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment variables from .env file
load_dotenv()

# Import test configuration
from tests.config import get_config, ENVIRONMENT

@pytest.fixture(scope="session")
def environment():
    """Return the current test environment (dev/staging/prod)."""
    return ENVIRONMENT

@pytest.fixture(scope="session")
def config():
    """Return environment-specific configuration."""
    return get_config()

@pytest.fixture(scope="session")
def api_base_url(config):
    """Return the API base URL for the current environment."""
    return config['api_base_url']

@pytest.fixture(scope="session")
def aws_region(config):
    """Return the AWS region for the current environment."""
    return config['region']
