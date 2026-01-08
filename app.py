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
from utils import _sidebar_logo_bottom_center
from data import load_bankroll

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Ensure a username key exists in session state
if "username" not in st.session_state:
    st.session_state.username = ""


def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.ID_USER = None
    st.session_state.bankroll = None
    st.rerun()


print(os.getcwd())
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
            f"{st.session_state.username} ({str(load_bankroll(st.session_state.ID_USER))}€)": [
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
