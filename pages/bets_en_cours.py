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

                # Create card HTML
                card_html = f"""
                <div style='
                    background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                    border-radius: 16px;
                    padding: 20px;
                    border: 1px solid rgba(50,178,150,0.2);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    backdrop-filter: blur(6px);
                    font-family: Segoe UI, sans-serif;
                    color: #e0e0e0;
                    margin-bottom: 20px;
                    transition: transform 0.2s;
                '>
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
                            <span style='color: #9ca3af; font-size: 14px;'>🏆 Compétition</span>
                            <span style='font-size: 13px;'>{bet["Compétition"]}</span>
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
                            <span style='color: {"#32b296" if bet["Marge attendue"] > 0 else "#e04e4e"}; font-weight: 600;'>{bet["Marge attendue"]:+.2f}€</span>
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
                </div>
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

        # Display summary statistics with cards
        st.markdown("### 📊 Vue d'ensemble")

        # Global metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f"""
            <div style='background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 12px; padding: 16px; border: 1px solid rgba(50,178,150,0.2);'>
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
            <div style='background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 12px; padding: 16px; border: 1px solid rgba(251,191,36,0.2);'>
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
            <div style='background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 12px; padding: 16px; border: 1px solid rgba(50,178,150,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>💸 Gains potentiels</div>
                <div style='font-size: 32px; font-weight: 700; color: {gain_color};'>{total_gains_potentiels:+.2f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>si tout gagne</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col4:
            marge_color = "#32b296" if total_marges > 0 else "#e04e4e"
            st.markdown(
                f"""
            <div style='background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 12px; padding: 16px; border: 1px solid rgba(147,51,234,0.2);'>
                <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px;'>📈 Marges attendues</div>
                <div style='font-size: 32px; font-weight: 700; color: {marge_color};'>{total_marges:+.2f}€</div>
                <div style='color: #9ca3af; font-size: 12px; margin-top: 8px;'>espérées</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        st.divider()

        # Competition-specific metrics
        st.markdown("### 🏆 Par compétition")
        col1, col2, col3 = st.columns(3)

        with col1:
            atp_mises = atp_bets["Mise"].sum() if not atp_bets.empty else 0
            atp_gains = atp_bets["Gain potentiel"].sum() if not atp_bets.empty else 0
            atp_marges = atp_bets["Marge attendue"].sum() if not atp_bets.empty else 0
            st.markdown(
                f"""
            <div style='background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 12px; padding: 16px; border: 1px solid rgba(59,130,246,0.2);'>
                <div style='text-align: center; font-size: 18px; font-weight: 600; color: #3b82f6; margin-bottom: 12px;'>🎾 ATP</div>
                <div style='margin: 8px 0;'>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                        <span style='font-weight: 600;'>{len(atp_bets)}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                        <span style='font-weight: 600; color: #fbbf24;'>{atp_mises:.2f}€</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                        <span style='font-weight: 600; color: #32b296;'>{atp_gains:+.2f}€</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                        <span style='font-weight: 600; color: {"#32b296" if atp_marges > 0 else "#e04e4e"};'>{atp_marges:+.2f}€</span>
                    </div>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col2:
            wta_mises = wta_bets["Mise"].sum() if not wta_bets.empty else 0
            wta_gains = wta_bets["Gain potentiel"].sum() if not wta_bets.empty else 0
            wta_marges = wta_bets["Marge attendue"].sum() if not wta_bets.empty else 0
            st.markdown(
                f"""
            <div style='background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 12px; padding: 16px; border: 1px solid rgba(236,72,153,0.2);'>
                <div style='text-align: center; font-size: 18px; font-weight: 600; color: #ec4899; margin-bottom: 12px;'>👩‍🦰 WTA</div>
                <div style='margin: 8px 0;'>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                        <span style='font-weight: 600;'>{len(wta_bets)}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                        <span style='font-weight: 600; color: #fbbf24;'>{wta_mises:.2f}€</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                        <span style='font-weight: 600; color: #32b296;'>{wta_gains:+.2f}€</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                        <span style='font-weight: 600; color: {"#32b296" if wta_marges > 0 else "#e04e4e"};'>{wta_marges:+.2f}€</span>
                    </div>
                </div>
            </div>
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
            st.markdown(
                f"""
            <div style='background: linear-gradient(145deg, rgba(25,28,35,0.95), rgba(35,38,45,0.95));
                        border-radius: 12px; padding: 16px; border: 1px solid rgba(168,85,247,0.2);'>
                <div style='text-align: center; font-size: 18px; font-weight: 600; color: #a855f7; margin-bottom: 12px;'>🤝 Doubles</div>
                <div style='margin: 8px 0;'>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Paris:</span>
                        <span style='font-weight: 600;'>{len(doubles_bets)}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Mises:</span>
                        <span style='font-weight: 600; color: #fbbf24;'>{doubles_mises:.2f}€</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Gains pot.:</span>
                        <span style='font-weight: 600; color: #32b296;'>{doubles_gains:+.2f}€</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #9ca3af; font-size: 13px;'>Marges:</span>
                        <span style='font-weight: 600; color: {"#32b296" if doubles_marges > 0 else "#e04e4e"};'>{doubles_marges:+.2f}€</span>
                    </div>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        st.divider()

        # ATP Section
        if not atp_bets.empty:
            st.markdown("## 🎾 ATP")
            display_bet_cards(atp_bets)
            st.divider()

        # WTA Section
        if not wta_bets.empty:
            st.markdown("## 👩‍🦰 WTA")
            display_bet_cards(wta_bets)
            st.divider()

        # Doubles Section
        if not doubles_bets.empty:
            st.markdown("## 🤝 Doubles")
            display_bet_cards(doubles_bets)

    else:
        st.info("Aucun pari en cours.")
else:
    st.warning("Veuillez vous connecter pour voir vos paris en cours.")
