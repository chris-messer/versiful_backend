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

CLIENT_ID = os.environ['CLIENT_ID']  # add to tf outputs and pass in through lambda
USER_POOL_ID = os.environ['USER_POOL_ID'] # add to tf outputs and pass in through lambda




def handler(event, context):
    try:
        logger.info('Received event: %s', event)
        route = event['path']
        method = event['httpMethod']

        ROUTES = {
            ("/auth/callback", "POST"): handle_auth,
            ("/auth/refresh", "POST"): handle_refresh,
            ("/auth/logout", "POST"): handle_logout,
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
    return {
        'Access-Control-Allow-Origin': "http://localhost:5173",
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