# ruff: noqa: E402
import streamlit as st
import pandas as pd
from datetime import timedelta

from data import load_future_matchs


# Cache the results to avoid reloading on every user interaction / rerun.
# TTL set to 300 seconds (5 minutes) — adjust as needed.
@st.cache_data(ttl=300)
def get_future_matchs_cached():
    return load_future_matchs()


MAX_PRED_BETABLE, MIN_PRED_BETABLE, MIN_MARGE = 4, 1.1, 2
st.set_page_config(page_title="Matchs à venir", layout="wide")

st.markdown("# 🔮 Matchs à venir")
st.markdown(
    "Affiche la prédiction pour chaque joueur et si le pari est rentable en utilisant les cotes maximales disponibles."
)

try:
    df = get_future_matchs_cached()
except Exception as e:
    st.error(f"Erreur lors du chargement des matchs: {e}")
    st.stop()

# Add filters for competition and tournament
try:
    # normalize
    df["tourney_name"] = df["tourney_name"].astype(str)
    df["compet"] = df["compet"].astype(str).str.title()
    comp_options = sorted(df["compet"].dropna().unique())
    tourney_options = sorted(df["tourney_name"].dropna().unique())

    # Use sidebar for filters so they don't span the full page
    with st.sidebar:
        st.markdown("## Filtres")
        selected_comps = st.multiselect(
            "Filtrer par compétition", options=comp_options, default=comp_options
        )
        selected_tourneys = st.multiselect(
            "Filtrer par tournoi", options=tourney_options, default=[]
        )

    if selected_comps:
        df = df[df["compet"].isin(selected_comps)]
    if selected_tourneys:
        df = df[df["tourney_name"].isin(selected_tourneys)]
except Exception:
    # if filters fail, continue with original df
    pass

if df is None or df.empty:
    st.info("Aucun match disponible.")
    st.stop()

# Normalize columns and build per-player rows
try:
    df["tourney_date"] = pd.to_datetime(df["tourney_date"], errors="coerce")
except Exception:
    pass

rows = []
for _, r in df.iterrows():
    match_label = f"{r.get('winner_name', '')} - {r.get('loser_name', '')}"
    odds_link = r.get("odds_lien", "")
    tournoi = r.get("tourney_name", "")
    competition = (r.get("compet") or "").title()

    # Winner side
    try:
        pred_w = float(r.get("winner_pred") or 0)
    except Exception:
        pred_w = 0.0
    try:
        max_odds_w = float(r.get("max_odds1") or 0)
    except Exception:
        max_odds_w = 0.0
    ev_w = (max_odds_w / pred_w - 1) * 100 if (max_odds_w and pred_w) else 0.0
    betable_w = ev_w > MIN_MARGE and (MIN_PRED_BETABLE <= pred_w <= MAX_PRED_BETABLE)

    rows.append(
        {
            "ID_MATCH": r.get("ID_MATCH"),
            "Match": match_label,
            "Joueur": r.get("winner_name", ""),
            "Prédiction": pred_w,
            "Max_cote": max_odds_w,
            "EV_pct": ev_w,
            "Parier ?": betable_w,
            "Lien": odds_link,
            "Tournoi": tournoi,
            "Compétition": competition,
            "Date": r.get("tourney_date"),
        }
    )

    # Loser side
    try:
        pred_l = float(r.get("loser_pred") or 0)
    except Exception:
        pred_l = 0.0
    try:
        max_odds_l = float(r.get("max_odds2") or 0)
    except Exception:
        max_odds_l = 0.0
    ev_l = (max_odds_l / pred_l - 1) * 100 if (max_odds_l and pred_l) else 0.0
    betable_l = ev_l > MIN_MARGE and (MIN_PRED_BETABLE <= pred_l <= MAX_PRED_BETABLE)
    rows.append(
        {
            "ID_MATCH": r.get("ID_MATCH"),
            "Match": match_label,
            "Joueur": r.get("loser_name", ""),
            "Prédiction": pred_l,
            "Max_cote": max_odds_l,
            "EV_pct": ev_l,
            "Parier ?": betable_l,
            "Lien": odds_link,
            "Tournoi": tournoi,
            "Compétition": competition,
            "Date": r.get("tourney_date"),
        }
    )

out = pd.DataFrame(rows)

# Formatting and sorting
out["Prédiction"] = out["Prédiction"].round(3)
out["Max_cote"] = out["Max_cote"].round(3)
out["EV_pct"] = out["EV_pct"].round(1)

out = out.sort_values(by=["Date", "Match"], ascending=[True, True]).reset_index(
    drop=True
)

# Add a date-range slider to filter opportunities
# Ensure Date column is datetime
out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
try:
    # derive min/max as datetimes for the slider (including time)
    min_ts = out["Date"].min()
    max_ts = out["Date"].max()
    if pd.isna(min_ts) or pd.isna(max_ts):
        raise Exception("No valid dates")

    min_dt = min_ts.to_pydatetime()
    max_dt = max_ts.to_pydatetime()

    # put datetime slider in sidebar to keep page clean
    with st.sidebar:
        st.markdown("### Plage date/heure")
        date_range = st.slider(
            "Filtrer par date et heure",
            min_value=min_dt,
            max_value=max_dt,
            value=(min_dt, max_dt),
            format="DD/MM/YYYY HH:mm",
            step=timedelta(minutes=30),
        )

    # apply filter using full timestamps
    out = out[
        (out["Date"] >= pd.to_datetime(date_range[0]))
        & (out["Date"] <= pd.to_datetime(date_range[1]))
    ]
except Exception:
    # If anything fails (e.g. no dates), keep original `out`
    pass

# Display table
st.markdown("## Tableau des opportunités")

# Filter toggle: show only betable opportunities (on main page, not sidebar)
filter_parier = st.checkbox(
    "Afficher seulement les opportunités (Parier ?)", value=False
)

# Use column_config for nicer number formatting if available
col_config = None
try:
    col_config = {
        "Prédiction": st.column_config.NumberColumn("Prédiction", format="%.3f"),
        "Max_cote": st.column_config.NumberColumn("Max_cote", format="%.3f"),
        "EV_pct": st.column_config.NumberColumn("EV_pct", format="%+.1f"),
        "Odds_URL": st.column_config.LinkColumn(
            "Cotes", max_chars=30, display_text="Voir Cotes"
        ),
        "Flash_URL": st.column_config.LinkColumn(
            "Flashscore", max_chars=30, display_text="Voir Flashscore"
        ),
    }
except Exception as e:
    st.error(f"Erreur lors de la configuration des colonnes : {e}")
    col_config = None

# Add a separate time column (Heure) for display
out["Heure"] = out["Date"].dt.strftime("%H:%M").fillna("")

# include Heure in the displayed columns
display_cols = [
    "Compétition",
    "Tournoi",
    "Date",
    "Heure",
    "Match",
    "Joueur",
    "Prédiction",
    "Max_cote",
    "EV_pct",
    "Parier ?",
]

# rebuild display_df with Heure
display_df = out[display_cols].copy()
display_df["Parier ?"] = display_df["Parier ?"].astype(bool)
if filter_parier:
    display_df = display_df[display_df["Parier ?"]]


# --- Ajout des colonnes de liens pour le tableau ---
def _make_links_by_index(idx):
    try:
        row = out.loc[idx]
    except Exception:
        return ("", "")
    try:
        q = (
            (f"{row.get('Match', '')} {row.get('Joueur', '')}")
            .strip()
            .replace(" ", "+")
        )
    except Exception:
        q = ""
    odds_url = row.get("Lien") or f"https://www.oddsportal.com/search/?q={q}"
    flash_id = row.get("ID_MATCH") or row.get("flashscore_id") or row.get("flashscore")
    if flash_id:
        flash_url = f"https://www.flashscore.com/match/{flash_id}"
    else:
        flash_url = f"https://www.flashscore.com/search/?q={q}"
    return (odds_url, flash_url)


# Build columns from original 'out' rows using their index (keeps alignment)
links_series = display_df.apply(
    lambda row: _make_links_by_index(row.name), axis=1, result_type="expand"
)
# result_type 'expand' returns DataFrame-like with columns 0 and 1
if not links_series.empty:
    display_df["Odds_URL"] = links_series[0]
    display_df["Flash_URL"] = links_series[1]
else:
    display_df["Odds_URL"] = ""
    display_df["Flash_URL"] = ""


# Styler: color full row if parable, and color EV_pct text by sign
def _row_highlight(row):
    try:
        if row["Parier ?"]:
            return ["background: rgba(50,178,150,0.06);" for _ in row]
        else:
            return ["background: transparent;" for _ in row]
    except Exception:
        return ["" for _ in row]


def _ev_color(v):
    try:
        val = float(v)
        # Strong positive margin -> violet
        if val > 10:
            return "color: #6a0dad; font-weight:700;"
        # Very low margin -> orange
        if val < 2 and val > 0:
            return "color: #ff8c00; font-weight:700;"
        # Default: positive -> green, non-positive -> red
        return (
            "color: #32b296; font-weight:700;"
            if val > 0
            else "color: #e04e4e; font-weight:700;"
        )
    except Exception:
        return ""


styler = (
    display_df.style.apply(_row_highlight, axis=1)
    .map(_ev_color, subset=["EV_pct"])  # replaced deprecated applymap -> map
    .format({"Prédiction": "{:.3f}", "Max_cote": "{:.3f}", "EV_pct": "{:+.1f}"})
)

try:
    st.dataframe(styler, width="stretch", column_config=col_config)
except Exception:
    st.dataframe(display_df, width="stretch", column_config=col_config)

# Show recommended bets as cards with link
recommended = out[out["Parier ?"]].copy()
if not recommended.empty:
    st.markdown("## ✅ Paris recommandés")

    # Add hover effects and small animations for the cards (with white stripe on hover)
    st.markdown(
        """
        <style>
        .fnv-card {
            position: relative;
            overflow: hidden;
            background: linear-gradient(180deg, rgba(18,20,24,0.95), rgba(23,25,30,0.9));
            border-radius: 12px;
            padding: 12px;
            border: 1px solid rgba(255,255,255,0.03);
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
            will-change: transform;
        }
        /* animated white stripe (sheen) that moves across on hover */
        .fnv-card::before {
            content: '';
            position: absolute;
            top: -60%;
            left: -40%;
            width: 180%;
            height: 80%;
            background: linear-gradient(90deg, rgba(255,255,255,0.0) 0%, rgba(255,255,255,0.18) 45%, rgba(255,255,255,0.06) 55%, rgba(255,255,255,0.0) 100%);
            transform: rotate(-18deg) translateX(-20%);
            opacity: 0;
            transition: opacity 0.32s ease, transform 0.5s ease;
            pointer-events: none;
            mix-blend-mode: overlay;
            border-radius: 40px;
        }
        /* subtle top highlight line */
        .fnv-card::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: linear-gradient(90deg, rgba(255,255,255,0.08), rgba(255,255,255,0));
            opacity: 0.9;
            pointer-events: none;
        }
        .fnv-card:hover {
            transform: translateY(-6px) scale(1.01);
            box-shadow: 0 18px 40px rgba(2,6,23,0.65);
            border-color: rgba(50,178,150,0.06);
        }
        .fnv-card:hover::before {
            opacity: 1;
            transform: rotate(-18deg) translateX(20%);
        }
        .fnv-ev {
            transition: transform 0.12s ease, box-shadow 0.12s ease;
            display:inline-block;
        }
        .fnv-ev:hover { transform: scale(1.06); box-shadow: 0 6px 14px rgba(0,0,0,0.25); }
        .fnv-btn { transition: transform 0.12s ease; display:inline-block; }
        .fnv-btn:hover { transform: translateY(-2px); }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # determine competitions and assign each competition to one of three columns
    comps = recommended["Compétition"].fillna("Autre").astype(str)
    unique_comps = list(dict.fromkeys(comps))  # preserve order

    cols = st.columns(3)
    comp_to_col = {comp: cols[i % 3] for i, comp in enumerate(unique_comps)}

    for comp, col in comp_to_col.items():
        comp_rows = recommended[
            recommended["Compétition"].fillna("Autre").astype(str) == comp
        ]
        with col:
            st.markdown(f"### {comp} ({len(comp_rows)})")

            # Group by tournament within this competition and show each tournament in an expander
            tourneys = (
                comp_rows["Tournoi"].fillna("Autre").astype(str).unique().tolist()
            )
            # Preserve original order: use list(dict.fromkeys(...)) if necessary
            tourneys = list(dict.fromkeys(tourneys))

            for tournoi in tourneys:
                t_rows = comp_rows[
                    comp_rows["Tournoi"].fillna("Autre").astype(str) == tournoi
                ]
                # Show tournament as an expander to allow collapsing when many tournaments
                with st.expander(f"{tournoi} ({len(t_rows)})", expanded=False):
                    for _, r in t_rows.iterrows():
                        link = r.get("Lien") or "#"
                        time_str = r.get("Heure") or ""
                        # determine EV badge color
                        try:
                            evf = float(r.get("EV_pct") or 0)
                        except Exception:
                            evf = 0.0
                        if evf > 10:
                            ev_bg = "#6a0dad"
                            ev_color = "#ffffff"
                        elif evf < 2 and evf > 0:
                            ev_bg = "#ff8c00"
                            ev_color = "#ffffff"
                        elif evf > 0:
                            ev_bg = "#32b296"
                            ev_color = "#ffffff"
                        else:
                            ev_bg = "#e04e4e"
                            ev_color = "#ffffff"

                        # build search / direct links for Flashscore and OddsPortal
                        try:
                            q = (
                                (f"{r.get('Match', '')} {r.get('Joueur', '')}")
                                .strip()
                                .replace(" ", "+")
                            )
                        except Exception:
                            q = ""

                        # OddsPortal: prefer provided direct link in 'Lien'
                        odds_url = (
                            r.get("Lien") or f"https://www.oddsportal.com/search/?q={q}"
                        )

                        # Flashscore: prefer an ID if present, else fallback to search
                        flash_id = (
                            r.get("ID_MATCH")
                            or r.get("flashscore_id")
                            or r.get("flashscore")
                        )
                        if flash_id:
                            flash_url = f"https://www.flashscore.com/match/{flash_id}"
                        else:
                            flash_url = f"https://www.flashscore.com/search/?q={q}"

                        # Compact buttons styled smaller
                        btn_style_flash = "display:inline-block;background:#ff2d55;color:#ffffff;padding:5px 8px;border-radius:6px;font-weight:700;font-size:12px;"
                        btn_style_odds = "display:inline-block;background:#0ea5a0;color:#ffffff;padding:5px 8px;border-radius:6px;font-weight:700;font-size:12px;"

                        # Card styled similar to match_card.py but with compact buttons and animation classes
                        html = f"""
                        <div style='padding:6px;'>
                          <div class='fnv-card' style='font-family:Segoe UI, Roboto, sans-serif;color:#e6eef8;'>
                            <div style='display:grid;grid-template-columns:1fr 120px;gap:10px;align-items:center;'>
                              <div style='min-width:0'>
                                <div style='font-size:15px;font-weight:700;color:#ffffff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{r["Match"]} — {r["Joueur"]}</div>
                                <div style='color:#9ca3af;font-size:12px;margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;'>
                                  <span style='background:rgba(255,255,255,0.03);padding:5px 6px;border-radius:6px;font-size:12px;'>Prédiction: {r["Prédiction"]:.3f}</span>
                                  <span style='background:rgba(255,255,255,0.03);padding:5px 6px;border-radius:6px;font-size:12px;'>Cote: {r["Max_cote"]:.3f}</span>
                                  <span class='fnv-ev' style='background:{ev_bg};color:{ev_color};padding:5px 6px;border-radius:999px;font-weight:700;font-size:12px;'>EV: {r["EV_pct"]:+.1f}%</span>
                                </div>
                                <div style='color:#9ca3af;font-size:12px;margin-top:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>Tournoi: {r["Tournoi"]}</div>
                              </div>
                              <div style='text-align:right'>
                                <div style='font-size:13px;color:#cbd5e1;font-weight:700'>{time_str}</div>
                                <div style='margin-top:8px;display:flex;gap:6px;justify-content:flex-end;'>
                                  <a href='{flash_url}' target='_blank' style='text-decoration:none'><span class='fnv-btn' style='{btn_style_flash}'>Flash</span></a>
                                  <a href='{odds_url}' target='_blank' style='text-decoration:none'><span class='fnv-btn' style='{btn_style_odds}'>Odds</span></a>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                        """
                        st.markdown(html, unsafe_allow_html=True)
else:
    st.info("Aucune opportunité de pari positive détectée selon les critères.")
