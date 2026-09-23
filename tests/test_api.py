from unittest.mock import patch

from fastapi.testclient import TestClient

import live_services
from api import (
    APPLICATION_VERSION,
    app,
    get_current_service_token,
    init_storage,
    set_cached_service_token,
)
from authentication import PasswordConfigurationError, UbisoftAuthenticationError
from bingo import ManualTimerState
from bingo_service import (
    SHARED_CANONICAL_GAME,
    SHARED_MANUAL_TIMER,
    CanonicalGameState,
)
from player import PLAYERS
from storage import InMemoryGameStateStore
from track import Track

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
    with patch(
        "api.get_current_service_token",
        side_effect=UbisoftAuthenticationError("Auth failed"),
    ):
        response = client.get("/api/campaigns")
        assert response.status_code == 502
        assert "Failed to authenticate" in response.json()["detail"]


def test_get_campaigns_live_service_error():
    set_cached_service_token({"accessToken": "fake_token"})
    try:
        with patch(
            "live_services.get_official_campaigns",
            side_effect=live_services.LiveServiceError(
                "API down", category="server", status_code=500
            ),
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

    with patch(
        "api.ensure_nadeo_service_token",
        return_value={"accessToken": "token_refreshed"},
    ):
        token = get_current_service_token()
        assert token == "token_refreshed"
    set_cached_service_token(None)


# Game Lifecycle & Timer Tests


def test_get_game_state_pending():
    response = client.get("/api/game")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["session"] is None
    assert "pending" in data
    assert "settings" in data["pending"]


def test_configure_game():
    response = client.post(
        "/api/game/configure",
        json={
            "campaign_id": "test_campaign",
            "board_seed": 42,
            "game_duration_minutes": 180,
            "grace_period_minutes": 15,
            "manual_timer_duration_minutes": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pending"]["campaign_id"] == "test_campaign"
    assert data["pending"]["settings"]["board_seed"] == 42
    assert data["pending"]["settings"]["game_duration_seconds"] == 180 * 60
    assert data["pending"]["settings"]["grace_period_seconds"] == 15 * 60
    assert data["pending"]["settings"]["manual_timer_duration_seconds"] == 5 * 60


def test_start_game_validation():
    # If no campaign is configured or provided
    client.post("/api/game/reset")
    client.post("/api/game/configure", json={"campaign_id": None})
    response = client.post("/api/game/start", json={})
    assert response.status_code == 400
    assert "A campaign_id must be selected" in response.json()["detail"]


def test_game_full_lifecycle():
    fake_tracks = [
        Track(str(num), f"Track {num}", number=num)
        for num in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)
    ]

    client.post("/api/game/reset")
    set_cached_service_token({"accessToken": "fake_token"})
    try:
        with patch(
            "live_services.get_playable_campaign_tracks", return_value=fake_tracks
        ):
            # 1. Start game
            start_resp = client.post(
                "/api/game/start",
                json={"campaign_id": "summer_2026", "board_seed": 10},
            )
            assert start_resp.status_code == 200
            game_data = start_resp.json()
            assert game_data["status"] == "active"
            assert game_data["session"]["campaign_id"] == "summer_2026"
            assert len(game_data["session"]["board"]) == 4

            # 2. Starting again causes 409 Conflict
            duplicate_start = client.post(
                "/api/game/start", json={"campaign_id": "summer_2026"}
            )
            assert duplicate_start.status_code == 409

            # 3. Configure while active causes 409 Conflict
            configure_active = client.post(
                "/api/game/configure", json={"board_seed": 99}
            )
            assert configure_active.status_code == 409

            # 4. Poll game
            with patch(
                "bingo_service._live_record_loader",
                return_value={"track": fake_tracks[0], "players": []},
            ):
                poll_resp = client.post("/api/game/poll")
                assert poll_resp.status_code == 200

            # 5. Stop game
            stop_resp = client.post("/api/game/stop")
            assert stop_resp.status_code == 200
            assert stop_resp.json()["status"] == "stopped"

            # 6. Stop when already stopped causes 400
            stop_again = client.post("/api/game/stop")
            assert (
                stop_again.status_code == 200
            )  # stopping an already stopped game retains stopped snapshot

            # 7. Reset game
            reset_resp = client.post("/api/game/reset")
            assert reset_resp.status_code == 200
            assert reset_resp.json()["status"] == "pending"

            # 8. Stop after reset causes 400
            stop_after_reset = client.post("/api/game/stop")
            assert stop_after_reset.status_code == 400
    finally:
        set_cached_service_token(None)
        client.post("/api/game/reset")


def test_timers_lifecycle():
    player_eljay = PLAYERS[0]

    # Get timers
    timers_resp = client.get("/api/timers")
    assert timers_resp.status_code == 200
    timers_data = timers_resp.json()
    assert len(timers_data) == 3

    # Unknown player 404
    unknown_resp = client.post(
        "/api/timers/nonexistent_id/action", json={"action": "start"}
    )
    assert unknown_resp.status_code == 404

    # Invalid action 400
    invalid_resp = client.post(
        f"/api/timers/{player_eljay.account_id}/action",
        json={"action": "dance"},
    )
    assert invalid_resp.status_code == 400

    # Start timer
    start_resp = client.post(
        f"/api/timers/{player_eljay.account_id}/action",
        json={"action": "start"},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "active"

    # Stop timer
    stop_resp = client.post(
        f"/api/timers/{player_eljay.account_id}/action",
        json={"action": "stop"},
    )
    assert stop_resp.status_code == 200
    assert stop_resp.json()["status"] == "stopped"

    # Restart timer
    restart_resp = client.post(
        f"/api/timers/{player_eljay.account_id}/action",
        json={"action": "restart"},
    )
    assert restart_resp.status_code == 200
    assert restart_resp.json()["status"] == "active"

    # Reset cleans up
    client.post("/api/game/reset")


def test_api_rehydration_on_startup():
    mem_store = InMemoryGameStateStore()
    init_storage(mem_store)

    fake_tracks = [
        Track(str(num), f"Track {num}", number=num)
        for num in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)
    ]
    set_cached_service_token({"accessToken": "fake_token"})
    try:
        with patch(
            "live_services.get_playable_campaign_tracks", return_value=fake_tracks
        ):
            start_resp = client.post(
                "/api/game/start",
                json={
                    "campaign_id": "rehydrate_camp",
                    "board_seed": 123,
                    "grace_period_minutes": 0,
                },
            )
            assert start_resp.status_code == 200

            # Start timer for player 0
            p0 = PLAYERS[0]
            timer_resp = client.post(
                f"/api/timers/{p0.account_id}/action",
                json={"action": "start"},
            )
            assert timer_resp.status_code == 200
            assert timer_resp.json()["status"] == "active"

            # Simulate complete server crash / restart:
            # Wipe in-memory process state without checkpointing
            SHARED_CANONICAL_GAME._state = CanonicalGameState()  # pylint: disable=protected-access
            SHARED_MANUAL_TIMER._states = {  # pylint: disable=protected-access
                player.account_id: ManualTimerState() for player in PLAYERS
            }
            assert SHARED_CANONICAL_GAME.get().session is None

            # Server startup rehydration
            rehydrated = SHARED_CANONICAL_GAME.rehydrate()
            assert rehydrated is True

            # Verify through API endpoints that state was rehydrated
            game_resp = client.get("/api/game")
            assert game_resp.status_code == 200
            game_data = game_resp.json()
            assert game_data["status"] == "active"
            assert game_data["session"]["campaign_id"] == "rehydrate_camp"

            timers_resp = client.get("/api/timers")
            assert timers_resp.status_code == 200
            t_data = {t["player"]["account_id"]: t for t in timers_resp.json()}
            assert t_data[p0.account_id]["status"] == "active"

            # Reset clears in-flight session
            client.post("/api/game/reset")
            assert SHARED_CANONICAL_GAME.get().session is None

            # Rehydrating after reset finds no active session
            assert not SHARED_CANONICAL_GAME.rehydrate()
            assert client.get("/api/game").json()["status"] == "pending"
    finally:
        set_cached_service_token(None)
        client.post("/api/game/reset")


def test_api_lifespan_handler():
    mem_store = InMemoryGameStateStore()
    init_storage(mem_store)
    with TestClient(app) as test_client:
        resp = test_client.get("/health")
        assert resp.status_code == 200
