import base64
import json
import os

import requests
from dotenv import load_dotenv

from config import UBISOFT_APP_ID

load_dotenv()
BASIC_AUTH = os.getenv("BASIC_AUTH")
EMAIL = os.getenv("EMAIL")
REQUEST_TIMEOUT_SECONDS = 30


class UbisoftAuthenticationError(RuntimeError):
    """Raised when Ubisoft does not return an authentication ticket."""


def get_ubisoft_authentication_ticket() -> str:
    """
    Gets authentication ticket specific to my Ubisoft account.
    Does not use alternative 'dedicate server' approach.
    Ubisoft authentication ticket can be used to get a nadeo jwt token.

    Gets value for key "ticket" in larger Dict.
    """

    if not BASIC_AUTH:
        raise UbisoftAuthenticationError(
            "Missing BASIC_AUTH. Set a valid Ubisoft Basic authorization value in .env."
        )

    headers = {
        "Content-Type": "application/json",
        "Ubi-AppId": UBISOFT_APP_ID,
        "Authorization": BASIC_AUTH,
        "User-Agent": f"Eljay's TM Tracker / {EMAIL}",
    }

    url_ubisoft_user_auth = "https://public-ubiservices.ubi.com/v3/profiles/sessions"
    response = requests.post(
        url_ubisoft_user_auth, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise UbisoftAuthenticationError(
            "Ubisoft authentication failed. Check BASIC_AUTH and account credentials."
        ) from error

    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as error:
        raise UbisoftAuthenticationError(
            "Ubisoft returned an invalid authentication response."
        ) from error

    if not isinstance(payload, dict) or not payload.get("ticket"):
        raise UbisoftAuthenticationError(
            "Ubisoft authentication returned no ticket. Check BASIC_AUTH and account credentials."
        )

    return str(payload["ticket"])


def get_nadeo_jwt_token(ubisoft_authentication_ticket: str) -> dict:
    """
    Returns dict with keys ["accessToken", "refreshToken"].
    Nadeo jwt token used in all further requests to Nadeo Services API.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"ubi_v1 t={ubisoft_authentication_ticket}",
    }

    url_nadeo_user_auth = (
        "https://prod.trackmania.core.nadeo.online/v2/authentication/token/ubiservices"
    )

    # Note that if you don't provide a json body, you get a token for the audience NadeoServices.
    body = {"audience": "NadeoLiveServices"}

    # Make the POST request to Ubisoft API
    jwt = requests.post(
        url_nadeo_user_auth,
        headers=headers,
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    jwt_dict = json.loads(jwt.text)

    return jwt_dict


def get_nadeo_service_token(basic_auth: str | None = None) -> dict:
    """Get a Nadeo Live Services token using service-account credentials."""

    authorization = BASIC_AUTH if basic_auth is None else basic_auth
    if not authorization:
        raise UbisoftAuthenticationError(
            "Missing BASIC_AUTH. Set the service-account Basic authorization value in .env."
        )

    response = requests.post(
        "https://prod.trackmania.core.nadeo.online/v2/authentication/token/basic",
        headers={
            "Content-Type": "application/json",
            "Authorization": authorization,
            "User-Agent": f"Eljay's TM Tracker / {EMAIL}",
        },
        json={"audience": "NadeoLiveServices"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise UbisoftAuthenticationError(
            "Nadeo service-account authentication failed. Check BASIC_AUTH."
        ) from error

    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as error:
        raise UbisoftAuthenticationError(
            "Nadeo returned an invalid authentication response."
        ) from error

    if not isinstance(payload, dict) or not payload.get("accessToken"):
        raise UbisoftAuthenticationError(
            "Nadeo authentication returned no access token. Check BASIC_AUTH."
        )

    return payload


# Convenience functions
def _urlsafe_base64_decode(base64_string):
    padding = "=" * (4 - len(base64_string) % 4)
    return base64.urlsafe_b64decode(base64_string + padding)


def decode_jwt_payload(jwt_token: str) -> dict:
    # Split the JWT into its parts
    _, payload, _ = jwt_token.split(".")

    # Decode the payload (URL-safe Base64)
    decoded_payload = _urlsafe_base64_decode(payload).decode("utf-8")

    # Parse the payload as JSON
    payload_data = json.loads(decoded_payload)

    return payload_data


def encode_basic_auth(email, password):
    credentials = f"{email}:{password}"
    return "Basic " + base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
