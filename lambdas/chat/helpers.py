"""
Helper functions for chat Lambda
"""
import os
import json
import logging
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')


def get_secret() -> Dict[str, Any]:
    """Get secrets from AWS Secrets Manager"""
    secret_name = f"{ENVIRONMENT}-versiful_secrets"
    region_name = "us-east-1"
    
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)
    
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        logger.error("Error retrieving secret: %s", str(e))
        raise e
    
    secret = get_secret_value_response['SecretString']
    return json.loads(secret)

