from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from api import (
    APPLICATION_VERSION,
    app,
    get_current_service_token,
    set_cached_service_token,
)
from authentication import PasswordConfigurationError, UbisoftAuthenticationError
import live_services

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == APPLICATION_VERSION
    assert "timestamp" in data


def test_api_version():
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"version": APPLICATION_VERSION}


def test_verify_password_success():
    with patch("api.verify_app_password", return_value=True):
        response = client.post("/api/auth/verify", json={"password": "valid_password"})
        assert response.status_code == 200
        assert response.json() == {"authenticated": True}


def test_verify_password_unauthorized():
    with patch("api.verify_app_password", return_value=False):
        response = client.post("/api/auth/verify", json={"password": "wrong_password"})
        assert response.status_code == 401
        assert "Incorrect application password" in response.json()["detail"]


def test_verify_password_configuration_error():
    with patch(
        "api.verify_app_password",
        side_effect=PasswordConfigurationError("Missing password hash"),
    ):
        response = client.post("/api/auth/verify", json={"password": "any"})
        assert response.status_code == 500
        assert "Missing password hash" in response.json()["detail"]


def test_get_campaigns_success():
    fake_campaigns = [
        live_services.Campaign("camp_1", "Summer 2026"),
        live_services.Campaign("camp_2", "Spring 2026"),
    ]
    set_cached_service_token({"accessToken": "fake_token"})
    try:
        with patch("live_services.get_official_campaigns", return_value=fake_campaigns):
            response = client.get("/api/campaigns")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0] == {"campaign_id": "camp_1", "name": "Summer 2026"}
    finally:
        set_cached_service_token(None)


def test_get_campaigns_authentication_error():
    with patch("api.get_current_service_token", side_effect=UbisoftAuthenticationError("Auth failed")):
        response = client.get("/api/campaigns")
        assert response.status_code == 502
        assert "Failed to authenticate" in response.json()["detail"]


def test_get_campaigns_live_service_error():
    set_cached_service_token({"accessToken": "fake_token"})
    try:
        with patch(
            "live_services.get_official_campaigns",
            side_effect=live_services.LiveServiceError("API down", category="server", status_code=500),
        ):
            response = client.get("/api/campaigns")
            assert response.status_code == 502
            assert "API down" in response.json()["detail"]
    finally:
        set_cached_service_token(None)


def test_get_current_service_token_logic():
    set_cached_service_token(None)
    with patch("api.get_nadeo_service_token", return_value={"accessToken": "token_1"}):
        token = get_current_service_token()
        assert token == "token_1"

    with patch("api.ensure_nadeo_service_token", return_value={"accessToken": "token_refreshed"}):
        token = get_current_service_token()
        assert token == "token_refreshed"
    set_cached_service_token(None)
