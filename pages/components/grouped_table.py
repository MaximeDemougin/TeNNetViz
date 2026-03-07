import streamlit as st
import pandas as pd
from pages.components.charts import (
    render_cote_distribution_bar,
    render_marge_distribution_bar,
    render_surface_distribution_bar,
    render_competition_distribution_bar,
    render_cote_histogram,
    render_marge_histogram,
    render_cote_raw_histogram,
    render_marge_raw_histogram,
    sort_competitions,
)


def render_grouped_table(bets_data: pd.DataFrame, unit_mode: bool = False) -> None:
    """Render the grouping controls, tables and charts below the metrics.

    This function encapsulates the long grouping/table/chart logic from the
    original dashboard file.
    unit_mode: if True, display monetary values as units (÷ mise) instead of €.
    """
    # Check if bets_data is empty
    if bets_data.empty:
        st.info("Aucune donnée à afficher")
        return

    group_by = st.radio(
        "Grouper par :",
        options=[
            "Compétition",
            "Type de tournoi",
            "Surface",
            "Cote",
            "Marge",
            "Mois",
            "Jour",
            "Match",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    col_map = {
        "Match": "Match",
        "Jour": "Date",
        "Compétition": "Compétition",
        "Type de tournoi": "Type de tournoi",
        "Surface": "Surface",
        "Cote": "Cote_bin",
        "Marge": "Marge_bin",
        "Mois": "Mois",
    }
    group_col = col_map.get(group_by, "Match")

    if group_by == "Match":
        match_df = bets_data.copy()
        try:
            match_df["Date"] = pd.to_datetime(match_df["Date"])
        except Exception:
            pass
        match_df = match_df.sort_values(by="Date", ascending=False)

        match_cols = [
            "Match",
            "Date",
            "Compétition",
            "Level",
            "Surface",
            "Round",
            "player_bet",
            "Score",
            "Cote",
            "Prédiction",
            "Mise",
            "Gains net",
            "Marge attendue",
        ]
        match_cols = [c for c in match_cols if c in match_df.columns]

        display_match = match_df[match_cols].copy()
        if "Date" in display_match.columns:
            try:
                display_match["Date"] = (
                    display_match["Horaire"].astype(str)
                    + " "
                    + display_match["Date"].dt.strftime("%Y-%m-%d")
                )
            except Exception:
                pass

        # Compute ROI attendu (Cote / Prédiction) and insert it after 'Prédiction'
        def _compute_roi_att(row):
            try:
                cote = float(row.get("Cote", 0) or 0)
                pred = float(row.get("Prédiction", 0) or 0)
                return (cote / pred * 100) - 100 if pred != 0 else 0.0
            except Exception:
                return 0.0

        if "Cote" in display_match.columns and "Prédiction" in display_match.columns:
            display_match["ROI attendu"] = display_match.apply(_compute_roi_att, axis=1)

        # Rename the data column for display only: "Marge attendue" -> "Gains attendus"
        if "Marge attendue" in display_match.columns:
            display_match = display_match.rename(
                columns={"Marge attendue": "Gains attendus"}
            )

        formatters = {}
        if "Mise" in display_match.columns:
            if unit_mode:
                formatters["Mise"] = lambda x: "1 u"
            else:
                formatters["Mise"] = lambda x: f"{x:,.2f}".replace(",", " ") + "€"
        if "Gains net" in display_match.columns:
            if unit_mode:
                # gains in units = gains / mise; we need access to the row, so compute a new col
                try:
                    display_match["Gains net"] = (
                        display_match["Gains net"] / display_match["Mise"].replace(0, float("nan"))
                    )
                except Exception:
                    pass
                formatters["Gains net"] = lambda x: f"{x:+.3f} u"
            else:
                formatters["Gains net"] = lambda x: f"{x:+,.2f}".replace(",", " ") + "€"
        if "Gains attendus" in display_match.columns:
            if unit_mode:
                try:
                    # Marge attendue / Mise for unit display
                    display_match["Gains attendus"] = (
                        display_match["Gains attendus"] / display_match["Mise"].replace(0, float("nan"))
                    )
                except Exception:
                    pass
                formatters["Gains attendus"] = lambda x: f"{x:+.3f} u"
            else:
                formatters["Gains attendus"] = lambda x: f"{x:,.2f}".replace(",", " ") + "€"
        if "ROI attendu" in display_match.columns:
            formatters["ROI attendu"] = lambda x: f"{x:+.1f}%"
        if "Cote" in display_match.columns:
            formatters["Cote"] = lambda x: f"{x:.3f}"
        if "Prédiction" in display_match.columns:
            formatters["Prédiction"] = lambda x: f"{x:.3f}"

        def gains_cell_color(v):
            try:
                return (
                    "color: #32b296; font-weight: 700;"
                    if float(v) > 0
                    else "color: #e04e4e; font-weight: 700;"
                )
            except Exception:
                return ""

        # Color for Marge attendue (displayed as Gains attendus) in match view (blue if positive, red if negative)
        def marge_cell_color(v):
            try:
                return (
                    "color: #3b82f6; font-weight: 700;"
                    if float(v) > 0
                    else "color: #e04e4e; font-weight: 700;"
                )
            except Exception:
                return ""

        # Color for Mise in match view (yellow like metric card)
        def mise_cell_color(v):
            try:
                # keep bold and yellow regardless of value
                return "color: #fbbf24; font-weight: 700;"
            except Exception:
                return ""

        # Color for competition names to match the chart colors
        def competition_cell_color(v):
            val_lower = str(v).lower()
            color_map = {
                "atp": "#10b981",  # Vert émeraude pour ATP
                "wta": "#ec4899",  # Rose pour WTA
                "doubles": "#8b5cf6",  # Violet pour Doubles
                "challenger": "#6366f1",  # Bleu indigo pour Challenger
            }
            color = color_map.get(val_lower, "#d1d4dc")  # Couleur par défaut
            return f"color: {color}; font-weight: 600;"

        # Color for surface names to match the chart colors
        def surface_cell_color(v):
            color_map = {
                "Dur": "#3772d1",
                "Terre battue": "#b45715",
                "Gazon": "#22c55e",
                "Carpet": "#8b5cf6",
                "Indoor Hard": "#6366f1",
            }
            color = color_map.get(v, "#d1d4dc")  # Couleur par défaut
            return f"color: {color}; font-weight: 600;"

        styler = display_match.style.format(formatters)
        if "Gains net" in display_match.columns:
            styler = styler.map(gains_cell_color, subset=["Gains net"])
        if "Gains attendus" in display_match.columns:
            styler = styler.map(marge_cell_color, subset=["Gains attendus"])
        if "Mise" in display_match.columns:
            styler = styler.map(mise_cell_color, subset=["Mise"])
        if "ROI attendu" in display_match.columns:
            styler = styler.map(gains_cell_color, subset=["ROI attendu"])
        if "Compétition" in display_match.columns:
            styler = styler.map(competition_cell_color, subset=["Compétition"])
        if "Surface" in display_match.columns:
            styler = styler.map(surface_cell_color, subset=["Surface"])
        # styler.index = display_match["_index"]
        st.dataframe(
            styler,
            width="stretch",
            hide_index=True,
            selection_mode="single-row",
        )

    else:
        df_display = bets_data.copy()

        # If the group column doesn't exist in the data, fall back to "Compétition"
        if group_col not in df_display.columns:
            st.warning(
                f"La colonne '{group_by}' n'est pas disponible dans les données. Rechargez la page pour mettre à jour le cache."
            )
            return

        df_display["Date"] = pd.to_datetime(df_display["Date"], errors="coerce")

        if group_by == "Mois":
            # create month name (French) and a sortable key (YYYYMM)
            df_display["Year"] = df_display["Date"].dt.year
            df_display["MonthNum"] = df_display["Date"].dt.month
            month_names_fr = {
                1: "Janvier",
                2: "Février",
                3: "Mars",
                4: "Avril",
                5: "Mai",
                6: "Juin",
                7: "Juillet",
                8: "Août",
                9: "Septembre",
                10: "Octobre",
                11: "Novembre",
                12: "Décembre",
            }
            multiple_years = df_display["Year"].nunique() > 1
            if multiple_years:
                df_display["Mois"] = df_display.apply(
                    lambda r: (
                        f"{month_names_fr.get(int(r['MonthNum']), '')} {int(r['Year'])}"
                    ),
                    axis=1,
                )
            else:
                df_display["Mois"] = df_display["MonthNum"].map(
                    lambda m: month_names_fr.get(int(m), "")
                )
            # sortable key for chronological sorting
            df_display["Mois_key"] = df_display["Date"].dt.strftime("%Y%m").astype(int)

        if group_by == "Cote":
            bins = [0, 1.5, 2.0, 2.5, 3.0, 5, 100]
            labels = ["<1.5", "1.5-2.0", "2.0-2.5", "2.5-3.0", "3.0-5.0", ">=5.0"]
            try:
                cote_vals = df_display["Cote"].astype(float)
            except Exception:
                cote_vals = pd.to_numeric(df_display["Cote"], errors="coerce")

            df_display["Cote_bin"] = pd.cut(
                cote_vals, bins=bins, labels=labels, include_lowest=True
            )
            df_display["Cote_bin"] = (
                df_display["Cote_bin"].astype(str).replace("nan", "Unknown")
            )

        if group_by == "Marge":
            # Compute ROI attendu per bet to bin by expected margin
            try:
                cote_vals = df_display["Cote"].astype(float)
                pred_vals = df_display["Prédiction"].astype(float)
                roi_att = (cote_vals / pred_vals - 1) * 100
            except Exception:
                roi_att = pd.Series([0.0] * len(df_display))
            marge_bins = [-100, 0, 2, 5, 10, 20, 100]
            marge_labels = ["<0%", "0-2%", "2-5%", "5-10%", "10-20%", ">=20%"]
            df_display["Marge_bin"] = pd.cut(
                roi_att, bins=marge_bins, labels=marge_labels, include_lowest=True
            )
            df_display["Marge_bin"] = (
                df_display["Marge_bin"].astype(str).replace("nan", "Unknown")
            )

        df_display["Date"] = df_display["Date"].dt.strftime("%Y-%m-%d")

        # Build aggregation dict, include Mois_key if present to help sorting
        agg_dict = {
            "Mise": "sum",
            "Gains net": "sum",
            "Marge attendue": "sum",
            "Cote": lambda x: x.mean(),
            "Prédiction": "mean",
        }
        # For consistent named aggregations used later
        if "Mois_key" in df_display.columns:
            agg_extra = {"Mois_key": ("Mois_key", "min")}
        else:
            agg_extra = {}

        grouped = (
            df_display.groupby(group_col)
            .agg(
                Total_Mises=("Mise", "sum"),
                Total_Gains=("Gains net", "sum"),
                Roi=(
                    "Gains net",
                    lambda x: (
                        (x.sum() / df_display.loc[x.index, "Mise"].sum() * 100)
                        if df_display.loc[x.index, "Mise"].sum() > 0
                        else 0
                    ),
                ),
                Resultat_attendu=("Marge attendue", "sum"),
                Avg_Cote=("Cote", "mean"),
                Avg_Pred=("Prédiction", "mean"),
                Wins=("Gains net", lambda x: (x > 0).sum()),
                Count=("Mise", "count"),
                **agg_extra,
            )
            .reset_index()
        )

        # compute expected ROI per group (Cote / Prediction - 1) * 100
        try:
            grouped["ROI_attendu"] = (
                grouped["Avg_Cote"] / grouped["Avg_Pred"] - 1
            ) * 100
        except Exception:
            grouped["ROI_attendu"] = 0.0

        # If we aggregated a Mois_key, sort by it (chronological) and then drop it from display
        if "Mois_key" in grouped.columns:
            grouped = grouped.sort_values(by="Mois_key", ascending=False)
        else:
            grouped = grouped.sort_values("Total_Gains", ascending=False)

        grouped["Winrate"] = grouped["Wins"] / grouped["Count"] * 100

        if group_by == "Cote":
            order_desc = [">=5.0", "3.0-5.0", "2.5-3.0", "2.0-2.5", "1.5-2.0", "<1.5"]
            try:
                grouped[group_col] = pd.Categorical(
                    grouped[group_col], categories=order_desc, ordered=True
                )
                grouped = grouped.sort_values(by=group_col, ascending=True)
            except Exception:
                grouped = grouped.set_index(group_col).reindex(order_desc).reset_index()

        if group_by == "Marge":
            order_marge = ["<0%", "0-2%", "2-5%", "5-10%", "10-20%", ">=20%"]
            try:
                grouped[group_col] = pd.Categorical(
                    grouped[group_col], categories=order_marge, ordered=True
                )
                grouped = grouped.sort_values(by=group_col, ascending=False)
            except Exception:
                grouped = (
                    grouped.set_index(group_col)
                    .reindex(order_marge[::-1])
                    .reset_index()
                )

        if group_by == "Compétition":
            # Sort competitions in standard order: ATP, WTA, Doubles
            sorted_comps = sort_competitions(grouped[group_col].unique().tolist())
            try:
                grouped[group_col] = pd.Categorical(
                    grouped[group_col], categories=sorted_comps, ordered=True
                )
                grouped = grouped.sort_values(by=group_col)
            except Exception:
                grouped = (
                    grouped.set_index(group_col).reindex(sorted_comps).reset_index()
                )

        if group_by == "Type de tournoi":
            # Sort alphabetically
            grouped = grouped.sort_values(by=group_col)

        display_df = grouped[
            [
                group_col,
                "Count",
                "Avg_Cote",
                "Total_Mises",
                "Total_Gains",
                "Roi",
                "Resultat_attendu",
                "ROI_attendu",
            ]
        ].copy()

        # Rename and reorder for display
        display_df = display_df.rename(
            columns={
                group_col: group_by,
                "Count": "Nb Paris",
                "Avg_Cote": "Cote moyenne",
                "Total_Mises": "Mises",
                "Total_Gains": "Gains",
                "Roi": "ROI",
                "Resultat_attendu": "Resultat.attendu",
                "ROI_attendu": "ROI attendu",
            }
        )

        # Ensure numeric types
        display_df["Mises"] = display_df["Mises"].astype(float)
        display_df["Gains"] = display_df["Gains"].astype(float)
        display_df["ROI"] = display_df["ROI"].astype(float)
        display_df["Resultat.attendu"] = display_df["Resultat.attendu"].astype(float)
        display_df["Cote moyenne"] = display_df["Cote moyenne"].astype(float)
        display_df["ROI attendu"] = display_df["ROI attendu"].astype(float)

        # Sort by group if needed
        if group_by == "Jour":
            display_df = display_df.sort_values(by=group_by, ascending=False)

        def gain_color(val):
            color = "#32b296" if val > 0 else "#e04e4e"
            return f"color: {color}; font-weight: 700;"

        # Color for Mises to match the yellow metric card
        def mises_color(val):
            return "color: #fbbf24; font-weight: 700;"

        # Color for Resultat.attendu to match the blue/red metric card
        def result_att_color(val):
            try:
                v = float(val)
                color = "#3b82f6" if v > 0 else "#e04e4e"
            except Exception:
                color = "#3b82f6"
            return f"color: {color}; font-weight: 700;"

        # Color for competition names to match the chart colors
        def competition_color(val):
            val_lower = str(val).lower()
            color_map = {
                "atp": "#10b981",  # Vert émeraude pour ATP
                "wta": "#ec4899",  # Rose pour WTA
                "doubles": "#8b5cf6",  # Violet pour Doubles
                "challenger": "#6366f1",  # Bleu indigo pour Challenger
            }
            color = color_map.get(val_lower, "#d1d4dc")  # Couleur par défaut
            return f"color: {color}; font-weight: 700;"

        # Color for surface names to match the chart colors
        def surface_color(val):
            color_map = {
                "Dur": "#3772d1",
                "Terre battue": "#b45715",
                "Gazon": "#22c55e",
                "Carpet": "#8b5cf6",
                "Indoor Hard": "#6366f1",
            }
            color = color_map.get(val, "#d1d4dc")  # Couleur par défaut
            return f"color: {color}; font-weight: 700;"

        # Color for cote bins to match the chart colors
        def cote_bin_color(val):
            color_map = {
                "<1.5": "#10b981",
                "1.5-2.0": "#3b82f6",
                "2.0-2.5": "#6366f1",
                "2.5-3.0": "#8b5cf6",
                "3.0-5.0": "#ec4899",
                ">=5.0": "#ef4444",
            }
            color = color_map.get(val, "#d1d4dc")  # Couleur par défaut
            return f"color: {color}; font-weight: 700;"

        # Color for marge bins to match the chart colors
        def marge_bin_color(val):
            color_map = {
                "<0%": "#10b981",
                "0-2%": "#3b82f6",
                "2-5%": "#6366f1",
                "5-10%": "#8b5cf6",
                "10-20%": "#ec4899",
                ">=20%": "#ef4444",
            }
            color = color_map.get(val, "#d1d4dc")  # Couleur par défaut
            return f"color: {color}; font-weight: 700;"

        # In unit mode, convert Mises and Gains columns to units (÷ mise per bet)
        if unit_mode:
            try:
                # Total_Mises in units = count (1 unit per bet)
                display_df["Mises"] = grouped["Count"].astype(float)
                # Total_Gains in units = sum(net_gain / mise) per group
                unit_gains = (
                    df_display.groupby(group_col)
                    .apply(
                        lambda g: (
                            g["Gains net"] / g["Mise"].replace(0, float("nan"))
                        ).sum(),
                        include_groups=False,
                    )
                    .reset_index(name="_unit_gains")
                )
                display_df = display_df.merge(unit_gains, left_on=group_by, right_on=group_col, how="left")
                display_df["Gains"] = display_df["_unit_gains"]
                display_df = display_df.drop(columns=[c for c in ["_unit_gains", group_col + "_y"] if c in display_df.columns])
                # Resultat.attendu in units
                unit_marges = (
                    df_display.groupby(group_col)
                    .apply(
                        lambda g: (
                            g["Marge attendue"] / g["Mise"].replace(0, float("nan"))
                        ).sum(),
                        include_groups=False,
                    )
                    .reset_index(name="_unit_marges")
                )
                display_df = display_df.merge(unit_marges, left_on=group_by, right_on=group_col, how="left")
                display_df["Resultat.attendu"] = display_df["_unit_marges"]
                display_df = display_df.drop(columns=[c for c in ["_unit_marges", group_col + "_y"] if c in display_df.columns])
            except Exception:
                pass

        styled = (
            display_df.style.format(
                {
                    "Cote moyenne": lambda x: f"{x:.2f}",
                    "ROI attendu": lambda x: f"{x:+.1f}%",
                    "Mises": (lambda x: f"{x:,.0f} u".replace(",", " ")) if unit_mode else (lambda x: f"{x:,.0f}".replace(",", " ") + "€"),
                    "Gains": (lambda x: f"{x:+.2f} u") if unit_mode else (lambda x: f"{x:+,.0f}".replace(",", " ") + "€"),
                    "ROI": lambda x: f"{x:+.1f}%",
                    "Resultat.attendu": (lambda x: f"{x:+.2f} u") if unit_mode else (lambda x: f"{x:+,.0f}".replace(",", " ") + "€"),
                }
            )
            .map(gain_color, subset=["Gains", "ROI"])
            .map(gain_color, subset=["ROI attendu"])
            .map(mises_color, subset=["Mises"])
            .map(result_att_color, subset=["Resultat.attendu"])
        )

        # Apply grouping-specific colors for the group column
        if "Compétition" in display_df.columns:
            styled = styled.map(competition_color, subset=["Compétition"])

        if "Surface" in display_df.columns:
            styled = styled.map(surface_color, subset=["Surface"])

        if "Cote" in display_df.columns:
            styled = styled.map(cote_bin_color, subset=["Cote"])

        if "Marge" in display_df.columns:
            styled = styled.map(marge_bin_color, subset=["Marge"])

        st.dataframe(
            styled, width="stretch", hide_index=True, selection_mode="single-row"
        )

        try:
            chart_df = grouped.copy() if "grouped" in locals() else None
            if chart_df is None or len(chart_df) == 0:
                chart_df = display_df.copy() if "display_df" in locals() else None

            if chart_df is not None and len(chart_df) > 0:
                if group_col not in chart_df.columns:
                    chart_df[group_col] = chart_df.index.astype(str)
                chart_df[group_col] = chart_df[group_col].fillna("Unknown")

                if group_by == "Jour" and chart_df[group_col].nunique() > 1:
                    st.markdown("### Visualisations (par jour)", unsafe_allow_html=True)
                    c1, c2, c3 = st.columns([4, 1, 4])
                    y_col_gains = (
                        "Total_Gains"
                        if "Total_Gains" in chart_df.columns
                        else ("Gains" if "Gains" in chart_df.columns else None)
                    )
                    y_col_mises = (
                        "Total_Mises"
                        if "Total_Mises" in chart_df.columns
                        else ("Mises" if "Mises" in chart_df.columns else None)
                    )

                    if y_col_gains is not None:
                        with c3:
                            chart_df["_gains_sign"] = chart_df[y_col_gains].apply(
                                lambda v: "Positive" if v > 0 else "Negative"
                            )
                            import plotly.express as px

                            fig_gains = px.bar(
                                chart_df,
                                x=group_col,
                                y=y_col_gains,
                                color="_gains_sign",
                                color_discrete_map={
                                    "Positive": "#32b296",
                                    "Negative": "#e04e4e",
                                },
                                labels={group_col: group_by, y_col_gains: "Gains (€)"},
                            )
                            try:
                                fig_gains.update_traces(
                                    marker_line_width=0,
                                    text=chart_df[y_col_gains].map(
                                        lambda v: f"{v:+.0f}€"
                                    ),
                                    textposition="outside",
                                )
                            except Exception:
                                pass
                            fig_gains.update_layout(
                                plot_bgcolor="rgba(0,0,0,0)",
                                paper_bgcolor="rgba(0,0,0,0)",
                                font=dict(color="#d1d4dc"),
                                margin=dict(t=30, b=80),
                            )
                            fig_gains.update_yaxes(tickformat=",")
                            st.plotly_chart(fig_gains, width="stretch")

                    if y_col_mises is not None:
                        with c1:
                            import plotly.express as px

                            fig_mises = px.bar(
                                chart_df,
                                x=group_col,
                                y=y_col_mises,
                                labels={group_col: group_by, y_col_mises: "Mises (€)"},
                            )
                            fig_mises.update_traces(marker_color="#636363")

                            count_field = (
                                "Count"
                                if "Count" in chart_df.columns
                                else (
                                    "Nb Paris"
                                    if "Nb Paris" in chart_df.columns
                                    else None
                                )
                            )
                            if count_field is not None:
                                text_series = chart_df.apply(
                                    lambda r: (
                                        f"{int(r[count_field])}p\n{r[y_col_mises]:.0f}€"
                                    ),
                                    axis=1,
                                )
                            else:
                                text_series = chart_df[y_col_mises].map(
                                    lambda v: f"{v:.0f}€"
                                )

                            fig_mises.update_traces(
                                text=text_series,
                                textposition="inside",
                                textfont=dict(color="#ffffff", size=12),
                                marker_line_width=0,
                            )
                            fig_mises.update_layout(
                                plot_bgcolor="rgba(0,0,0,0)",
                                paper_bgcolor="rgba(0,0,0,0)",
                                font=dict(color="#d1d4dc"),
                                margin=dict(t=30, b=80),
                            )
                            fig_mises.update_yaxes(tickformat=",")
                            st.plotly_chart(fig_mises, width="stretch")
        except Exception:
            pass

    # Add colored distribution bar for bets by odds only when "Cote" grouping is selected
    if group_by == "Cote":
        # Add toggle button for visualization type
        viz_type_cote = st.radio(
            "Type de visualisation :",
            options=[
                "Barre de progression",
                "Bar chart (bins)",
                "Histogramme (continu)",
            ],
            horizontal=True,
            key="viz_type_cote",
        )

        if viz_type_cote == "Barre de progression":
            render_cote_distribution_bar(bets_data)
        elif viz_type_cote == "Bar chart (bins)":
            render_cote_histogram(bets_data)
        else:
            # Add slider for number of bins
            nbins_cote = st.slider(
                "Nombre de bins :",
                min_value=10,
                max_value=100,
                value=50,
                step=5,
                key="nbins_cote",
            )
            render_cote_raw_histogram(bets_data, nbins=nbins_cote)

    # Add colored distribution bar for bets by expected margin only when "Marge" grouping is selected
    if group_by == "Marge":
        # Add toggle button for visualization type
        viz_type_marge = st.radio(
            "Type de visualisation :",
            options=[
                "Barre de progression",
                "Bar chart (bins)",
                "Histogramme (continu)",
            ],
            horizontal=True,
            key="viz_type_marge",
        )

        if viz_type_marge == "Barre de progression":
            render_marge_distribution_bar(bets_data)
        elif viz_type_marge == "Bar chart (bins)":
            render_marge_histogram(bets_data)
        else:
            # Add slider for number of bins
            nbins_marge = st.slider(
                "Nombre de bins :",
                min_value=10,
                max_value=100,
                value=50,
                step=5,
                key="nbins_marge",
            )
            render_marge_raw_histogram(bets_data, nbins=nbins_marge)

    # Add colored distribution bar for bets by surface only when "Surface" grouping is selected
    if group_by == "Surface":
        render_surface_distribution_bar(bets_data)

    # Add colored distribution bar for bets by competition only when "Compétition" grouping is selected
    if group_by == "Compétition":
        render_competition_distribution_bar(bets_data)
