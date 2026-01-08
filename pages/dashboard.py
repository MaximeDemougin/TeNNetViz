import streamlit as st
import pandas as pd
from data import prepare_bets_data
from pages.components.metrics import render_metrics
from pages.components.charts import render_cumulative_chart
from pages.components.match_card import render_match_info
from pages.components.grouped_table import render_grouped_table

st.set_page_config(
    layout="wide", page_icon="logo_TeNNet.png", page_title="Dashboard TeNNet"
)

# Style global pour le fond de page
st.markdown(
    """
    <style>
        /* Fond de page avec gradient élégant */
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, 
                rgba(15,15,20,1) 0%, 
                rgba(20,20,25,1) 50%, 
                rgba(15,15,20,1) 100%);
        }
        
        /* Fond de la sidebar si présente */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, 
                rgba(20,20,25,0.95) 0%, 
                rgba(15,15,20,0.95) 100%);
        }
        
        /* Header */
        [data-testid="stHeader"] {
            background: transparent;
        }
        
        /* Titre principal */
        h1 {
            color: #e0e0e0 !important;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        
        /* Sous-titres */
        h2, h3 {
            color: #d1d5db !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


chartOptions = {
    "layout": {
        "textColor": "#d1d4dc",
        "background": {"type": "solid", "color": "rgb(23, 26, 31,0)"},
    }
}

st.title("🏆 Les résultats TeNNet", text_alignment="center")

# Cache bets data once per user in session_state to avoid repeated loads during reruns
if st.session_state.get("logged_in", False):
    user_id = st.session_state.get("ID_USER")
    # If cached data missing or belongs to a different user, (re)load it
    if (
        "bets_data_cached" not in st.session_state
        or st.session_state.get("bets_data_user_id") != user_id
    ):
        try:
            st.session_state["bets_data_cached"] = prepare_bets_data(
                user_id, finished=True
            )
            st.session_state["bets_data_user_id"] = user_id
        except Exception:
            st.session_state["bets_data_cached"] = pd.DataFrame()

# For example, display user-specific data if logged in
if st.session_state.get("logged_in", False):
    # Use cached data if available (loaded once per user above)
    bets_data = st.session_state.get("bets_data_cached", pd.DataFrame())

    # --- Sidebar filters: competition, cote range, date range ---
    try:
        bets_original = bets_data.copy()
    except Exception:
        bets_original = pd.DataFrame()

    if not bets_original.empty:
        # Ensure Date is datetime
        try:
            bets_original["Date"] = pd.to_datetime(
                bets_original["Date"], errors="coerce"
            )
        except Exception:
            pass

        # Competition filter
        try:
            comps = sorted(bets_original["Compétition"].dropna().unique().tolist())
        except Exception:
            comps = []
        comp_selected = st.sidebar.multiselect(
            "Filtrer - Compétition",
            options=comps,
            default=comps if len(comps) > 0 else None,
        )

        # Cote double slider
        try:
            cote_vals = pd.to_numeric(bets_original["Cote"], errors="coerce")
            cote_min = float(cote_vals.min()) if cote_vals.notna().any() else 0.0
            cote_max = float(cote_vals.max()) if cote_vals.notna().any() else 10.0
        except Exception:
            cote_min, cote_max = 0.0, 10.0
        cote_range = st.sidebar.slider(
            "Filtrer - Cote",
            min_value=float(cote_min),
            max_value=float(cote_max),
            value=(float(cote_min), float(cote_max)),
            step=0.01,
        )

        # Date range picker
        try:
            min_date = bets_original["Date"].min().date()
            max_date = bets_original["Date"].max().date()
        except Exception:
            import datetime

            min_date = datetime.date(2000, 1, 1)
            max_date = datetime.date.today()

        date_range = st.sidebar.date_input(
            "Filtrer - Période",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        # Apply filters
        filtered = bets_original.copy()
        try:
            if comp_selected and len(comp_selected) > 0:
                filtered = filtered[filtered["Compétition"].isin(comp_selected)]
        except Exception:
            pass

        try:
            cmin, cmax = cote_range
            filtered["Cote"] = pd.to_numeric(filtered["Cote"], errors="coerce")
            try:
                # use inclusive param if available
                filtered = filtered[
                    filtered["Cote"].between(float(cmin), float(cmax), inclusive="both")
                ]
            except TypeError:
                # fallback for pandas versions without 'inclusive' keyword
                filtered = filtered[
                    (filtered["Cote"] >= float(cmin))
                    & (filtered["Cote"] <= float(cmax))
                ]
        except Exception:
            pass

        try:
            # date_range may be a single date or a tuple
            if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                start_date, end_date = date_range
            else:
                start_date = date_range
                end_date = date_range
            # convert to datetimes for comparison
            start_dt = pd.to_datetime(start_date)
            end_dt = (
                pd.to_datetime(end_date)
                + pd.Timedelta(days=1)
                - pd.Timedelta(seconds=1)
            )
            filtered = filtered[
                (filtered["Date"] >= start_dt) & (filtered["Date"] <= end_dt)
            ]
        except Exception:
            pass

        # Preserve original index for ID display in match card
        try:
            filtered = filtered.copy()
            filtered["_orig_index"] = filtered.index
        except Exception:
            pass

        # Sort by Date to compute cumulative sums in chronological order
        try:
            filtered = filtered.sort_values(by="Date", ascending=True)
        except Exception:
            pass

        # Recompute cumulative gains column based on filtered order
        try:
            if "Gains net" in filtered.columns:
                filtered["Cumulative Gains"] = filtered["Gains net"].cumsum()
        except Exception:
            pass

        # Set index back to original identifier so components that display ID keep it
        try:
            filtered = filtered.set_index("_orig_index")
        except Exception:
            pass

        bets_data = filtered

    # Add CSS for metric cards
    st.markdown(
        """
    <style>
        .metric-card {
            background: linear-gradient(135deg, 
                rgba(30,30,35,0.95) 0%, 
                rgba(20,20,25,0.98) 50%, 
                rgba(30,30,35,0.95) 100%);
            border-radius: 12px;
            padding: 16px;
            box-shadow: 
                0 4px 12px rgba(0,0,0,0.4),
                0 2px 4px rgba(0,0,0,0.3),
                inset 0 1px 0 rgba(255,255,255,0.05);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }
        .metric-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, 
                transparent, 
                rgba(255,255,255,0.05), 
                transparent);
            transition: left 0.5s;
        }
        .metric-card:hover::before {
            left: 100%;
        }
        .metric-card:hover {
            transform: translateY(-4px) scale(1.02);
        }
        
        /* Effet ombre verte pour Total Paris */
        .metric-card.card-green:hover {
            box-shadow: 
                0 8px 24px rgba(0,0,0,0.5),
                0 4px 8px rgba(0,0,0,0.4),
                0 0 20px rgba(50,178,150,0.6),
                0 0 40px rgba(50,178,150,0.3),
                0 0 0 1px rgba(50,178,150,0.2),
                inset 0 1px 0 rgba(255,255,255,0.1);
            border-color: rgba(50,178,150,0.8) !important;
        }
        
        /* Effet ombre jaune pour Mises totales */
        .metric-card.card-yellow:hover {
            box-shadow: 
                0 8px 24px rgba(0,0,0,0.5),
                0 4px 8px rgba(0,0,0,0.4),
                0 0 20px rgba(251,191,36,0.6),
                0 0 40px rgba(251,191,36,0.3),
                0 0 0 1px rgba(251,191,36,0.2),
                inset 0 1px 0 rgba(255,255,255,0.1);
            border-color: rgba(251,191,36,0.8) !important;
        }
        
        /* Effet ombre verte pour Gains positifs */
        .metric-card.card-gains-positive:hover {
            box-shadow: 
                0 8px 24px rgba(0,0,0,0.5),
                0 4px 8px rgba(0,0,0,0.4),
                0 0 20px rgba(50,178,150,0.6),
                0 0 40px rgba(50,178,150,0.3),
                0 0 0 1px rgba(50,178,150,0.2),
                inset 0 1px 0 rgba(255,255,255,0.1);
            border-color: rgba(50,178,150,0.8) !important;
        }
        
        /* Effet ombre rouge pour Gains négatifs */
        .metric-card.card-gains-negative:hover {
            box-shadow: 
                0 8px 24px rgba(0,0,0,0.5),
                0 4px 8px rgba(0,0,0,0.4),
                0 0 20px rgba(224,78,78,0.6),
                0 0 40px rgba(224,78,78,0.3),
                0 0 0 1px rgba(224,78,78,0.2),
                inset 0 1px 0 rgba(255,255,255,0.1);
            border-color: rgba(224,78,78,0.8) !important;
        }
        
        /* Effet ombre bleu pour Marges attendues */
        .metric-card.card-blue:hover {
            box-shadow: 
                0 8px 24px rgba(0,0,0,0.5),
                0 4px 8px rgba(0,0,0,0.4),
                0 0 20px rgba(59,130,246,0.6),
                0 0 40px rgba(59,130,246,0.3),
                0 0 0 1px rgba(59,130,246,0.2),
                inset 0 1px 0 rgba(255,255,255,0.1);
            border-color: rgba(59,130,246,0.8) !important;
        }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # Calculate statistics
    total_bets = len(bets_data)
    total_mises = bets_data["Mise"].sum()
    total_gains = bets_data["Gains net"].sum()
    total_marges = bets_data["Marge attendue"].sum()
    wins = len(bets_data[bets_data["Gains net"] > 0])
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    roi = (total_gains / total_mises * 100) if total_mises > 0 else 0
    marge_percentage = (total_marges / total_mises * 100) if total_mises > 0 else 0

    # Display metric cards
    # Render metrics via separate component (add top-level title)
    st.markdown("### 📊 Vue d'ensemble", unsafe_allow_html=True)
    metrics = render_metrics(bets_data)

    st.divider()

    col1, col2, col3 = st.columns([7, 1, 4])
    with col1:
        # Section title and cumulative chart component
        st.markdown("### 📈 Évolution des gains nets")
        selected = render_cumulative_chart(bets_data)

    with col3:
        # Section title and match info
        st.markdown("### 🎾 Info Match")
        render_match_info(bets_data, selected)
    st.divider()

    # Grouped table and charts component (section title)
    st.markdown("### 🧾 Détail des paris")
    render_grouped_table(bets_data)
