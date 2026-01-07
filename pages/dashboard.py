import streamlit as st
from streamlit_lightweight_charts import renderLightweightCharts
from data import prepare_bets_data, prep_candle_data

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
        col1, col2, col3 = st.columns([1, 6, 1])
        with col2:
            st.markdown("### Évolution des gains nets", text_alignment="center")
            st.line_chart(bets_data, y="Cumulative Gains", color="#32b296")
            seriesCandlestickChart = [
                {
                    "type": "Candlestick",
                    "data": prep_candle_data(st.session_state["ID_USER"]),
                    "options": {
                        "upColor": "#26a69a",
                        "downColor": "#CA4F4F",
                        "borderVisible": False,
                        "wickUpColor": "#26a69a",
                        "wickDownColor": "#ef5350",
                    },
                }
            ]
            # st.subheader("Candlestick Chart with Watermark", text_alignment="center")
            renderLightweightCharts(
                [{"chart": chartOptions, "series": seriesCandlestickChart}],
                "candlestick",
            )

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
