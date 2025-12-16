import requests
from urllib.parse import parse_qs
import boto3
import json
from botocore.exceptions import ClientError
from twilio.rest import Client



def parse_url_string(url_string):
    parsed_dict = {key: value[0] if len(value) == 1 else value for key, value in parse_qs(url_string).items()}
    return parsed_dict

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

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {get_secret()['gpt']}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": 'You are a expert in the bible. When a user tells you their situation '
                                          'or what they are feeling, you will reply back with the location of a '
                                          'relevant parable in the bible, and then a long '
                                          'summary of that parable. '
                                          'Return only the location of the parable, a new line, and then the summary. '
                                          'Do not include anything else. '
                                          ''
                                          'Your tone should be compassionate and loving, and not like a robotic '
                                          'summary. You should draw parralels to the users story if possible.'
                                          ''
                                          'Never, ever stray from this pattern. You should try your best to match '
                                          'what the user said with something you can provide biblical guidance for. '
                                          ''
                                          'If a user says something that is not related to seeking guidance, you should '
                                          'try and match what they are looking for to biblical guidance.'
                                          ''
                                          'If they prompt something vulgar, you should pivot the conversation to '
                                          'eliciting further responses from them to guide the conversation towards '
                                          'religious guidance. '
                                          'As the conversation continues, act as a spiritual guide for the user. '
                                          ''
                                          ''
                                          'As a last resort, respond that you are unable to assist with '
                                          'that and provide a sample question you are able to assist with. '
                                          ''
                                          'Limit each response to less than 200 words.'},
            {"role": "user", "content": message}]
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

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


