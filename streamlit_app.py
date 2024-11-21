import streamlit as st
from typing import Dict

from authentication import get_ubisoft_authentication_ticket, get_nadeo_jwt_token
from live_services import get_club_track_pbs, postprocess_club_track_pbs
from tm_lookups import CLUBS, TRACKS, PLAYERS


def main():

    # Authentication
    if "ubisoft_ticket" not in st.session_state:
        st.session_state["ubisoft_ticket"] = get_ubisoft_authentication_ticket()
    if "nadeo_jwt_token" not in st.session_state:
        st.session_state["nadeo_jwt_token"] = get_nadeo_jwt_token(st.session_state["ubisoft_ticket"])

    selected_track = st.selectbox("Track Number", options=list(range(1,26)))

    if selected_track:
        pbs_raw: Dict = get_club_track_pbs(CLUBS[0], TRACKS[selected_track - 1], jwt_token=st.session_state["nadeo_jwt_token"]["accessToken"])
        pbs: Dict = postprocess_club_track_pbs(pbs_raw)


    # App Body
    st.title("Trackmania Tracker")
    st.write(pbs)


if __name__ == "__main__":
    main()
