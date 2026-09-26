import json
from unittest.mock import Mock, call, patch

import pytest
import requests

from authentication import get_user_agent
from live_services import (
    LIVE_SERVICES_URL,
    PLAYABLE_TRACK_NUMBERS,
    LiveServiceError,
    _get_player_by_account_id,
    _get_track_by_uid,
    get_campaign_tracks,
    get_club_track_pbs,
    get_official_campaigns,
    get_playable_campaign_tracks,
    postprocess_club_track_pbs,
)
from player import PLAYERS
from tm_lookups import CLUBS
from track import TRACKS


def response_for(payload, status_code=200):
    response = Mock()
    response.text = json.dumps(payload)
    response.status_code = status_code
    return response


def test_get_official_campaigns_maps_list_payload():
    response = response_for(
        {
            "campaignList": [
                {"id": 123, "name": "Summer 2026"},
                {"campaignId": "456", "name": "Winter"},
            ]
        }
    )

    with patch("live_services.requests.get", return_value=response) as request:
        campaigns = get_official_campaigns("jwt")

    response.raise_for_status.assert_called_once_with()
    request.assert_called_once_with(
        f"{LIVE_SERVICES_URL}/api/token/campaign/official",
        headers={
            "Content-Type": "application/json",
            "Authorization": "nadeo_v1 t=jwt",
            "User-Agent": get_user_agent(),
        },
        params={"offset": 0, "length": 100},
        timeout=30,
    )
    assert [(campaign.campaign_id, campaign.name) for campaign in campaigns] == [
        ("123", "Summer 2026"),
        ("456", "Winter"),
    ]


def test_get_official_campaigns_accepts_top_level_list():
    response = response_for([{"id": "123", "name": "Summer 2026"}])

    with patch("live_services.requests.get", return_value=response):
        assert get_official_campaigns("jwt")[0].campaign_id == "123"


def test_campaign_track_mapping_and_playable_selection():
    playlist = [
        {"mapUid": f"uid-{number}", "position": number - 1} for number in range(1, 20)
    ]
    campaign_response = response_for([{"id": "campaign-1", "playlist": playlist}])
    map_response = response_for(
        {
            "mapList": [
                {"uid": f"uid-{number}", "name": f"Track {number}"}
                for number in range(1, 20)
            ]
        }
    )

    with patch(
        "live_services.requests.get", side_effect=[campaign_response, map_response]
    ) as request:
        tracks = get_playable_campaign_tracks("campaign-1", "jwt")

    assert request.call_args_list == [
        call(
            f"{LIVE_SERVICES_URL}/api/token/campaign/official",
            headers={
                "Content-Type": "application/json",
                "Authorization": "nadeo_v1 t=jwt",
                "User-Agent": get_user_agent(),
            },
            params={"offset": 0, "length": 100},
            timeout=30,
        ),
        call(
            f"{LIVE_SERVICES_URL}/api/token/map/get-multiple",
            headers={
                "Content-Type": "application/json",
                "Authorization": "nadeo_v1 t=jwt",
                "User-Agent": get_user_agent(),
            },
            params={"mapUidList": ",".join(f"uid-{number}" for number in range(1, 20))},
            timeout=30,
        ),
    ]
    assert [track.number for track in tracks] == list(PLAYABLE_TRACK_NUMBERS)
    assert [track.uid for track in tracks] == [
        f"uid-{number}" for number in PLAYABLE_TRACK_NUMBERS
    ]


def test_campaign_tracks_accept_uid_and_top_level_list():
    campaign_response = response_for(
        [{"id": "campaign-1", "playlist": [{"mapUid": "uid-1"}]}]
    )
    map_response = response_for({"mapList": [{"uid": "uid-1", "name": "Track 1"}]})

    with patch(
        "live_services.requests.get", side_effect=[campaign_response, map_response]
    ):
        tracks = get_campaign_tracks("campaign-1", "jwt")

    assert tracks[0].uid == "uid-1"
    assert tracks[0].number == 1


def test_campaign_payload_and_missing_tracks_are_rejected():
    invalid_response = response_for({"campaignList": ["invalid"]})
    with (
        patch("live_services.requests.get", return_value=invalid_response),
        pytest.raises(LiveServiceError, match="invalid campaign payload"),
    ):
        get_official_campaigns("jwt")

    tracks_response = response_for(
        [{"id": "campaign-1", "playlist": [{"mapUid": "uid-1"}]}]
    )
    map_response = response_for({"mapList": [{"uid": "uid-1", "name": "Track 1"}]})
    with (
        patch(
            "live_services.requests.get",
            side_effect=[tracks_response, map_response],
        ),
        pytest.raises(LiveServiceError, match="missing track numbers"),
    ):
        get_playable_campaign_tracks("campaign-1", "jwt")


def test_requests_require_a_token():
    with pytest.raises(ValueError, match="Missing"):
        get_official_campaigns("")
    with pytest.raises(ValueError, match="Missing"):
        get_campaign_tracks("campaign-1", "")
    with pytest.raises(ValueError, match="Missing"):
        get_club_track_pbs(CLUBS["Elliot"], TRACKS[0], jwt_token=None)


def test_club_track_processing_and_lookup_helpers():
    raw = {
        "mapUid": TRACKS[0].uid,
        "length": 2,
        "top": [
            {"accountId": PLAYERS[0].account_id, "score": 60_000},
            {"accountId": PLAYERS[1].account_id, "score": 61_000},
        ],
    }
    response = response_for(raw)

    with patch("live_services.requests.get", return_value=response) as request:
        assert get_club_track_pbs(CLUBS["Elliot"], TRACKS[0], "group", "jwt") == raw

    response.raise_for_status.assert_called_once_with()
    assert request.call_args.kwargs["headers"]["Authorization"] == "nadeo_v1 t=jwt"
    processed = postprocess_club_track_pbs(raw)
    assert processed["track"] is TRACKS[0]
    assert processed["players"][1]["player"] is PLAYERS[1]
    assert _get_track_by_uid(TRACKS[0].uid) is TRACKS[0]
    assert _get_player_by_account_id(PLAYERS[0].account_id) is PLAYERS[0]

    with pytest.raises(ValueError):
        _get_track_by_uid("missing", tracks=[])
    with pytest.raises(ValueError):
        _get_player_by_account_id("missing", players=[])


@pytest.mark.parametrize(
    ("status_code", "category", "retryable"),
    [(401, "authentication", False), (429, "rate_limit", True), (503, "server", True)],
)
def test_live_http_failures_have_actionable_categories(
    status_code, category, retryable
):
    response = response_for({"error": "failure"}, status_code)
    response.raise_for_status.side_effect = requests.HTTPError(response=response)

    with (
        patch("live_services.requests.get", return_value=response),
        pytest.raises(LiveServiceError) as raised,
    ):
        get_club_track_pbs(CLUBS["Elliot"], TRACKS[0], jwt_token="jwt")

    assert raised.value.status_code == status_code
    assert raised.value.category == category
    assert raised.value.retryable is retryable


@pytest.mark.parametrize("failure", [requests.Timeout(), requests.ConnectionError()])
def test_live_transport_failures_are_translated(failure):
    with (
        patch("live_services.requests.get", side_effect=failure),
        pytest.raises(LiveServiceError) as raised,
    ):
        get_club_track_pbs(CLUBS["Elliot"], TRACKS[0], jwt_token="jwt")

    assert raised.value.category in {"timeout", "connection"}
    assert raised.value.retryable is True


def test_live_malformed_json_is_translated():
    response = response_for(None)
    response.text = "not-json"

    with (
        patch("live_services.requests.get", return_value=response),
        pytest.raises(LiveServiceError, match="malformed JSON"),
    ):
        get_club_track_pbs(CLUBS["Elliot"], TRACKS[0], jwt_token="jwt")


def test_live_leaderboard_payload_must_be_an_object():
    response = response_for(["invalid"])

    with (
        patch("live_services.requests.get", return_value=response),
        pytest.raises(LiveServiceError, match="invalid leaderboard payload"),
    ):
        get_club_track_pbs(CLUBS["Elliot"], TRACKS[0], jwt_token="jwt")


def test_postprocess_can_use_campaign_track_metadata():
    campaign_track = TRACKS[0].__class__("Campaign 1", TRACKS[0].uid, number=1)
    raw = {
        "mapUid": campaign_track.uid,
        "length": 1,
        "top": [{"accountId": PLAYERS[0].account_id, "score": 60_000}],
    }

    processed = postprocess_club_track_pbs(raw, tracks=[campaign_track])

    assert processed["track"] is campaign_track
