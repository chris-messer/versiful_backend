#!/usr/bin/env python3
"""
Backfill createdAt timestamps for existing users from Cognito UserCreateDate.

This script:
1. Retrieves all users from the Cognito user pool
2. For each user, gets the UserCreateDate from Cognito
3. Updates the corresponding DynamoDB user record with createdAt field

Usage:
    python scripts/backfill_user_created_at.py --environment dev
    python scripts/backfill_user_created_at.py --environment prod --dry-run
"""

import argparse
import boto3
import sys
from datetime import datetime


def get_cognito_user_pool_id(environment, project_name="versiful"):
    """Get the Cognito User Pool ID for the specified environment."""
    cognito_client = boto3.client('cognito-idp')

    try:
        response = cognito_client.list_user_pools(MaxResults=60)

        # Find the user pool matching our naming convention
        pool_name = f"{environment}-{project_name}-user-pool"
        for pool in response['UserPools']:
            if pool['Name'] == pool_name:
                return pool['Id']

        print(f"Error: Could not find user pool with name '{pool_name}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error listing user pools: {str(e)}")
        sys.exit(1)


def get_all_cognito_users(user_pool_id):
    """Retrieve all users from Cognito user pool."""
    cognito_client = boto3.client('cognito-idp')
    users = []
    pagination_token = None

    print(f"Fetching users from Cognito user pool: {user_pool_id}")

    while True:
        try:
            if pagination_token:
                response = cognito_client.list_users(
                    UserPoolId=user_pool_id,
                    Limit=60,
                    PaginationToken=pagination_token
                )
            else:
                response = cognito_client.list_users(
                    UserPoolId=user_pool_id,
                    Limit=60
                )

            users.extend(response['Users'])
            pagination_token = response.get('PaginationToken')

            if not pagination_token:
                break

        except Exception as e:
            print(f"Error fetching users from Cognito: {str(e)}")
            break

    print(f"Found {len(users)} users in Cognito")
    return users


def backfill_created_at(environment, project_name="versiful", dry_run=False):
    """Backfill createdAt field for all users in DynamoDB from Cognito."""

    # Get Cognito user pool ID
    user_pool_id = get_cognito_user_pool_id(environment, project_name)
    print(f"Using Cognito User Pool: {user_pool_id}")

    # Get all users from Cognito
    cognito_users = get_all_cognito_users(user_pool_id)

    # Connect to DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table_name = f"{environment}-{project_name}-users"
    users_table = dynamodb.Table(table_name)

    print(f"Using DynamoDB table: {table_name}")
    print(f"Dry run: {dry_run}")
    print("-" * 80)

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for cognito_user in cognito_users:
        # Extract user info from Cognito
        user_id = cognito_user.get('Username')  # This is the sub/userId
        user_create_date = cognito_user.get('UserCreateDate')

        if not user_id or not user_create_date:
            print(f"Skipping user - missing userId or UserCreateDate")
            error_count += 1
            continue

        # Convert UserCreateDate to ISO format string
        created_at = user_create_date.isoformat()

        try:
            # Check if user exists in DynamoDB
            response = users_table.get_item(Key={"userId": user_id})

            if "Item" not in response:
                print(f"⚠️  User {user_id} exists in Cognito but not in DynamoDB - skipping")
                skipped_count += 1
                continue

            user_item = response["Item"]

            # Check if createdAt already exists
            if user_item.get("createdAt"):
                print(f"✓ User {user_id} already has createdAt: {user_item['createdAt']} - skipping")
                skipped_count += 1
                continue

            # Update user with createdAt
            if dry_run:
                print(f"[DRY RUN] Would set createdAt={created_at} for user {user_id}")
                updated_count += 1
            else:
                users_table.update_item(
                    Key={"userId": user_id},
                    UpdateExpression="SET createdAt = :createdAt",
                    ExpressionAttributeValues={":createdAt": created_at}
                )
                print(f"✓ Updated user {user_id} with createdAt: {created_at}")
                updated_count += 1

        except Exception as e:
            print(f"❌ Error updating user {user_id}: {str(e)}")
            error_count += 1

    print("-" * 80)
    print(f"Summary:")
    print(f"  Total Cognito users: {len(cognito_users)}")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors: {error_count}")

    if dry_run:
        print("\nThis was a dry run. Run without --dry-run to apply changes.")


def main():
    parser = argparse.ArgumentParser(
        description='Backfill createdAt timestamps for users from Cognito'
    )
    parser.add_argument(
        '--environment',
        choices=['dev', 'staging', 'prod'],
        required=True,
        help='Environment to backfill (dev, staging, or prod)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run in dry-run mode (no actual updates)'
    )
    parser.add_argument(
        '--project-name',
        default='versiful',
        help='Project name (default: versiful)'
    )

    args = parser.parse_args()

    print(f"Starting createdAt backfill for environment: {args.environment}")
    backfill_created_at(args.environment, args.project_name, args.dry_run)
    print("Done!")


if __name__ == "__main__":
    main()
