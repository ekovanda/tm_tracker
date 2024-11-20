import base64
import os
from dotenv import load_dotenv
import requests
from typing import Dict
import json
from config import UBISOFT_APP_ID

load_dotenv()
BASIC_AUTH = os.getenv('BASIC_AUTH')
EMAIL = os.getenv("EMAIL")

def get_ubisoft_authentication_ticket() -> str:
    """
    Gets authentication ticket specific to my Ubisoft account.
    Does not use alternative 'dedicate server' approach. 
    Ubisoft authentication ticket can be used to get a nadeo jwt token.

    Gets value for key "ticket" in larger Dict.
    """

    headers = {
        "Content-Type": "application/json",
        "Ubi-AppId": UBISOFT_APP_ID,
        "Authorization": BASIC_AUTH,
        "User-Agent": f"Eljay's TM Tracker / {EMAIL}"
    }

    url_ubisoft_user_auth = "https://public-ubiservices.ubi.com/v3/profiles/sessions"
    response = requests.post(url_ubisoft_user_auth, headers=headers)

    return json.loads(response.text)["ticket"]

def get_nadeo_jwt_token(ubisoft_authentication_ticket:str) -> Dict:
    """
    Returns dict with keys ["accessToken", "refreshToken"]. 
    Nadeo jwt token used in all further requests to Nadeo Services API. 
    """
    headers = {
    "Content-Type": "application/json",
    "Authorization": f"ubi_v1 t={ubisoft_authentication_ticket}",
    }

    url_nadeo_user_auth = "https://prod.trackmania.core.nadeo.online/v2/authentication/token/ubiservices"

    # Note that if you don't provide a json body, you get a token for the audience NadeoServices.
    body = { "audience": "NadeoLiveServices" }

    # Make the POST request to Ubisoft API
    jwt = requests.post(url_nadeo_user_auth, headers=headers, json=body)
    jwt_dict = json.loads(jwt.text)
    
    return jwt_dict


# Convenience functions 
def _urlsafe_base64_decode(base64_string):
    padding = '=' * (4 - len(base64_string) % 4)
    return base64.urlsafe_b64decode(base64_string + padding)

def decode_jwt_payload(jwt_token: str) -> Dict:
    # Split the JWT into its parts
    header, payload, signature = jwt_token.split('.')
    
    # Decode the payload (URL-safe Base64)
    decoded_payload = _urlsafe_base64_decode(payload).decode('utf-8')
    
    # Parse the payload as JSON
    payload_data = json.loads(decoded_payload)
    
    return payload_data

def encode_basic_auth(email, password):
    credentials = f"{email}:{password}"
    return "Basic " + base64.b64encode(credentials.encode('utf-8')).decode('utf-8')