import requests

import boto3
import json
from botocore.exceptions import ClientError
from twilio.rest import Client
import openai


def get_secret():
    secret_name = "dev-versiful_secrets"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)
    # Your code goes here.

def generate_response(message, model="gpt-4o"):
    """
        Sends a message to OpenAI's GPT-4o model and returns the response.

        :param api_key: Your OpenAI API key
        :param message: The message to send
        :param model: The model to use (default is "gpt-4o")
        :return: The model's response
        """

    client = openai.OpenAI(api_key=get_secret()['gpt'])

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

def generate_photo(prompt):
    url = "https://api.openai.com/v1/images/generations"
    payload = json.dumps({
        "model": "dall-e-3",
        "prompt": f"{prompt}",
        "n": 1,
        "size": "1024x1024"
    })
    auth = get_secret()['dalle_secret']
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {auth}'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    r = json.loads(response.text)

    return r

def get_twilio_secrets():
    secret_name = "twilio_keys"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


def send_message(to_num, message):
    twilio_auth = get_twilio_secrets()
    account_sid = twilio_auth['twilio_account_sid']
    auth_token = twilio_auth['twilio_auth']

    client = Client(account_sid, auth_token)

    message = client.messages.create(
        from_='+18336811158',
        body=f'{message}',
        to= f'{to_num}'
    )

    print(message.sid)


