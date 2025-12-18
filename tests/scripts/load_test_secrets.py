"""
Fetch test credentials from AWS Secrets Manager and emit a dotenv file for tests.

Defaults:
- Secret name: "{ENVIRONMENT}-{PROJECT_NAME}_secrets" (matches Terraform)
- Region: us-east-1
- Output file: .env.test.generated (gitignored recommended)

Expected secret JSON keys (add them to your secret payload):
- TEST_USER_EMAIL
- TEST_USER_PASSWORD
- USER_POOL_CLIENT_ID
- USER_POOL_CLIENT_SECRET (optional if your client has no secret)
- API_BASE_URL (optional override; otherwise terraform defaults in tests/config.py)

Usage:
  ENVIRONMENT=dev PROJECT_NAME=versiful \
  python tests/scripts/load_test_secrets.py --write-env

Then either:
  export $(cat .env.test.generated | xargs)  # bash-compatible shells
or rely on pytest loading the generated file (see conftest.py).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def fetch_secret(secret_id: str, region: str) -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    try:
        resp = client.get_secret_value(SecretId=secret_id)
    except ClientError as e:
        print(f"Failed to fetch secret {secret_id}: {e}", file=sys.stderr)
        sys.exit(2)

    secret_str = resp.get("SecretString")
    if not secret_str:
        print(f"Secret {secret_id} has no SecretString", file=sys.stderr)
        sys.exit(3)

    try:
        return json.loads(secret_str)
    except json.JSONDecodeError as e:
        print(f"Secret {secret_id} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(4)


def write_env_file(data: dict, path: Path) -> None:
    with path.open("w") as f:
        for key, val in data.items():
            if val is None:
                continue
            f.write(f"{key}={val}\n")
    print(f"Wrote {path} with {len(data)} entries.")


def main():
    parser = argparse.ArgumentParser(description="Load test secrets into a dotenv file.")
    parser.add_argument("--secret-id", help="Secrets Manager ID/ARN. Default: {ENVIRONMENT}-{PROJECT_NAME}_secrets")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--write-env", action="store_true", help="Write .env.test.generated")
    parser.add_argument("--env-file", default=".env.test.generated", help="Path to write dotenv file")
    args = parser.parse_args()

    environment = os.getenv("ENVIRONMENT", "dev")
    project_name = os.getenv("PROJECT_NAME", "versiful")
    secret_id = args.secret_id or f"{environment}-{project_name}_secrets"

    secret = fetch_secret(secret_id, args.region)

    needed_keys = [
        "TEST_USER_EMAIL",
        "TEST_USER_PASSWORD",
        "USER_POOL_CLIENT_ID",
        "USER_POOL_ID",
    ]
    optional_keys = [
        "USER_POOL_CLIENT_SECRET",
        "API_BASE_URL",
    ]

    missing = [k for k in needed_keys if not secret.get(k)]
    if missing:
        print(f"Missing keys in secret {secret_id}: {', '.join(missing)}", file=sys.stderr)
        print("Add them to the secret JSON and re-run.", file=sys.stderr)
        sys.exit(5)

    out_data = {k: secret.get(k) for k in needed_keys + optional_keys}

    if args.write_env:
        write_env_file(out_data, Path(args.env_file))
    else:
        for k, v in out_data.items():
            if v is not None:
                print(f"{k}={v}")


if __name__ == "__main__":
    main()

