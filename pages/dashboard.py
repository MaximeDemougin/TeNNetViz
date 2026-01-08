import streamlit as st
import plotly.express as px
from data import prepare_bets_data

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

st.title("Les résultats TeNNet", text_alignment="center")
# You can add more dashboard components here as needed.
# For example, display user-specific data if logged in
if st.session_state.get("logged_in", False):
    bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=True)
    if not bets_data.empty:
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
        st.markdown("### 📊 Vue d'ensemble")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f"""
            <div class='metric-card card-green' style='border: 1px solid rgba(50,178,150,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>📝 Total Paris</div>
                <div style='font-size: 32px; font-weight: 700; color: #32b296;'>{total_bets:,}</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>{wins} gagnés</div>
            </div>
            """.replace(
                    ",", " "
                ),
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                f"""
            <div class='metric-card card-yellow' style='border: 1px solid rgba(251,191,36,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>💰 Mises totales</div>
                <div style='font-size: 32px; font-weight: 700; color: #fbbf24;'>{total_mises:,.0f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>investis</div>
            </div>
            """.replace(
                    ",", " "
                ),
                unsafe_allow_html=True,
            )

        with col3:
            gain_color = "#32b296" if total_gains > 0 else "#e04e4e"
            gain_card_class = (
                "card-gains-positive" if total_gains > 0 else "card-gains-negative"
            )
            border_color = (
                "rgba(50,178,150,0.2)" if total_gains > 0 else "rgba(224,78,78,0.2)"
            )
            st.markdown(
                f"""
            <div class='metric-card {gain_card_class}' style='border: 1px solid {border_color};'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>💸 Gains nets</div>
                <div style='font-size: 32px; font-weight: 700; color: {gain_color};'>{total_gains:+,.0f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>ROI: {roi:+.1f}%</div>
            </div>
            """.replace(
                    ",", " "
                ),
                unsafe_allow_html=True,
            )

        with col4:
            marge_color = "#3b82f6" if total_marges > 0 else "#e04e4e"
            st.markdown(
                f"""
            <div class='metric-card card-blue' style='border: 1px solid rgba(59,130,246,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>📈 Marges attendues</div>
                <div style='font-size: 32px; font-weight: 700; color: {marge_color};'>{total_marges:+,.0f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>{marge_percentage:+.1f}% des mises</div>
            </div>
            """.replace(
                    ",", " "
                ),
                unsafe_allow_html=True,
            )

        st.divider()

        col1, col2, col3 = st.columns([7, 1, 4])
        with col1:
            # Préparer les données pour le graphique
            bets_data_reset = bets_data.reset_index(drop=True)
            bets_data_reset["Match_Num"] = range(len(bets_data_reset))

            fig = px.line(
                bets_data_reset,
                x="Match_Num",
                y="Cumulative Gains",
                markers=True,
                labels={
                    "Match_Num": "Match #",
                    "Cumulative Gains": "Gains nets cumulés",
                },
            )

            fig.update_traces(
                line_color="#32b296", line_width=2, marker=dict(size=1, color="#32b296")
            )
            # add trace cumulative marge in white
            bets_data_reset["Cumulative_Marge"] = bets_data_reset[
                "Marge attendue"
            ].cumsum()
            # fig.add_trace(
            #     px.line(
            #         bets_data_reset,
            #         x="Match_Num",
            #         y="Cumulative_Marge",
            #         markers=False,
            #     ).data[0]
            # )

            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#d1d4dc"),
                hovermode="x",
                # make markers invisible until hover
                # hoverlabel=dict(bgcolor="white", font_size=12, font_family="Segoe UI"),
            )

            # Affichage dans une carte
            with st.container(border=True):
                st.markdown("### 📈 Évolution des gains nets", text_alignment="center")
                event_dict = st.plotly_chart(
                    fig,
                    height="content",
                    selection_mode="points",
                    on_select="rerun",
                    use_container_width=True,
                )
            selected = event_dict["selection"]["points"]

        with col3:
            st.markdown("### Info Match", text_alignment="center")
            print(selected)

            # Get selected match or default to last
            if selected and len(selected) > 0:
                idx = selected[0]["point_index"]
                match = bets_data.iloc[idx]
            else:
                match = bets_data.iloc[-1]

            gain_color = "#32b296" if match["Gains net"] > 0 else "#e04e4e"

            html = f"""<div style='background:rgba(25,28,35,0.85);border-radius:16px;padding:22px 26px;border:1px solid rgba(255,255,255,0.06);box-shadow:0 4px 12px rgba(0,0,0,0.3);backdrop-filter:blur(6px);font-family:Segoe UI,sans-serif;color:#e0e0e0;text-align:center;line-height:1.6;'><h3 style='margin:0 0 16px 0;font-size:22px;color:#32b296;'>{match["Match"]}</h3><div style='display:grid;grid-template-columns:1fr 1fr;gap:14px;text-align:center;'><div><p><b>📅 Date :</b><br>{match["Date"]}</p></div><div><p><b>🎾 Joueur :</b><br>{match["player_bet"]}</p></div><div><p><b>🏆 Compétition :</b><br>{match["Compétition"]} – {match["Level"]}</p></div><div><p><b>🏟️ Surface :</b><br>{match["Surface"]}</p></div><div><p><b>🎯 Round :</b><br>{match["Round"]}</p></div><div><p><b>💰 Mise :</b><br>{match["Mise"]:.2f}€</p></div><div><p><b>📊 Cote :</b><br>{match["Cote"]:.3f}</p></div><div><p><b>🔮 Prédiction :</b><br>{match["Prédiction"]:.3f}</p></div></div><hr style='opacity:0.15;margin:18px 0;'><p><b>💸 Gains net :</b> <span style='color:{gain_color};font-weight:600;'>{match["Gains net"]:+.2f}€</span></p><p><b>📈 Cumul :</b> {match["Cumulative Gains"]:.2f}€</p></div>"""

            st.markdown(html, unsafe_allow_html=True)
        st.markdown("### Détail des paris", text_alignment="center")
        st.dataframe(
            bets_data.sort_values(by="Date", ascending=False).drop(
                columns=["Cumulative Gains"]
            ),
        )

    else:
        st.write("No bets found.")
else:
    st.write("Please log in to see your dashboard.")
