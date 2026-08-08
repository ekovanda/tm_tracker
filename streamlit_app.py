import streamlit as st

from authentication import (
    UbisoftAuthenticationError,
    get_nadeo_service_token,
)
from streamlit_bingo_page import bingo_page
from streamlit_player_focus_page import player_focus_page
from streamlit_track_focus_page import track_focus_page


def main():

    # Authentication
    if "nadeo_jwt_token" not in st.session_state:
        try:
            st.session_state["nadeo_jwt_token"] = get_nadeo_service_token()
        except UbisoftAuthenticationError as error:
            st.error(str(error))
            st.stop()

    # App Body
    st.title("Trackmania Tracker 🏆🏎")

    with st.sidebar:
        add_radio = st.radio(
            label="Choose a Page", options=("Bingo", "Player View", "Track View")
        )

    if add_radio == "Player View":
        player_focus_page()
    elif add_radio == "Track View":
        track_focus_page()
    else:
        bingo_page()


if __name__ == "__main__":
    main()
