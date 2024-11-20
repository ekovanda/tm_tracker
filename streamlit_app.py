import streamlit as st
from typing import Dict

from authentication import get_ubisoft_authentication_ticket, get_nadeo_jwt_token
from live_services import get_club_map_pbs
from tm_lookups import CLUBS, MAPS, PLAYERS


def main():

    # Authentication
    if "ubisoft_ticket" not in st.session_state:
        st.session_state["ubisoft_ticket"] = get_ubisoft_authentication_ticket()
    if "nadeo_jwt_token" not in st.session_state:
        st.session_state["nadeo_jwt_token"] = get_nadeo_jwt_token(st.session_state["ubisoft_ticket"])


    pbs: Dict = get_club_map_pbs(CLUBS[0], MAPS[0], jwt_token=st.session_state["nadeo_jwt_token"]["accessToken"])

    # App Body
    st.title("Trackmania Tracker")
    st.write(pbs)


if __name__ == "__main__":
    main()
