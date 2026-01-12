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
from data import load_bankroll, prepare_bets_data

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
    # clear cached in-play badge when logging out
    st.session_state.pop("cached_total_inplay", None)
    st.rerun()


login_page = st.Page("pages/login.py", title="Log in", icon=":material/login:")
logout_page = st.Page(logout, title="Log out", icon=":material/logout:")

dashboard = st.Page(
    "pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True
)
bets_en_cours = st.Page(
    "pages/bets_en_cours.py", title="Paris en cours", icon=":material/sports_tennis:"
)

# New page: future matches
future_matchs_page = st.Page(
    "pages/future_matchs.py", title="Matchs à venir", icon=":material/calendar_today:"
)

if st.session_state.logged_in:
    # compute in-play count to show next to the menu label, but cache it so it doesn't update on every rerun
    cached = st.session_state.get("cached_total_inplay", None)
    if cached is None:
        try:
            bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=False)
            cached = len(bets_data) if bets_data is not None else 0
        except Exception:
            cached = 0
        st.session_state["cached_total_inplay"] = cached

    total_inplay = st.session_state.get("cached_total_inplay", 0)

    pg = st.navigation(
        {
            f"{st.session_state.username} ({str(st.session_state.bankroll_cached)}€)": [
                logout_page
            ],
            "Reports": [
                dashboard,
                future_matchs_page,
                st.Page(
                    "pages/bets_en_cours.py",
                    title=f"Paris en cours 🟢{total_inplay}",
                    icon=":material/sports_tennis:",
                ),
            ],
        }
    )
else:
    pg = st.navigation([login_page])

# call helper to insert the logo at the bottom center of the sidebar
# _sidebar_logo_bottom_center()

pg.run()
