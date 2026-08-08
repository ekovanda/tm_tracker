import streamlit as st

from authentication import (
    PasswordConfigurationError,
    UbisoftAuthenticationError,
    ensure_nadeo_service_token,
    get_nadeo_service_token,
    verify_app_password,
)
from streamlit_bingo_page import bingo_page

st.set_page_config(layout="wide")


def _require_app_password() -> bool:
    """Render the password gate and return whether this session is unlocked."""

    if st.session_state.get("app_password_authenticated") is True:
        return True

    st.subheader("Enter password")
    password = st.text_input("Password", type="password")
    if st.button("Unlock", type="primary"):
        try:
            accepted = verify_app_password(password)
        except PasswordConfigurationError as error:
            st.error(str(error))
            st.stop()
        if accepted:
            st.session_state["app_password_authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    return False


def main():
    if not _require_app_password():
        return

    # Authentication
    if "nadeo_jwt_token" not in st.session_state:
        try:
            st.session_state["nadeo_jwt_token"] = get_nadeo_service_token()
        except UbisoftAuthenticationError as error:
            st.error(str(error))
            st.stop()
    else:
        try:
            st.session_state["nadeo_jwt_token"] = ensure_nadeo_service_token(
                st.session_state["nadeo_jwt_token"]
            )
        except UbisoftAuthenticationError as error:
            st.error(str(error))
            st.stop()

    st.title("Trackmania Tracker 🏆🏎")
    bingo_page()


if __name__ == "__main__":
    main()
