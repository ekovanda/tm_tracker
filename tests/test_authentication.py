import base64
import json
from unittest.mock import Mock, patch

import pytest

import authentication
from authentication import (
    UbisoftAuthenticationError,
    decode_jwt_payload,
    encode_basic_auth,
    get_nadeo_jwt_token,
    get_nadeo_service_token,
    get_ubisoft_authentication_ticket,
    get_user_agent,
)


def response_for(payload, status_code=200):
    response = Mock()
    response.text = json.dumps(payload)
    response.status_code = status_code
    response.raise_for_status.return_value = None
    return response


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
    response = response_for({"accessToken": "access", "refreshToken": "refresh"})
    with (
        patch.object(authentication, "EMAIL", "test@example.com"),
        patch("authentication.requests.post", return_value=response) as request,
    ):
        assert get_nadeo_service_token("Basic service-credentials") == {
            "accessToken": "access",
            "refreshToken": "refresh",
        }

    request.assert_called_once_with(
        "https://prod.trackmania.core.nadeo.online/v2/authentication/token/basic",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic service-credentials",
            "User-Agent": "Eljay's TM Tracker / Eljay / test@example.com",
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
