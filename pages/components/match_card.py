import streamlit as st
import pandas as pd


def render_match_info(bets_data: pd.DataFrame, selected: list) -> None:
    """Render the right-hand Match info card based on selection or last match."""
    # Check if bets_data is empty
    if bets_data.empty:
        st.info("Aucun match à afficher")
        return

    try:
        if selected and len(selected) > 0:
            idx = selected[0]["point_index"]
            match = bets_data.iloc[idx]
        else:
            match = bets_data.iloc[-1]
    except Exception:
        # If there's any error accessing the match, show message and return
        st.info("Aucun match à afficher")
        return

    gain_color = "#32b296" if match["Gains net"] > 0 else "#e04e4e"
    outcome_text = "Gagné" if match["Gains net"] > 0 else "Perdu"
    outcome_bg = (
        "rgba(50,178,150,0.12)" if match["Gains net"] > 0 else "rgba(224,78,78,0.12)"
    )

    try:
        mise = float(match.get("Mise", 0))
        marge_val = float(match.get("Marge attendue", 0))
        marge_pct = (marge_val / mise * 100) if mise > 0 else 0.0
    except Exception:
        marge_pct = 0.0

    scaled_width_pct = max(0.0, min(100.0, (marge_pct / 10.0) * 100.0))

    if marge_pct >= 10:
        bar_width = "100%"
        bar_gradient = "linear-gradient(90deg,#16a34a,#06b6d4)"
        bar_note = "<span style='color:#a7f3d0;font-weight:700;'>🔥 Forte marge</span>"
    else:
        bar_width = f"{int(round(scaled_width_pct))}%"
        bar_gradient = "linear-gradient(90deg,#9ca3af,#6b7280)"
        bar_note = ""

    # Get competition color
    comp_lower = str(match.get("Compétition", "")).lower()
    comp_color_map = {
        "atp": "#10b981",  # Vert émeraude pour ATP
        "wta": "#ec4899",  # Rose pour WTA
        "doubles": "#8b5cf6",  # Violet pour Doubles
        "challenger": "#6366f1",  # Bleu indigo pour Challenger
    }
    comp_color = comp_color_map.get(comp_lower, "#9ca3af")

    card_html = f"""
    <div style='background:linear-gradient(180deg, rgba(18,20,24,0.9), rgba(23,25,30,0.85));border-radius:14px;padding:18px;border:1px solid rgba(255,255,255,0.04);box-shadow:0 6px 18px rgba(0,0,0,0.45);font-family:Segoe UI, Roboto, sans-serif;color:#e6eef8;'>
        <div style='display:grid;grid-template-columns:1fr 120px;gap:16px;align-items:center;'>
            <div>
                <div style='font-size:18px;font-weight:700;color:#ffffff;margin-bottom:6px;'>{match["Match"]}</div>
                <div style='color:#9ca3af;font-size:13px;margin-bottom:10px;'><span style='color:{comp_color};font-weight:700;'>{match["Compétition"]}</span> — {match["Level"]} • {match["Surface"]} • {match["Round"]}</div>
                <div style='display:flex;gap:12px;flex-wrap:wrap;'>
                    <div style='background:rgba(255,255,255,0.03);padding:8px;border-radius:8px;font-size:13px;color:#cbd5e1;'>📅 {match["Date"]}</div>
                    <div style='background:rgba(255,255,255,0.03);padding:8px;border-radius:8px;font-size:13px;color:#cbd5e1;'>🎾 Joueur: {match["player_bet"]}</div>
                    <div style='background:rgba(255,255,255,0.03);padding:8px;border-radius:8px;font-size:13px;color:#cbd5e1;'>💰 Mise: {match["Mise"]:.2f}€</div>
                    <div style='background:rgba(255,255,255,0.03);padding:8px;border-radius:8px;font-size:13px;color:#cbd5e1;'>📊 Cote: {match["Cote"]:.3f}</div>
                </div>
            </div>
            <div style='text-align:center;'>
                <div style='display:inline-block;padding:12px;border-radius:999px;background:{outcome_bg};border:1px solid rgba(255,255,255,0.04);min-width:96px;'>
                    <div style='font-size:12px;color:#9ca3af;margin-bottom:6px;'>Résultat</div>
                    <div style='font-size:20px;font-weight:800;color:{gain_color};'>{match["Gains net"]:+.2f}€</div>
                    <div style='margin-top:6px;font-size:12px;color:#cbd5e1;padding:6px 10px;border-radius:999px;background:rgba(0,0,0,0.18);display:inline-block;'>
                        {outcome_text}
                    </div>
                </div>
                <div style='margin-top:12px;text-align:left;'>
                    <div style='font-size:12px;color:#9ca3af;margin-bottom:6px;'>🔮 Marge</div>
                    <div style='background:rgba(255,255,255,0.04);height:12px;border-radius:8px;overflow:hidden;'>
                        <div style='width:{bar_width};height:100%;background:{bar_gradient};'></div>
                    </div>
                    <div style='font-size:12px;color:#cbd5e1;margin-top:6px;'>{marge_pct:.1f}% de marge {bar_note}</div>
                </div>
            </div>
        </div>
        <hr style='opacity:0.08;margin:14px 0;'>
        <div style='display:flex;gap:12px;flex-wrap:wrap;font-size:13px;color:#cbd5e1;'>
            <div style='flex:1;min-width:160px;'><b style='color:#e6eef8;'>Cumul :</b> {match["Cumulative Gains"]:.2f}€</div>
            <div style='flex:1;min-width:160px;'><b style='color:#e6eef8;'>Marge attendue :</b> {match["Marge attendue"]:.2f}€</div>
            <div style='flex:1;min-width:160px;'><b style='color:#e6eef8;'>ID Pari :</b> {match.name}</div>
        </div>
    </div>
    """

    # Center the card horizontally within its column
    centered = f"<div style='display:flex;justify-content:center;'> {card_html} </div>"
    st.markdown(centered, unsafe_allow_html=True)
