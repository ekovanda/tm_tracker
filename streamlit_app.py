import streamlit as st
from typing import Dict

from authentication import get_ubisoft_authentication_ticket, get_nadeo_jwt_token
from live_services import get_club_track_pbs, postprocess_club_track_pbs
from utils import prettify_time
from tm_lookups import CLUBS, TRACKS, PLAYERS


def main():

    # Authentication
    if "ubisoft_ticket" not in st.session_state:
        st.session_state["ubisoft_ticket"] = get_ubisoft_authentication_ticket()
    if "nadeo_jwt_token" not in st.session_state:
        st.session_state["nadeo_jwt_token"] = get_nadeo_jwt_token(st.session_state["ubisoft_ticket"])

    # App Body
    st.title("Trackmania Tracker 🏆🏎")

    # Using "with" notation
    with st.sidebar:
        add_radio = st.radio(
            label = "Chose Page",
            options = ("Overview", "Player View", "Track View")
        )
     
    if add_radio == "Player View":
        player_focus_page()
    elif add_radio == "Track View":
        track_focus_page()
    else:
         overview_page()


def track_focus_page():
    """
    Shows ...
    """
    st.write("More track-specific stats to come.")
    selected_track = st.selectbox("Track Number", options=list(range(1,26)))

    if selected_track:
        pbs_raw: Dict = get_club_track_pbs(CLUBS[0], TRACKS[selected_track - 1], jwt_token=st.session_state["nadeo_jwt_token"]["accessToken"])
        pbs: Dict = postprocess_club_track_pbs(pbs_raw)
        st.header(pbs["track"].name)
        for idx, player in enumerate(pbs["players"]):
            icons = ["🏆", "🥈", "🥉"]
            st.write(f"### {icons[idx]} {prettify_time(player["pb"])}: \t {player["player"].alias or player["player"].name}")

def player_focus_page():
    """
    Shows ...
    """
    st.write("More player-specific stats to come.")

def overview_page():
    st.write("Overview page to come")


if __name__ == "__main__":
    main()
