# ruff: noqa: E402
import streamlit as st
import os
import re
import sys

project_path = re.sub(
    r"TeNNetViz.*", "TeNNetViz/", os.path.dirname(os.path.abspath(__file__))
)
os.chdir(project_path)
st.session_state["project_path"] = project_path
sys.path.append(project_path)
from data import load_bankroll

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.ID_USER = None

# Ensure a username key exists in session state
if "username" not in st.session_state:
    st.session_state.username = ""
    # Cache bankroll once per user as well
if (
    "bankroll_cached" not in st.session_state
    or st.session_state.get("bankroll_cached_user_id") != st.session_state.ID_USER
):
    try:
        st.session_state["bankroll_cached"] = load_bankroll(st.session_state.ID_USER)
        st.session_state["bankroll_cached_user_id"] = st.session_state.ID_USER
    except Exception:
        st.session_state["bankroll_cached"] = None


def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.ID_USER = None
    st.session_state.bankroll = None
    st.rerun()


login_page = st.Page("pages/login.py", title="Log in", icon=":material/login:")
logout_page = st.Page(logout, title="Log out", icon=":material/logout:")

dashboard = st.Page(
    "pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True
)
bets_en_cours = st.Page(
    "pages/bets_en_cours.py", title="Paris en cours", icon=":material/sports_tennis:"
)

if st.session_state.logged_in:
    pg = st.navigation(
        {
            f"{st.session_state.username} ({str(st.session_state.bankroll_cached)}€)": [
                logout_page
            ],
            "Reports": [dashboard, bets_en_cours],
        }
    )
else:
    pg = st.navigation([login_page])


# call helper to insert the logo at the bottom center of the sidebar
# _sidebar_logo_bottom_center()

pg.run()
