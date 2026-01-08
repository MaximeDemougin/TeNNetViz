import streamlit as st
import pandas as pd


def render_metrics(bets_data: pd.DataFrame) -> dict:
    """Calculate statistics and render the four metric cards.

    Returns a dict with the calculated totals for downstream use.
    """
    total_bets = len(bets_data)
    total_mises = bets_data["Mise"].sum()
    total_gains = bets_data["Gains net"].sum()
    total_marges = bets_data["Marge attendue"].sum()
    wins = len(bets_data[bets_data["Gains net"] > 0])
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    roi = (total_gains / total_mises * 100) if total_mises > 0 else 0
    marge_percentage = (total_marges / total_mises * 100) if total_mises > 0 else 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_bets_fmt = f"{total_bets:,}".replace(",", " ")
        wins_fmt = f"{wins:,}".replace(",", " ")
        st.markdown(
            f"""
        <div class='metric-card card-green' style='border: 1px solid rgba(50,178,150,0.2);'>
            <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>📝 Total Paris</div>
            <div style='font-size: 32px; font-weight: 700; color: #32b296;'>{total_bets_fmt}</div>
            <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>{wins_fmt} gagnés</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        mises_formatted = f"{total_mises:,.0f}".replace(",", " ")
        st.markdown(
            f"""
        <div class='metric-card card-yellow' style='border: 1px solid rgba(251,191,36,0.2);'>
            <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>💰 Mises totales</div>
            <div style='font-size: 32px; font-weight: 700; color: #fbbf24;'>{mises_formatted}€</div>
            <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>Total misé</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        gains_formatted = f"{total_gains:+,.0f}".replace(",", " ")
        roi_formatted = f"{roi:+.1f}%"
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
            <div style='color: #9ca3af; font-size: 14px, margin-bottom: 8px;'>💸 Gains nets</div>
            <div style='font-size: 32px; font-weight: 700; color: {gain_color};'>{gains_formatted}€</div>
            <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>ROI: {roi_formatted}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        total_marges_fmt = f"{total_marges:+,.0f}".replace(",", " ")
        marge_pct_fmt = f"{marge_percentage:+.1f}%"
        marge_color = "#3b82f6" if total_marges > 0 else "#e04e4e"
        st.markdown(
            f"""
        <div class='metric-card card-blue' style='border: 1px solid rgba(59,130,246,0.2);'>
            <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>📈 Gains attendus</div>
            <div style='font-size: 32px; font-weight: 700; color: {marge_color};'>{total_marges_fmt}€</div>
            <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>{marge_pct_fmt} des mises</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    return {
        "total_bets": total_bets,
        "total_mises": total_mises,
        "total_gains": total_gains,
        "total_marges": total_marges,
        "wins": wins,
        "win_rate": win_rate,
        "roi": roi,
        "marge_percentage": marge_percentage,
    }
