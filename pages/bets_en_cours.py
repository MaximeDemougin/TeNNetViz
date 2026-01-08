import streamlit as st
from data import prepare_bets_data

st.set_page_config(layout="wide")

st.title("Paris en cours", text_alignment="center")


def display_bet_cards(bets_df, cols_per_row=3):
    """Display bet cards in a grid layout"""
    if bets_df.empty:
        st.info("Aucun pari dans cette catégorie.")
        return

    rows = [
        bets_df.iloc[i : i + cols_per_row] for i in range(0, len(bets_df), cols_per_row)
    ]

    for row_data in rows:
        cols = st.columns(cols_per_row)
        for idx, (_, bet) in enumerate(row_data.iterrows()):
            with cols[idx]:
                # Calculate potential gain
                potential_gain = bet["Mise"] * bet["Cote"] - bet["Mise"]

                # Calculate marge percentage
                marge_percentage = (
                    (bet["Marge attendue"] / bet["Mise"] * 100)
                    if bet["Mise"] > 0
                    else 0
                )

                # Build Flashscore URL
                flashscore_url = f"https://www.flashscore.fr/match/{bet['ID_MATCH']}"

                # Create card HTML with hover effects and clickable link
                card_html = f"""
                <style>
                    .bet-card {{
                        background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 16px;
                        padding: 20px;
                        border: 1px solid rgba(50,178,150,0.2);
                        box-shadow: 0 4px 12px rgba(0,0,0,0.3), 0 2px 4px rgba(0,0,0,0.2);
                        backdrop-filter: blur(6px);
                        font-family: Segoe UI, sans-serif;
                        color: #e0e0e0;
                        margin-bottom: 20px;
                        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                        cursor: pointer;
                        position: relative;
                        text-decoration: none !important;
                        display: block;
                    }}
                    .bet-card:hover {{
                        transform: translateY(-2px) scale(1.01);
                        border-color: rgba(50,178,150,0.5);
                        text-decoration: none !important;
                    }}
                    .bet-card * {{
                        text-decoration: none !important;
                    }}
                </style>
                <a href='{flashscore_url}' target='_blank' class='bet-card' style='color: inherit; text-decoration: none !important;'>
                    <h3 style='
                        margin: 0 0 16px 0;
                        font-size: 18px;
                        color: #32b296;
                        text-align: center;
                        border-bottom: 1px solid rgba(255,255,255,0.1);
                        padding-bottom: 12px;
                    '>{bet["Match"]}</h3>
                    <div style='margin: 12px 0;'>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>📅 Date</span>
                            <span style='font-weight: 600;'>{bet["Date"]}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>🎾 Pari sur</span>
                            <span style='font-weight: 600; color: #32b296;'>{bet["player_bet"]}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>🏟️ Surface</span>
                            <span>{bet["Surface"]}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>🎯 Round</span>
                            <span>{bet["Round"]}</span>
                        </div>
                    </div>
                    <hr style='opacity: 0.15; margin: 16px 0;'>
                    <div style='margin: 12px 0;'>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>💰 Mise</span>
                            <span style='font-weight: 600; color: #fbbf24;'>{bet["Mise"]:.2f}€</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>📊 Cote</span>
                            <span style='font-weight: 600;'>{bet["Cote"]:.3f}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>🔮 Prédiction</span>
                            <span style='font-weight: 600;'>{bet["Prédiction"]:.3f}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; margin: 8px 0;'>
                            <span style='color: #9ca3af; font-size: 14px;'>📈 Marge</span>
                            <span style='color: {"#c026d3" if bet["Marge attendue"] > 0 else "#e04e4e"}; font-weight: 600;'>{bet["Marge attendue"]:+.2f}€ ({marge_percentage:+.1f}%)</span>
                        </div>
                    </div>
                    <hr style='opacity: 0.15; margin: 16px 0;'>
                    <div style='
                        background: rgba(50,178,150,0.1);
                        border-radius: 8px;
                        padding: 12px;
                        text-align: center;
                    '>
                        <div style='color: #9ca3af; font-size: 13px; margin-bottom: 4px;'>💸 Gain potentiel</div>
                        <div style='
                            font-size: 20px;
                            font-weight: 700;
                            color: #32b296;
                        '>{potential_gain:+.2f}€</div>
                    </div>
                    <div style='
                        margin-top: 12px;
                        text-align: center;
                        font-size: 12px;
                        color: #9ca3af;
                        opacity: 0.7;
                    '>
                        🔗 Cliquez pour voir sur Flashscore
                    </div>
                </a>
                """
                st.markdown(card_html, unsafe_allow_html=True)


if st.session_state.get("logged_in", False):
    bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=False)

    if not bets_data.empty:
        # Calculate potential gains for all bets
        bets_data["Gain potentiel"] = (
            bets_data["Mise"] * bets_data["Cote"] - bets_data["Mise"]
        )

        # Separate bets by competition type
        atp_bets = bets_data[bets_data["Compétition"] == "atp"]
        wta_bets = bets_data[bets_data["Compétition"] == "wta"]
        doubles_bets = bets_data[bets_data["Compétition"] == "doubles"]

        # Calculate totals
        total_mises = bets_data["Mise"].sum()
        total_gains_potentiels = bets_data["Gain potentiel"].sum()
        total_marges = bets_data["Marge attendue"].sum()
        total_marge_percentage = (
            (total_marges / total_mises * 100) if total_mises > 0 else 0
        )

        # Display summary statistics with cards
        st.markdown("### 📊 Vue d'ensemble")

        # Add global CSS for metric cards
        st.markdown(
            """
        <style>
            .metric-card {
                background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                border-radius: 12px;
                padding: 16px;
                box-shadow: 
                    6px 6px 12px rgba(0,0,0,0.4),
                    4px 4px 8px rgba(0,0,0,0.3),
                    2px 2px 4px rgba(0,0,0,0.2),
                    inset -1px -1px 2px rgba(0,0,0,0.5);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                cursor: pointer;
                position: relative;
                overflow: hidden;
            }
            .metric-card:hover {
                transform: translateY(-6px) translateX(-2px) scale(1.01);
            }
            
            /* Effet ombre verte pour Total Paris */
            .metric-card.card-green:hover {
                box-shadow: 
                    10px 10px 20px rgba(0,0,0,0.5),
                    8px 8px 16px rgba(0,0,0,0.4),
                    0 0 20px rgba(50,178,150,0.6),
                    0 0 40px rgba(50,178,150,0.3),
                    inset 0 0 20px rgba(50,178,150,0.1);
                border-color: rgba(50,178,150,0.8) !important;
            }
            
            /* Effet ombre jaune pour Mises totales */
            .metric-card.card-yellow:hover {
                box-shadow: 
                    10px 10px 20px rgba(0,0,0,0.5),
                    8px 8px 16px rgba(0,0,0,0.4),
                    0 0 20px rgba(251,191,36,0.6),
                    0 0 40px rgba(251,191,36,0.3),
                    inset 0 0 20px rgba(251,191,36,0.1);
                border-color: rgba(251,191,36,0.8) !important;
            }
            
            /* Effet ombre verte pour Gains potentiels */
            .metric-card.card-gains:hover {
                box-shadow: 
                    10px 10px 20px rgba(0,0,0,0.5),
                    8px 8px 16px rgba(0,0,0,0.4),
                    0 0 20px rgba(50,178,150,0.6),
                    0 0 40px rgba(50,178,150,0.3),
                    inset 0 0 20px rgba(50,178,150,0.1);
                border-color: rgba(50,178,150,0.8) !important;
            }
            
            /* Effet ombre violette pour Marges attendues */
            .metric-card.card-purple:hover {
                box-shadow: 
                    10px 10px 20px rgba(0,0,0,0.5),
                    8px 8px 16px rgba(0,0,0,0.4),
                    0 0 20px rgba(192,38,211,0.6),
                    0 0 40px rgba(192,38,211,0.3),
                    inset 0 0 20px rgba(192,38,211,0.1);
                border-color: rgba(192,38,211,0.8) !important;
            }
            
            .metric-card::after {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(135deg, rgba(255,255,255,0.08), transparent);
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            .metric-card:hover::after {
                opacity: 1;
            .metric-card::before {
                content: '';
                position: absolute;
                bottom: -2px;
                right: -2px;
                width: 40%;
                height: 40%;
                border-radius: 0 0 12px 0;
                pointer-events: none;
            }
        </style>
        """,
            unsafe_allow_html=True,
        )

        # Global metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f"""
            <div class='metric-card card-green' style='border: 1px solid rgba(50,178,150,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>📝 Total Paris</div>
                <div style='font-size: 32px; font-weight: 700; color: #32b296;'>{len(bets_data)}</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>paris en cours</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                f"""
            <div class='metric-card card-yellow' style='border: 1px solid rgba(251,191,36,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>💰 Mises totales</div>
                <div style='font-size: 32px; font-weight: 700; color: #fbbf24;'>{total_mises:.2f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>engagés</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col3:
            gain_color = "#32b296" if total_gains_potentiels > 0 else "#e04e4e"
            st.markdown(
                f"""
            <div class='metric-card card-gains' style='border: 1px solid rgba(50,178,150,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>💸 Gains potentiels</div>
                <div style='font-size: 32px; font-weight: 700; color: {gain_color};'>{total_gains_potentiels:+.2f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>si tout gagne</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col4:
            marge_color = "#c026d3" if total_marges > 0 else "#e04e4e"
            st.markdown(
                f"""
            <div class='metric-card card-purple' style='border: 1px solid rgba(192,38,211,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>📈 Marges attendues</div>
                <div style='font-size: 32px; font-weight: 700; color: {marge_color};'>{total_marges:+.2f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>{total_marge_percentage:+.1f}% des mises</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        st.divider()

        # Competition-specific metrics
        st.markdown("### 🏆 Par compétition")

        # Add CSS for competition cards
        st.markdown(
            """
        <style>
            .comp-card {
                background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                border-radius: 12px;
                padding: 16px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                cursor: pointer;
            }
            .comp-card:not(.disabled):hover {
                transform: translateY(-2px) scale(1.01);
                box-shadow: 0 16px 32px rgba(0,0,0,0.4), 0 8px 16px rgba(0,0,0,0.2);
            }
            .comp-card.disabled {
                cursor: default;
            }
        </style>
        """,
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            atp_mises = atp_bets["Mise"].sum() if not atp_bets.empty else 0
            atp_gains = atp_bets["Gain potentiel"].sum() if not atp_bets.empty else 0
            atp_marges = atp_bets["Marge attendue"].sum() if not atp_bets.empty else 0

            # Style grisé si pas de paris
            is_empty = atp_bets.empty
            card_style = "opacity: 0.4; filter: grayscale(0.8);" if is_empty else ""
            border_color = (
                "rgba(150,150,150,0.2)" if is_empty else "rgba(59,130,246,0.3)"
            )
            title_color = "#6b7280" if is_empty else "#3b82f6"
            disabled_class = " disabled" if is_empty else ""

            # Format values - use dash if empty
            count_display = "—" if is_empty else str(len(atp_bets))
            mises_display = "—" if is_empty else f"{atp_mises:.2f}€"
            gains_display = "—" if is_empty else f"{atp_gains:+.2f}€"
            atp_marge_pct = (atp_marges / atp_mises * 100) if atp_mises > 0 else 0
            marges_display = (
                "—" if is_empty else f"{atp_marges:+.2f}€ ({atp_marge_pct:+.1f}%)"
            )
            marges_color = (
                "#6b7280" if is_empty else ("#c026d3" if atp_marges > 0 else "#e04e4e")
            )

            # Add link if not empty
            if is_empty:
                st.markdown(
                    f"""
                <div class='comp-card{disabled_class}' style='border: 1px solid {border_color}; {card_style}'>
                    <div style='text-align: center; font-size: 18px; font-weight: 600; color: {title_color}; margin-bottom: 12px;'>🎾 ATP</div>
                    <div style='margin: 8px 0;'>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                            <span style='font-weight: 600;'>{count_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                            <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#fbbf24"};'>{mises_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                            <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#32b296"};'>{gains_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                            <span style='font-weight: 600; color: {marges_color};'>{marges_display}</span>
                        </div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                <a href='#atp-section' style='text-decoration: none; color: inherit;'>
                    <div class='comp-card{disabled_class}' style='border: 1px solid {border_color}; {card_style}'>
                        <div style='text-align: center; font-size: 18px; font-weight: 600; color: {title_color}; margin-bottom: 12px;'>🎾 ATP</div>
                        <div style='margin: 8px 0;'>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                                <span style='font-weight: 600;'>{count_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                                <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#fbbf24"};'>{mises_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                                <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#32b296"};'>{gains_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                                <span style='font-weight: 600; color: {marges_color};'>{marges_display}</span>
                            </div>
                        </div>
                    </div>
                </a>
                """,
                    unsafe_allow_html=True,
                )

        with col2:
            wta_mises = wta_bets["Mise"].sum() if not wta_bets.empty else 0
            wta_gains = wta_bets["Gain potentiel"].sum() if not wta_bets.empty else 0
            wta_marges = wta_bets["Marge attendue"].sum() if not wta_bets.empty else 0

            # Style grisé si pas de paris
            is_empty = wta_bets.empty
            card_style = "opacity: 0.4; filter: grayscale(0.8);" if is_empty else ""
            border_color = (
                "rgba(150,150,150,0.2)" if is_empty else "rgba(236,72,153,0.3)"
            )
            title_color = "#6b7280" if is_empty else "#ec4899"
            disabled_class = " disabled" if is_empty else ""

            # Format values - use dash if empty
            count_display = "—" if is_empty else str(len(wta_bets))
            mises_display = "—" if is_empty else f"{wta_mises:.2f}€"
            gains_display = "—" if is_empty else f"{wta_gains:+.2f}€"
            wta_marge_pct = (wta_marges / wta_mises * 100) if wta_mises > 0 else 0
            marges_display = (
                "—" if is_empty else f"{wta_marges:+.2f}€ ({wta_marge_pct:+.1f}%)"
            )
            marges_color = (
                "#6b7280" if is_empty else ("#c026d3" if wta_marges > 0 else "#e04e4e")
            )

            # Add link if not empty
            if is_empty:
                st.markdown(
                    f"""
                <div class='comp-card{disabled_class}' style='border: 1px solid {border_color}; {card_style}'>
                    <div style='text-align: center; font-size: 18px; font-weight: 600; color: {title_color}; margin-bottom: 12px;'>👩‍🦰 WTA</div>
                    <div style='margin: 8px 0;'>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                            <span style='font-weight: 600;'>{count_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                            <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#fbbf24"};'>{mises_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                            <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#32b296"};'>{gains_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                            <span style='font-weight: 600; color: {marges_color};'>{marges_display}</span>
                        </div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                <a href='#wta-section' style='text-decoration: none; color: inherit;'>
                    <div class='comp-card{disabled_class}' style='border: 1px solid {border_color}; {card_style}'>
                        <div style='text-align: center; font-size: 18px; font-weight: 600; color: {title_color}; margin-bottom: 12px;'>👩‍🦰 WTA</div>
                        <div style='margin: 8px 0;'>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                                <span style='font-weight: 600;'>{count_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                                <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#fbbf24"};'>{mises_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                                <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#32b296"};'>{gains_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                                <span style='font-weight: 600; color: {marges_color};'>{marges_display}</span>
                            </div>
                        </div>
                    </div>
                </a>
                """,
                    unsafe_allow_html=True,
                )

        with col3:
            doubles_mises = doubles_bets["Mise"].sum() if not doubles_bets.empty else 0
            doubles_gains = (
                doubles_bets["Gain potentiel"].sum() if not doubles_bets.empty else 0
            )
            doubles_marges = (
                doubles_bets["Marge attendue"].sum() if not doubles_bets.empty else 0
            )

            # Style grisé si pas de paris
            is_empty = doubles_bets.empty
            card_style = "opacity: 0.4; filter: grayscale(0.8);" if is_empty else ""
            border_color = (
                "rgba(150,150,150,0.2)" if is_empty else "rgba(192,38,211,0.3)"
            )
            title_color = "#6b7280" if is_empty else "#c026d3"
            disabled_class = " disabled" if is_empty else ""

            # Format values - use dash if empty
            count_display = "—" if is_empty else str(len(doubles_bets))
            mises_display = "—" if is_empty else f"{doubles_mises:.2f}€"
            gains_display = "—" if is_empty else f"{doubles_gains:+.2f}€"
            doubles_marge_pct = (
                (doubles_marges / doubles_mises * 100) if doubles_mises > 0 else 0
            )
            marges_display = (
                "—"
                if is_empty
                else f"{doubles_marges:+.2f}€ ({doubles_marge_pct:+.1f}%)"
            )
            marges_color = (
                "#6b7280"
                if is_empty
                else ("#c026d3" if doubles_marges > 0 else "#e04e4e")
            )

            # Add link if not empty
            if is_empty:
                st.markdown(
                    f"""
                <div class='comp-card{disabled_class}' style='border: 1px solid {border_color}; {card_style}'>
                    <div style='text-align: center; font-size: 18px; font-weight: 600; color: {title_color}; margin-bottom: 12px;'>🤝 Doubles</div>
                    <div style='margin: 8px 0;'>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                            <span style='font-weight: 600;'>{count_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                            <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#fbbf24"};'>{mises_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                            <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#32b296"};'>{gains_display}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                            <span style='font-weight: 600; color: {marges_color};'>{marges_display}</span>
                        </div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                <a href='#doubles-section' style='text-decoration: none; color: inherit;'>
                    <div class='comp-card{disabled_class}' style='border: 1px solid {border_color}; {card_style}'>
                        <div style='text-align: center; font-size: 18px; font-weight: 600; color: {title_color}; margin-bottom: 12px;'>🤝 Doubles</div>
                        <div style='margin: 8px 0;'>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                                <span style='font-weight: 600;'>{count_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                                <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#fbbf24"};'>{mises_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                                <span style='font-weight: 600; color: {"#6b7280" if is_empty else "#32b296"};'>{gains_display}</span>
                            </div>
                            <div style='display: flex; justify-content: space-between;'>
                                <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                                <span style='font-weight: 600; color: {marges_color};'>{marges_display}</span>
                            </div>
                        </div>
                    </div>
                </a>
                """,
                    unsafe_allow_html=True,
                )

        st.divider()

        # ATP Section
        st.markdown('<div id="atp-section"></div>', unsafe_allow_html=True)
        st.markdown("## 🎾 ATP")
        if not atp_bets.empty:
            display_bet_cards(atp_bets)
        else:
            st.markdown(
                """
                <div style='
                    background: rgba(100,100,100,0.1);
                    border: 1px solid rgba(150,150,150,0.2);
                    border-radius: 12px;
                    padding: 40px;
                    text-align: center;
                    color: #6b7280;
                    font-size: 16px;
                    font-style: italic;
                    margin: 20px 0;
                '>
                    Pas de paris pour cette compétition
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.divider()

        # WTA Section
        st.markdown('<div id="wta-section"></div>', unsafe_allow_html=True)
        st.markdown("## 👩‍🦰 WTA")
        if not wta_bets.empty:
            display_bet_cards(wta_bets)
        else:
            st.markdown(
                """
                <div style='
                    background: rgba(100,100,100,0.1);
                    border: 1px solid rgba(150,150,150,0.2);
                    border-radius: 12px;
                    padding: 40px;
                    text-align: center;
                    color: #6b7280;
                    font-size: 16px;
                    font-style: italic;
                    margin: 20px 0;
                '>
                    Pas de paris pour cette compétition
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.divider()

        # Doubles Section
        st.markdown('<div id="doubles-section"></div>', unsafe_allow_html=True)
        st.markdown("## 🤝 Doubles")
        if not doubles_bets.empty:
            display_bet_cards(doubles_bets)
        else:
            st.markdown(
                """
                <div style='
                    background: rgba(100,100,100,0.1);
                    border: 1px solid rgba(150,150,150,0.2);
                    border-radius: 12px;
                    padding: 40px;
                    text-align: center;
                    color: #6b7280;
                    font-size: 16px;
                    font-style: italic;
                    margin: 20px 0;
                '>
                    Pas de paris pour cette compétition
                </div>
                """,
                unsafe_allow_html=True,
            )

    else:
        st.info("Aucun pari en cours.")
else:
    st.warning("Veuillez vous connecter pour voir vos paris en cours.")
