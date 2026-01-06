import streamlit as st
from data import prepare_bets_data

st.set_page_config(layout="wide")

st.title("Les résultats TeNNet", text_alignment="center")
# You can add more dashboard components here as needed.
# For example, display user-specific data if logged in
if st.session_state.get("logged_in", False):
    bets_data = prepare_bets_data(st.session_state["ID_USER"])
    if not bets_data.empty:
        bets_data["cumsum"] = bets_data["Gains net"].cumsum()
        col1, col2, col3 = st.columns([1, 6, 1])
        with col2:
            st.markdown("### Évolution des gains nets", text_alignment="center")
            st.line_chart(bets_data, y="cumsum", color="#32b296")
        st.markdown("### Détail des paris", text_alignment="center")
        st.dataframe(
            bets_data.sort_values(by="Date", ascending=False).drop(columns=["cumsum"]),
            use_container_width=True,
        )

    else:
        st.write("No bets found.")
else:
    st.write("Please log in to see your dashboard.")
