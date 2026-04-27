# ruff: noqa: E402
import streamlit as st
import os
import re
import sys


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


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

if not st.session_state.logged_in and _env_flag("TENNETVIZ_DEV_AUTO_LOGIN"):
    st.session_state.logged_in = True
    st.session_state.ID_USER = int(os.getenv("TENNETVIZ_DEV_USER_ID", "1"))
    st.session_state.username = os.getenv("TENNETVIZ_DEV_USERNAME", "dev")

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

# New page: data explorer
data_explorer_page = st.Page(
    "pages/data_explorer.py",
    title="Exploration de données",
    icon=":material/analytics:",
)

# New analytics pages
alerts_page = st.Page(
    "pages/alerts.py", title="Alertes", icon=":material/notifications_active:"
)
calibration_page = st.Page(
    "pages/calibration.py", title="Calibration", icon=":material/track_changes:"
)
bankroll_page = st.Page(
    "pages/bankroll.py", title="Bankroll & Kelly", icon=":material/savings:"
)
players_page = st.Page("pages/players.py", title="Joueurs", icon=":material/person:")
streaks_page = st.Page(
    "pages/streaks.py",
    title="Streaks & Volatilité",
    icon=":material/local_fire_department:",
)

if st.session_state.logged_in:
    # compute in-play count to show next to the menu label, but cache it with a short TTL
    # so it stays fresh without re-querying on every Streamlit rerun.
    import time
    from config import INPLAY_BADGE_TTL

    cached = st.session_state.get("cached_total_inplay", None)
    cached_at = st.session_state.get("cached_total_inplay_at", 0)
    is_stale = (time.time() - cached_at) > INPLAY_BADGE_TTL
    if cached is None or is_stale:
        try:
            bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=False)
            cached = len(bets_data) if bets_data is not None else 0
        except Exception:
            cached = 0
        st.session_state["cached_total_inplay"] = cached
        st.session_state["cached_total_inplay_at"] = time.time()

    total_inplay = st.session_state.get("cached_total_inplay", 0)

    pg = st.navigation(
        {
            f"{st.session_state.username} ({str(st.session_state.bankroll_cached)}€)": [
                logout_page
            ],
            "Reports": [
                dashboard,
                alerts_page,
                future_matchs_page,
                st.Page(
                    "pages/bets_en_cours.py",
                    title=f"Paris en cours 🟢{total_inplay}",
                    icon=":material/sports_tennis:",
                ),
            ],
            "Analyse": [
                calibration_page,
                bankroll_page,
                players_page,
                streaks_page,
                data_explorer_page,
            ],
        }
    )
else:
    pg = st.navigation([login_page])

# call helper to insert the logo at the bottom center of the sidebar
# _sidebar_logo_bottom_center()

pg.run()
