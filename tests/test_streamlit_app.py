import base64
import hashlib
from unittest.mock import patch

import pytest

import streamlit_app
from authentication import (
    PasswordConfigurationError,
    UbisoftAuthenticationError,
    verify_app_password,
)

# pylint: disable=protected-access


def password_hash(password: str) -> str:
    salt = b"test-salt"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)

    def encode(value):
        return base64.urlsafe_b64encode(value).decode("ascii")

    return f"pbkdf2_sha256$100000${encode(salt)}${encode(digest)}"


def test_password_verification_accepts_and_rejects_without_exposing_secret():
    encoded_hash = password_hash("correct")

    assert verify_app_password("correct", encoded_hash)
    assert not verify_app_password("wrong", encoded_hash)


def test_password_verification_rejects_missing_or_malformed_configuration():
    with pytest.raises(PasswordConfigurationError, match="Missing APP_PASSWORD_HASH"):
        verify_app_password("correct", "")
    with pytest.raises(PasswordConfigurationError, match="must use the format"):
        verify_app_password("correct", "not-a-hash")


class FakeStreamlit:
    def __init__(self, password="", button=False):
        self.session_state = {}
        self.password = password
        self.button_result = button
        self.errors = []
        self.titles = []

    def subheader(self, *_args, **_kwargs):
        pass

    def text_input(self, *_args, **_kwargs):
        return self.password

    def button(self, *_args, **_kwargs):
        return self.button_result

    def error(self, message):
        self.errors.append(message)

    def title(self, message):
        self.titles.append(message)

    def stop(self):
        raise RuntimeError("stopped")

    def rerun(self):
        raise RuntimeError("rerun")


def test_password_gate_stays_locked_without_submission():
    fake_st = FakeStreamlit()
    with patch.object(streamlit_app, "st", fake_st):
        assert not streamlit_app._require_app_password()
    assert not fake_st.session_state


def test_password_gate_unlocks_valid_submission():
    fake_st = FakeStreamlit("correct", True)
    with (
        patch.object(streamlit_app, "st", fake_st),
        patch.object(streamlit_app, "verify_app_password", return_value=True),
        pytest.raises(RuntimeError, match="rerun"),
    ):
        streamlit_app._require_app_password()
    assert fake_st.session_state["app_password_authenticated"] is True


def test_password_gate_reports_rejected_submission():
    fake_st = FakeStreamlit("wrong", True)
    with (
        patch.object(streamlit_app, "st", fake_st),
        patch.object(streamlit_app, "verify_app_password", return_value=False),
    ):
        assert not streamlit_app._require_app_password()
    assert fake_st.errors == ["Incorrect password."]


def test_password_gate_reports_missing_configuration_and_stops():
    fake_st = FakeStreamlit("correct", True)
    with (
        patch.object(streamlit_app, "st", fake_st),
        patch.object(
            streamlit_app,
            "verify_app_password",
            side_effect=PasswordConfigurationError("missing configuration"),
        ),
        pytest.raises(RuntimeError, match="stopped"),
    ):
        streamlit_app._require_app_password()
    assert fake_st.errors == ["missing configuration"]


def test_unlocked_password_gate_skips_input():
    fake_st = FakeStreamlit()
    fake_st.session_state["app_password_authenticated"] = True
    with (
        patch.object(streamlit_app, "st", fake_st),
        patch.object(streamlit_app, "verify_app_password") as verify,
    ):
        assert streamlit_app._require_app_password()
    verify.assert_not_called()


def test_main_authenticates_new_session_and_renders_page():
    fake_st = FakeStreamlit()
    fake_st.session_state["app_password_authenticated"] = True
    with (
        patch.object(streamlit_app, "st", fake_st),
        patch.object(streamlit_app, "get_nadeo_service_token", return_value="token"),
        patch.object(streamlit_app, "bingo_page") as page,
    ):
        streamlit_app.main()

    assert fake_st.session_state["nadeo_jwt_token"] == "token"
    assert fake_st.titles == ["Trackmania Tracker 🏆🏎"]
    page.assert_called_once_with()


def test_main_refreshes_existing_session_token():
    fake_st = FakeStreamlit()
    fake_st.session_state.update(
        {"app_password_authenticated": True, "nadeo_jwt_token": "old-token"}
    )
    with (
        patch.object(streamlit_app, "st", fake_st),
        patch.object(
            streamlit_app, "ensure_nadeo_service_token", return_value="new-token"
        ) as ensure,
        patch.object(streamlit_app, "bingo_page"),
    ):
        streamlit_app.main()

    ensure.assert_called_once_with("old-token")
    assert fake_st.session_state["nadeo_jwt_token"] == "new-token"


@pytest.mark.parametrize(
    ("has_token", "operation_name"),
    [(False, "get_nadeo_service_token"), (True, "ensure_nadeo_service_token")],
)
def test_main_reports_nadeo_authentication_failure(has_token, operation_name):
    fake_st = FakeStreamlit()
    fake_st.session_state["app_password_authenticated"] = True
    if has_token:
        fake_st.session_state["nadeo_jwt_token"] = "token"
    failure = UbisoftAuthenticationError("auth failed")
    with (
        patch.object(streamlit_app, "st", fake_st),
        patch.object(streamlit_app, operation_name, side_effect=failure),
        pytest.raises(RuntimeError, match="stopped"),
    ):
        streamlit_app.main()

    assert fake_st.errors == ["auth failed"]
