import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta

import requests
import streamlit as st

from config import UBISOFT_APP_ID
from logger import get_logger

logger = get_logger("authentication")


def _get_secret(name: str, default: str | None = None) -> str | None:
    """Read an app setting from Streamlit-managed secrets or environment variables."""

    try:
        val = st.secrets.get(name)
        if val is not None:
            return str(val)
    except (FileNotFoundError, RuntimeError, AttributeError, KeyError):
        logger.debug(
            "Secret '%s' not present in st.secrets; falling back to environment.", name
        )

    env_val = os.environ.get(name)
    if env_val is not None:
        return env_val

    return default


BASIC_AUTH = _get_secret("BASIC_AUTH")
APP_PASSWORD_HASH = _get_secret("APP_PASSWORD_HASH")
EMAIL = _get_secret("EMAIL")
PROJECT_NAME = _get_secret("PROJECT_NAME", "Eljay's TM Tracker")
MAINTAINER_HANDLE = _get_secret("MAINTAINER_HANDLE", "Eljay")
REQUEST_TIMEOUT_SECONDS = 30
TOKEN_REFRESH_URL = (
    "https://prod.trackmania.core.nadeo.online/v2/authentication/token/refresh"
)
ACCESS_TOKEN_EXPIRY_KEY = "accessTokenExpiresAt"
TOKEN_REFRESH_SKEW = timedelta(minutes=5)
_RUNTIME_SECRET_KEY: bytes | None = None


class UbisoftAuthenticationError(RuntimeError):
    """Raised when Ubisoft does not return an authentication ticket."""


class PasswordConfigurationError(RuntimeError):
    """Raised when the application password hash is missing or malformed."""


def _get_session_signing_key() -> bytes:
    """Retrieve or generate the secret key used for HMAC session tokens."""

    key_str = _get_secret("SESSION_SECRET_KEY")
    if key_str:
        return key_str.encode("utf-8")

    pwd_hash = APP_PASSWORD_HASH or _get_secret("APP_PASSWORD_HASH")
    if pwd_hash:
        return hashlib.sha256(pwd_hash.encode("utf-8")).digest()

    global _RUNTIME_SECRET_KEY  # pylint: disable=global-statement
    if _RUNTIME_SECRET_KEY is None:
        _RUNTIME_SECRET_KEY = secrets.token_bytes(32)
    return _RUNTIME_SECRET_KEY


def create_session_token(
    subject: str = "app_user", expires_in_seconds: int = 86400
) -> str:
    """Generate a signed HMAC-SHA256 bearer session token."""

    now = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_in_seconds,
        "nonce": secrets.token_hex(8),
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")
    signature = hmac.new(
        _get_session_signing_key(), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> bool:
    """Verify an HMAC-SHA256 session token signature and expiration."""

    if not token or "." not in token:
        return False

    parts = token.split(".")
    if len(parts) != 2:
        return False

    payload_b64, sig_b64 = parts
    try:
        expected_sig = hmac.new(
            _get_session_signing_key(), payload_b64.encode("ascii"), hashlib.sha256
        ).digest()

        rem_sig = len(sig_b64) % 4
        padded_sig = sig_b64 + ("=" * (4 - rem_sig) if rem_sig else "")
        actual_sig = base64.urlsafe_b64decode(padded_sig.encode("ascii"))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False

        rem_payload = len(payload_b64) % 4
        padded_payload = payload_b64 + ("=" * (4 - rem_payload) if rem_payload else "")
        payload = json.loads(
            base64.urlsafe_b64decode(padded_payload.encode("ascii")).decode("utf-8")
        )
        if not isinstance(payload, dict):
            return False

        exp = int(payload.get("exp", 0))
        now = int(datetime.now(UTC).timestamp())
        return now <= exp
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError):
        return False


def verify_app_password(password: str, encoded_hash: str | None = None) -> bool:
    """Verify an app password against a PBKDF2-SHA256 encoded hash."""

    stored_hash = (
        encoded_hash
        if encoded_hash is not None
        else (APP_PASSWORD_HASH or _get_secret("APP_PASSWORD_HASH"))
    )
    if not stored_hash:
        raise PasswordConfigurationError(
            "Missing APP_PASSWORD_HASH. Set a PBKDF2 password hash in "
            ".streamlit/secrets.toml or APP_PASSWORD_HASH environment variable."
        )

    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$")
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as error:
        raise PasswordConfigurationError(
            "APP_PASSWORD_HASH must use the format pbkdf2_sha256$iterations$salt$digest."
        ) from error

    if algorithm != "pbkdf2_sha256" or iterations < 100_000 or not salt:
        raise PasswordConfigurationError(
            "APP_PASSWORD_HASH must use a valid PBKDF2-SHA256 configuration."
        )

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    is_valid = secrets.compare_digest(actual_digest, expected_digest)
    if is_valid:
        logger.info("Application password verified successfully.")
    else:
        logger.warning("Application password verification failed.")
    return is_valid


def get_user_agent() -> str:
    """Build the identifying User-Agent shared by all service requests."""

    contact = _get_secret("EMAIL") or EMAIL or "contact configured through EMAIL"
    project_name = _get_secret("PROJECT_NAME") or PROJECT_NAME
    maintainer = _get_secret("MAINTAINER_HANDLE") or MAINTAINER_HANDLE
    return f"{project_name} / {maintainer} / {contact}"


def get_ubisoft_authentication_ticket() -> str:
    """
    Gets authentication ticket specific to my Ubisoft account.
    Does not use alternative 'dedicate server' approach.
    Ubisoft authentication ticket can be used to get a nadeo jwt token.

    Gets value for key "ticket" in larger Dict.
    """

    basic_auth = BASIC_AUTH or _get_secret("BASIC_AUTH")

    if not basic_auth:
        raise UbisoftAuthenticationError(
            "Missing BASIC_AUTH. Set a valid Ubisoft Basic authorization value in .env."
        )

    headers = {
        "Content-Type": "application/json",
        "Ubi-AppId": UBISOFT_APP_ID,
        "Authorization": basic_auth,
        "User-Agent": get_user_agent(),
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
        "User-Agent": get_user_agent(),
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

    logger.info(
        "Requesting Nadeo service token", extra={"audience": "NadeoLiveServices"}
    )
    response = requests.post(
        "https://prod.trackmania.core.nadeo.online/v2/authentication/token/basic",
        headers={
            "Content-Type": "application/json",
            "Authorization": authorization,
            "User-Agent": get_user_agent(),
        },
        json={"audience": "NadeoLiveServices"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        logger.error(
            "Nadeo service-account authentication failed",
            extra={"status_code": getattr(response, "status_code", None)},
        )
        raise UbisoftAuthenticationError(
            "Nadeo service-account authentication failed. Check BASIC_AUTH."
        ) from error

    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as error:
        logger.error("Nadeo returned an invalid authentication response")
        raise UbisoftAuthenticationError(
            "Nadeo returned an invalid authentication response."
        ) from error

    if not isinstance(payload, dict) or not payload.get("accessToken"):
        logger.error("Nadeo authentication returned no access token")
        raise UbisoftAuthenticationError(
            "Nadeo authentication returned no access token. Check BASIC_AUTH."
        )

    logger.info("Nadeo service token acquired successfully")
    return _with_access_token_expiry(payload)


def refresh_nadeo_service_token(refresh_token: str) -> dict:
    """Replace an expiring Nadeo access/refresh token pair."""

    if not refresh_token:
        raise UbisoftAuthenticationError("Missing Nadeo refresh token.")

    logger.info("Refreshing Nadeo service token")
    response = requests.post(
        TOKEN_REFRESH_URL,
        headers={
            "Authorization": f"nadeo_v1 t={refresh_token}",
            "User-Agent": get_user_agent(),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        logger.error(
            "Nadeo token refresh failed",
            extra={"status_code": getattr(response, "status_code", None)},
        )
        raise UbisoftAuthenticationError("Nadeo token refresh failed.") from error

    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as error:
        logger.error("Nadeo returned an invalid token refresh response")
        raise UbisoftAuthenticationError(
            "Nadeo returned an invalid token refresh response."
        ) from error

    if not isinstance(payload, dict) or not payload.get("accessToken"):
        logger.error("Nadeo token refresh returned no access token")
        raise UbisoftAuthenticationError(
            "Nadeo token refresh returned no access token."
        )
    if not payload.get("refreshToken"):
        logger.error("Nadeo token refresh returned no refresh token")
        raise UbisoftAuthenticationError(
            "Nadeo token refresh returned no refresh token."
        )

    logger.info("Nadeo service token refreshed successfully")
    return _with_access_token_expiry(payload)


def ensure_nadeo_service_token(
    token: object,
    now: datetime | None = None,
    refresh_skew: timedelta = TOKEN_REFRESH_SKEW,
) -> object:
    """Refresh a service token when its access token is near expiry."""

    if not isinstance(token, dict) or not token.get("accessToken"):
        return token

    expires_at = token.get(ACCESS_TOKEN_EXPIRY_KEY)
    if not isinstance(expires_at, int):
        expires_at = _access_token_expiry(token["accessToken"])
    if expires_at is None:
        return token

    current_time = now or datetime.now(UTC)
    if current_time.timestamp() + refresh_skew.total_seconds() < expires_at:
        return token

    try:
        return refresh_nadeo_service_token(str(token.get("refreshToken", "")))
    except UbisoftAuthenticationError:
        return get_nadeo_service_token()


def _with_access_token_expiry(payload: dict) -> dict:
    token = dict(payload)
    expires_at = _access_token_expiry(str(token["accessToken"]))
    if expires_at is not None:
        token[ACCESS_TOKEN_EXPIRY_KEY] = expires_at
    return token


def _access_token_expiry(access_token: str) -> int | None:
    try:
        expiry = decode_jwt_payload(access_token).get("exp")
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return int(expiry) if isinstance(expiry, (int, float)) else None


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
