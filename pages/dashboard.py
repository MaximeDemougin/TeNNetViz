import streamlit as st
import plotly.express as px

st.set_page_config(layout="wide")


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
    bets_data = prepare_bets_data(st.session_state["ID_USER"])
    if not bets_data.empty:
        col1, col2, col3 = st.columns([7, 1, 4])
        with col1:
            st.markdown("### Évolution des gains nets", text_alignment="center")

            # Prepare data for plotting
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

            event_dict = st.plotly_chart(
                fig,
                height="content",
                selection_mode="points",
                on_select="rerun",
            )
            print(event_dict)
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
