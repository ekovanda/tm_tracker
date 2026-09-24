import base64
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

import authentication
from authentication import (
    UbisoftAuthenticationError,
    create_session_token,
    decode_jwt_payload,
    encode_basic_auth,
    ensure_nadeo_service_token,
    get_nadeo_jwt_token,
    get_nadeo_service_token,
    get_ubisoft_authentication_ticket,
    get_user_agent,
    refresh_nadeo_service_token,
    verify_session_token,
)


def response_for(payload, status_code=200):
    response = Mock()
    response.text = json.dumps(payload)
    response.status_code = status_code
    response.raise_for_status.return_value = None
    return response


def jwt_for(expiry: int) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode())
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


def test_ubisoft_ticket_requires_basic_auth():
    with (
        patch.object(authentication, "BASIC_AUTH", None),
        pytest.raises(UbisoftAuthenticationError, match="BASIC_AUTH"),
    ):
        get_ubisoft_authentication_ticket()


def test_ubisoft_ticket_maps_successful_response():
    response = response_for({"ticket": "ticket-value"})
    with (
        patch.object(authentication, "BASIC_AUTH", "Basic credentials"),
        patch("authentication.requests.post", return_value=response) as request,
    ):
        assert get_ubisoft_authentication_ticket() == "ticket-value"

    request.assert_called_once()
    response.raise_for_status.assert_called_once_with()


def test_ubisoft_ticket_rejects_error_or_malformed_responses():
    missing_ticket = response_for({"errorCode": 401})
    with (
        patch.object(authentication, "BASIC_AUTH", "Basic credentials"),
        patch("authentication.requests.post", return_value=missing_ticket),
        pytest.raises(UbisoftAuthenticationError, match="no ticket"),
    ):
        get_ubisoft_authentication_ticket()

    invalid_json = response_for(None)
    invalid_json.text = "not-json"
    with (
        patch.object(authentication, "BASIC_AUTH", "Basic credentials"),
        patch("authentication.requests.post", return_value=invalid_json),
        pytest.raises(UbisoftAuthenticationError, match="invalid"),
    ):
        get_ubisoft_authentication_ticket()


def test_ubisoft_ticket_translates_http_errors():
    response = response_for({"error": "unauthorized"}, status_code=401)
    response.raise_for_status.side_effect = authentication.requests.HTTPError
    with (
        patch.object(authentication, "BASIC_AUTH", "Basic credentials"),
        patch("authentication.requests.post", return_value=response),
        pytest.raises(UbisoftAuthenticationError, match="failed"),
    ):
        get_ubisoft_authentication_ticket()


def test_nadeo_token_and_jwt_helpers():
    response = response_for({"accessToken": "jwt", "refreshToken": "refresh"})
    with patch("authentication.requests.post", return_value=response) as request:
        assert get_nadeo_jwt_token("ticket") == {
            "accessToken": "jwt",
            "refreshToken": "refresh",
        }
    assert request.call_args.kwargs["json"] == {"audience": "NadeoLiveServices"}
    assert request.call_args.kwargs["headers"]["User-Agent"] == get_user_agent()

    payload = base64.urlsafe_b64encode(b'{"sub":"player"}').decode().rstrip("=")
    assert decode_jwt_payload(f"header.{payload}.signature") == {"sub": "player"}
    assert encode_basic_auth("user", "password").startswith("Basic ")


def test_nadeo_service_token_uses_basic_auth_and_live_audience():
    response = response_for(
        {
            "accessToken": jwt_for(1_800_000_000),
            "refreshToken": "refresh",
        }
    )
    with (
        patch.object(authentication, "EMAIL", "test@example.com"),
        patch("authentication.requests.post", return_value=response) as request,
    ):
        assert get_nadeo_service_token("Basic service-credentials") == {
            "accessToken": jwt_for(1_800_000_000),
            "refreshToken": "refresh",
            "accessTokenExpiresAt": 1_800_000_000,
        }

    request.assert_called_once_with(
        "https://prod.trackmania.core.nadeo.online/v2/authentication/token/basic",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic service-credentials",
            "User-Agent": "Eljay's TM Bingo / Eljay / test@example.com",
        },
        json={"audience": "NadeoLiveServices"},
        timeout=30,
    )


def test_user_agent_includes_configured_project_identity_and_contact():
    with (
        patch.object(authentication, "PROJECT_NAME", "Tracker"),
        patch.object(authentication, "MAINTAINER_HANDLE", "maintainer"),
        patch.object(authentication, "EMAIL", "maintainer@example.com"),
    ):
        assert get_user_agent() == "Tracker / maintainer / maintainer@example.com"


def test_nadeo_service_token_rejects_missing_or_invalid_responses():
    with pytest.raises(UbisoftAuthenticationError, match="Missing BASIC_AUTH"):
        get_nadeo_service_token("")

    invalid_response = response_for({"message": "unauthorized"}, status_code=401)
    invalid_response.raise_for_status.side_effect = authentication.requests.HTTPError
    with (
        patch("authentication.requests.post", return_value=invalid_response),
        pytest.raises(UbisoftAuthenticationError, match="service-account"),
    ):
        get_nadeo_service_token("Basic credentials")

    missing_token = response_for({"refreshToken": "refresh"})
    with (
        patch("authentication.requests.post", return_value=missing_token),
        pytest.raises(UbisoftAuthenticationError, match="no access token"),
    ):
        get_nadeo_service_token("Basic credentials")


def test_refresh_replaces_tokens_and_retains_expiry_metadata():
    response = response_for(
        {
            "accessToken": jwt_for(1_800_000_000),
            "refreshToken": "new-refresh",
        }
    )

    with patch("authentication.requests.post", return_value=response) as request:
        refreshed = refresh_nadeo_service_token("old-refresh")

    request.assert_called_once_with(
        "https://prod.trackmania.core.nadeo.online/v2/authentication/token/refresh",
        headers={
            "Authorization": "nadeo_v1 t=old-refresh",
            "User-Agent": get_user_agent(),
        },
        timeout=30,
    )
    assert refreshed == {
        "accessToken": jwt_for(1_800_000_000),
        "refreshToken": "new-refresh",
        "accessTokenExpiresAt": 1_800_000_000,
    }


def test_ensure_token_refreshes_near_expiry_but_keeps_valid_token():
    valid = {
        "accessToken": jwt_for(1_800_100_000),
        "refreshToken": "refresh",
    }
    now = datetime.fromtimestamp(1_800_000_000, UTC)

    with patch(
        "authentication.refresh_nadeo_service_token",
        return_value={"accessToken": "new", "refreshToken": "new-refresh"},
    ) as refresh:
        assert ensure_nadeo_service_token(valid, now) is valid
        assert ensure_nadeo_service_token(
            {"accessToken": jwt_for(1_800_000_100), "refreshToken": "refresh"},
            now,
            refresh_skew=timedelta(minutes=5),
        ) == {"accessToken": "new", "refreshToken": "new-refresh"}

    refresh.assert_called_once_with("refresh")


def test_ensure_token_falls_back_to_service_token_when_refresh_fails():
    expired = {
        "accessToken": jwt_for(1_800_000_100),
        "refreshToken": "broken-refresh",
    }
    now = datetime.fromtimestamp(1_800_000_000, UTC)

    with (
        patch(
            "authentication.refresh_nadeo_service_token",
            side_effect=UbisoftAuthenticationError("refresh failed"),
        ),
        patch(
            "authentication.get_nadeo_service_token",
            return_value={
                "accessToken": "fresh-service-token",
                "refreshToken": "fresh-refresh",
            },
        ) as get_service,
    ):
        result = ensure_nadeo_service_token(
            expired, now, refresh_skew=timedelta(minutes=5)
        )

    get_service.assert_called_once_with()
    assert result == {
        "accessToken": "fresh-service-token",
        "refreshToken": "fresh-refresh",
    }


def test_get_secret_resolves_from_environ(monkeypatch):
    monkeypatch.setenv("TEST_ENV_VAR", "configured_value")
    # pylint: disable=protected-access
    assert authentication._get_secret("TEST_ENV_VAR") == "configured_value"
    assert authentication._get_secret("NON_EXISTENT_VAR", "fallback") == "fallback"


def test_session_token_creation_and_verification():
    token = create_session_token("custom_subject", expires_in_seconds=3600)
    assert verify_session_token(token) is True


def test_session_token_rejects_expired():
    token = create_session_token("expired_subject", expires_in_seconds=-10)
    assert verify_session_token(token) is False


def test_session_token_rejects_tampered_or_invalid():
    assert verify_session_token("") is False
    assert verify_session_token("invalid") is False
    assert verify_session_token("a.b.c") is False

    valid_token = create_session_token("valid_user")
    payload_b64, _ = valid_token.split(".")
    tampered_sig = payload_b64 + ".dGFtcGVyZWQ="
    assert verify_session_token(tampered_sig) is False

    tampered_payload = "bm90LWpzb24." + "dGVzdA=="
    assert verify_session_token(tampered_payload) is False


def test_session_token_custom_secret_key(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "custom-secret-key-12345")
    token = create_session_token("user")
    assert verify_session_token(token) is True

    monkeypatch.setenv("SESSION_SECRET_KEY", "different-secret-key-67890")
    assert verify_session_token(token) is False


def test_session_token_malformed_base64_and_non_dict():
    # Invalid base64 in signature
    assert verify_session_token("dGVzdA.???invalid-base64???") is False
    # Non-dict JSON payload
    non_dict_payload = (
        base64.urlsafe_b64encode(b'"just a string"').decode("ascii").rstrip("=")
    )
    # pylint: disable=protected-access
    sig = (
        base64.urlsafe_b64encode(
            authentication.hmac.new(
                authentication._get_session_signing_key(),
                non_dict_payload.encode("ascii"),
                authentication.hashlib.sha256,
            ).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )
    assert verify_session_token(f"{non_dict_payload}.{sig}") is False


def test_verify_app_password_with_env_hash(monkeypatch):
    salt = authentication.secrets.token_bytes(16)
    digest = authentication.hashlib.pbkdf2_hmac("sha256", b"my_password", salt, 100_000)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    hash_str = f"pbkdf2_sha256$100000${salt_b64}${digest_b64}"

    monkeypatch.setenv("APP_PASSWORD_HASH", hash_str)
    assert authentication.verify_app_password("my_password") is True
    assert authentication.verify_app_password("wrong_password") is False


def test_verify_app_password_configuration_errors(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    with patch.object(authentication, "APP_PASSWORD_HASH", None):
        with pytest.raises(
            authentication.PasswordConfigurationError, match="Missing APP_PASSWORD_HASH"
        ):
            authentication.verify_app_password("password")

        with pytest.raises(
            authentication.PasswordConfigurationError, match="pbkdf2_sha256"
        ):
            authentication.verify_app_password(
                "password", encoded_hash="invalid_format"
            )

        valid_b64 = base64.urlsafe_b64encode(b"1234567890123456").decode("ascii")
        with pytest.raises(
            authentication.PasswordConfigurationError, match="valid PBKDF2-SHA256"
        ):
            authentication.verify_app_password(
                "password", encoded_hash=f"pbkdf2_sha256$100${valid_b64}${valid_b64}"
            )
