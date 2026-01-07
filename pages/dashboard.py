import streamlit as st
from streamlit_lightweight_charts import renderLightweightCharts
from data import prepare_bets_data, prep_candle_data
import plotly.express as px
from streamlit_plotly_events import plotly_events

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
        col1, col2 = st.columns([7, 5])
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
                line_color="#32b296", line_width=2, marker=dict(size=8, color="#32b296")
            )

            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#d1d4dc"),
                hovermode="closest",
            )

            # Capture click events (this also displays the chart)
            selected = plotly_events(
                fig,
                click_event=True,
                hover_event=False,
                select_event=False,
                key="chart1",
            )

        with col2:
            st.markdown("### Info Match", text_alignment="center")

            # Get selected match or default to last
            if selected and len(selected) > 0:
                idx = selected[0]["pointIndex"]
                match = bets_data.iloc[idx]
            else:
                match = bets_data.iloc[-1]

            # Simple card display
            st.markdown(f"**{match['Match']}**")
            st.write(f"📅 {match['Date']}")
            st.write(f"🎾 {match['player_bet']}")
            st.write(f"🏆 {match['Compétition']} - {match['Level']}")
            st.write(f"🎯 {match['Round']} | 🏟️ {match['Surface']}")
            st.divider()
            st.write(f"💰 Mise: {match['Mise']:.2f}€")
            st.write(f"📊 Cote: {match['Cote']:.3f}")
            st.write(f"🔮 Prédiction: {match['Prédiction']:.3f}")
            st.divider()
            gain_color = "green" if match["Gains net"] > 0 else "red"
            st.markdown(f"**Gains net:** :{gain_color}[{match['Gains net']:+.2f}€]")
            st.write(f"📈 Cumul: {match['Cumulative Gains']:.2f}€")

        st.markdown("### Détail des paris", text_alignment="center")
        st.dataframe(
            bets_data.sort_values(by="Date", ascending=False).drop(
                columns=["Cumulative Gains"]
            ),
            use_container_width=True,
        )

    else:
        st.write("No bets found.")
else:
    st.write("Please log in to see your dashboard.")
