import streamlit as st

from authentication import get_ubisoft_authentication_ticket, get_nadeo_jwt_token
from streamlit_overview_page import overview_page
from streamlit_track_focus_page import track_focus_page
from streamlit_player_focus_page import player_focus_page


def main():

    # Authentication
    if "ubisoft_ticket" not in st.session_state:
        st.session_state["ubisoft_ticket"] = get_ubisoft_authentication_ticket()
    if "nadeo_jwt_token" not in st.session_state:
        st.session_state["nadeo_jwt_token"] = get_nadeo_jwt_token(st.session_state["ubisoft_ticket"])

    # App Body
    st.title("Trackmania Tracker 🏆🏎")

    with st.sidebar:
        add_radio = st.radio(
            label = "Choose a Page",
            options = ("Overview", "Player View", "Track View")
        )
     
    if add_radio == "Player View":
        player_focus_page()
    elif add_radio == "Track View":
        track_focus_page()
    else:
        overview_page()


if __name__ == "__main__":
    main()
