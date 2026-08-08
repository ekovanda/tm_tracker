import streamlit as st

from authentication import (
    UbisoftAuthenticationError,
    get_nadeo_service_token,
)
from streamlit_bingo_page import bingo_page

st.set_page_config(layout="wide")


def main():
    # Authentication
    if "nadeo_jwt_token" not in st.session_state:
        try:
            st.session_state["nadeo_jwt_token"] = get_nadeo_service_token()
        except UbisoftAuthenticationError as error:
            st.error(str(error))
            st.stop()

    st.title("Trackmania Tracker 🏆🏎")
    bingo_page()


if __name__ == "__main__":
    main()
