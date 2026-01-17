import json
import logging
import sys
import os
import boto3
import jwt
import requests
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)



env = os.environ["ENVIRONMENT"]
project_name = os.environ["PROJECT_NAME"]
domain = os.environ["DOMAIN"]

COGNITO_TOKEN_URL = f"https://auth.{env}.{domain}/oauth2/token"

COGNITO_CLIENT_ID = os.environ["CLIENT_ID"]


ALLOWED_REDIRECT_URIS = [
    f"https://dev.{domain}/callback",
    f"https://{domain}/callback",
    "http://localhost:5173/callback"
]

cognito_client = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')

CLIENT_ID = os.environ['CLIENT_ID']  # add to tf outputs and pass in through lambda
USER_POOL_ID = os.environ['USER_POOL_ID'] # add to tf outputs and pass in through lambda

# DynamoDB table
table_name = f"{env}-{project_name}-users"
users_table = dynamodb.Table(table_name)


def create_or_update_user_email(user_id, email):
    """
    Create or update user record in DynamoDB with email.
    """
    try:
        # Check if user exists
        response = users_table.get_item(Key={"userId": user_id})
        
        if "Item" in response:
            # User exists, only update email if not already set
            if not response["Item"].get("email"):
                users_table.update_item(
                    Key={"userId": user_id},
                    UpdateExpression="SET email = :email",
                    ExpressionAttributeValues={":email": email}
                )
                logger.info(f"Updated email for existing user {user_id}")
        else:
            # Create new user with email
            users_table.put_item(
                Item={
                    "userId": user_id,
                    "email": email,
                    "isSubscribed": False,
                    "isRegistered": False
                }
            )
            logger.info(f"Created new user {user_id} with email")
    except Exception as e:
        logger.error(f"Error creating/updating user email: {str(e)}")




def handler(event, context):
    try:
        logger.info('Received event: %s', event)
        route = event['path']
        method = event['httpMethod']

        ROUTES = {
            ("/auth/callback", "POST"): handle_auth,
            ("/auth/login", "POST"): handle_login,
            ("/auth/signup", "POST"): handle_signup,
            ("/auth/refresh", "POST"): handle_refresh,
            ("/auth/logout", "POST"): handle_logout,
            ("/auth/login", "OPTIONS"): handle_options,
            ("/auth/signup", "OPTIONS"): handle_options,
            ("/auth/callback", "OPTIONS"): handle_options,
            ("/auth/refresh", "OPTIONS"): handle_options,
            ("/auth/logout", "OPTIONS"): handle_options,
        }
        #     return rval
        handler = ROUTES.get((route, method), None)
        if handler:
            return handler(event)


        return {
            'statusCode': 404,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': 'Route not found'})
        }
    except Exception as e:
        logger.info('Lambda Failure: %s', e)
        logger.error('Lambda Failure: %s', e)

def handle_auth(event):
    try:
        body = json.loads(event.get('body', '{}'))
        auth_code = body.get('code')
        redirect_uri = body.get('redirectUri')

        if not auth_code or not redirect_uri:
            return error_response(400, 'Missing authorization code or redirect URI')

        # Exchange authorization code for tokens using Cognito OAuth2 Token Endpoint
        token_url = COGNITO_TOKEN_URL
        payload = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "code": auth_code
        }



        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(token_url, data=payload, headers=headers)

        if response.status_code != 200:
            return error_response(400, "Failed to exchange authorization code")

        tokens = response.json()

        # Extract tokens
        id_token = tokens["id_token"]
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")  # Might not always be present

        # Decode the ID token to get user info (email, sub/userId)
        try:
            # Decode without verification (already verified by Cognito)
            decoded_token = jwt.decode(id_token, options={"verify_signature": False})
            user_id = decoded_token.get("sub")  # Cognito user ID
            email = decoded_token.get("email")  # User's email
            
            if user_id and email:
                # Create or update user in DynamoDB with email
                create_or_update_user_email(user_id, email)
            else:
                logger.warning(f"Could not extract user_id or email from token")
        except Exception as e:
            logger.error(f"Error decoding ID token: {str(e)}")

        # Format Set-Cookie headers correctly
        SameSite = "None; " if env == 'dev' else 'Strict'
        cookie_headers = [
            f"id_token={id_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}",
            f"access_token={access_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}"
        ]

        if refresh_token:
            cookie_headers.append(
                f"refresh_token={refresh_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60 * 24 * 30}"
            )  # 30 days

        return {
            'statusCode': 200,
            'multiValueHeaders': {
                'Set-Cookie': cookie_headers
            },
            'body': json.dumps({'message': 'Authentication successful'})
        }

    except Exception as e:
        logging.error(f"Error in authentication: {str(e)}")
        return error_response(500, 'Internal server error')


def handle_login(event):
    try:
        body = json.loads(event.get('body', '{}'))
        username = body.get('username')
        password = body.get('password')

        if not username or not password:
            return error_response(400, 'Missing username or password')

        auth_response = cognito_client.initiate_auth(
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            },
            ClientId=CLIENT_ID
        )

        auth_result = auth_response.get('AuthenticationResult', {})
        id_token = auth_result.get('IdToken')
        access_token = auth_result.get('AccessToken')
        refresh_token = auth_result.get('RefreshToken')

        if not id_token or not access_token:
            return error_response(400, 'Authentication failed')

        # Decode the ID token to get user info and store email
        try:
            decoded_token = jwt.decode(id_token, options={"verify_signature": False})
            user_id = decoded_token.get("sub")
            email = decoded_token.get("email") or username  # Use username as email if not in token
            
            if user_id and email:
                create_or_update_user_email(user_id, email)
        except Exception as e:
            logger.error(f"Error decoding ID token in login: {str(e)}")

        SameSite = "None; " if env == 'dev' else 'Strict'
        cookie_headers = [
            f"id_token={id_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}",
            f"access_token={access_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}"
        ]

        if refresh_token:
            cookie_headers.append(
                f"refresh_token={refresh_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60 * 24 * 30}"
            )  # 30 days

        return {
            'statusCode': 200,
            'multiValueHeaders': {
                'Set-Cookie': cookie_headers
            },
            'headers': get_cors_headers(),
            'body': json.dumps({'message': 'Authentication successful'})
        }

    except cognito_client.exceptions.NotAuthorizedException:
        return error_response(401, 'Invalid username or password')
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return error_response(500, 'Internal server error')


def handle_signup(event):
    try:
        body = json.loads(event.get('body', '{}'))
        username = body.get('username')
        password = body.get('password')

        if not username or not password:
            return error_response(400, 'Missing username or password')

        cognito_client.sign_up(
            ClientId=CLIENT_ID,
            Username=username,
            Password=password,
        )

        # Attempt to auto-confirm to reduce friction; ignore if not permitted
        try:
            cognito_client.admin_confirm_sign_up(
                UserPoolId=USER_POOL_ID,
                Username=username,
            )
        except cognito_client.exceptions.NotAuthorizedException:
            pass
        except cognito_client.exceptions.UserNotFoundException:
            pass

        auth_response = cognito_client.initiate_auth(
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            },
            ClientId=CLIENT_ID
        )

        auth_result = auth_response.get('AuthenticationResult', {})
        id_token = auth_result.get('IdToken')
        access_token = auth_result.get('AccessToken')
        refresh_token = auth_result.get('RefreshToken')

        if not id_token or not access_token:
            return error_response(400, 'Authentication failed')

        # Decode the ID token to get user info and store email
        try:
            decoded_token = jwt.decode(id_token, options={"verify_signature": False})
            user_id = decoded_token.get("sub")
            email = decoded_token.get("email") or username  # Use username as email if not in token
            
            if user_id and email:
                create_or_update_user_email(user_id, email)
        except Exception as e:
            logger.error(f"Error decoding ID token in signup: {str(e)}")

        SameSite = "None; " if env == 'dev' else 'Strict'
        cookie_headers = [
            f"id_token={id_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}",
            f"access_token={access_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}"
        ]

        if refresh_token:
            cookie_headers.append(
                f"refresh_token={refresh_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60 * 24 * 30}"
            )  # 30 days

        return {
            'statusCode': 200,
            'multiValueHeaders': {
                'Set-Cookie': cookie_headers
            },
            'headers': get_cors_headers(),
            'body': json.dumps({'message': 'Signup successful'})
        }

    except cognito_client.exceptions.UsernameExistsException:
        logger.error("Signup error: Email already exists")
        return error_response(409, 'An account with this email already exists')
    except cognito_client.exceptions.InvalidPasswordException as e:
        error_message = str(e)
        logger.error(f"Signup error: Invalid password - {error_message}")
        # Parse Cognito error message to extract user-friendly message
        if "Password did not conform" in error_message:
            return error_response(400, 'Password must be at least 6 characters long')
        return error_response(400, error_message)
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        return error_response(500, 'Internal server error')


def handle_refresh(event):
    try:
        cookies = event.get('headers', {}).get('Cookie', '')
        refresh_token = extract_cookie_value(cookies, 'refresh_token')

        if not refresh_token:
            return error_response(401, 'No refresh token found')

        try:
            response = cognito_client.initiate_auth(
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token
                },
                ClientId=CLIENT_ID
            )

            auth_result = response['AuthenticationResult']
            new_id_token = auth_result['IdToken']
            new_access_token = auth_result['AccessToken']

            # Update tokens in cookies
            SameSite = "None; " if env == 'dev' else 'Strict'
            cookies = [
                f'id_token={new_id_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}',
                f'access_token={new_access_token}; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age={60 * 60}'
            ]

            return {
                'statusCode': 200,
                'multiValueHeaders': {
                'Set-Cookie': cookies
            },
                'body': json.dumps({'message': 'Token refresh successful'})
            }

        except cognito_client.exceptions.NotAuthorizedException:
            return error_response(401, 'Invalid refresh token')

    except Exception as e:
        print(f"Error in token refresh: {str(e)}")
        return error_response(500, 'Internal server error')


def handle_logout(event):
    try:
        # Clear all auth cookies
        SameSite = "None; " if env == 'dev' else 'Strict'
        cookies = [
            f'id_token=; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age=0',
            f'access_token=; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age=0',
            f'refresh_token=; HttpOnly; Secure; SameSite={SameSite}; Path=/; Max-Age=0'
        ]

        return {
            'statusCode': 200,
            'multiValueHeaders': {
                'Set-Cookie': cookies
            },
            'body': json.dumps({'message': 'Logout successful'})
        }

    except Exception as e:
        print(f"Error in logout: {str(e)}")
        return error_response(500, 'Internal server error')


def extract_cookie_value(cookie_string, cookie_name):
    if not cookie_string:
        return None

    cookies = dict(cookie.split('=') for cookie in cookie_string.split('; '))
    return cookies.get(cookie_name)


def get_cors_headers():
    origin = "http://localhost:5173" if env == "dev" else f"https://{domain}"
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }


def error_response(status_code, message):
    return {
        'statusCode': status_code,
        'headers': get_cors_headers(),
        'body': json.dumps({'error': message})
    }


def handle_options(event):
    return {
        'statusCode': 200,
        'headers': get_cors_headers(),
        'body': json.dumps({'message': 'OK'})
    }