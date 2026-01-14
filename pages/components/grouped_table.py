import streamlit as st
import pandas as pd


def render_grouped_table(bets_data: pd.DataFrame) -> None:
    """Render the grouping controls, tables and charts below the metrics.

    This function encapsulates the long grouping/table/chart logic from the
    original dashboard file.
    """
    group_by = st.radio(
        "Grouper par :",
        options=["Compétition", "Surface", "Cote", "Mois", "Jour", "Match"],
        horizontal=True,
        label_visibility="collapsed",
    )

    col_map = {
        "Match": "Match",
        "Jour": "Date",
        "Compétition": "Compétition",
        "Surface": "Surface",
        "Cote": "Cote_bin",
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
            formatters["Mise"] = lambda x: f"{x:,.2f}".replace(",", " ") + "€"
        if "Gains net" in display_match.columns:
            formatters["Gains net"] = lambda x: f"{x:+,.2f}".replace(",", " ") + "€"
        if "Gains attendus" in display_match.columns:
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

        styler = display_match.style.format(formatters)
        if "Gains net" in display_match.columns:
            styler = styler.map(gains_cell_color, subset=["Gains net"])
        if "Gains attendus" in display_match.columns:
            styler = styler.map(marge_cell_color, subset=["Gains attendus"])
        if "Mise" in display_match.columns:
            styler = styler.map(mise_cell_color, subset=["Mise"])
        if "ROI attendu" in display_match.columns:
            styler = styler.map(gains_cell_color, subset=["ROI attendu"])
        # styler.index = display_match["_index"]
        st.dataframe(
            styler,
            width="stretch",
            hide_index=True,
            selection_mode="single-row",
        )

    else:
        df_display = bets_data.copy()
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
                    lambda r: f"{month_names_fr.get(int(r['MonthNum']), '')} {int(r['Year'])}",
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
                    lambda x: (x.sum() / df_display.loc[x.index, "Mise"].sum() * 100)
                    if df_display.loc[x.index, "Mise"].sum() > 0
                    else 0,
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

        display_df = grouped[
            [
                group_col,
                "Count",
                "Avg_Cote",
                "ROI_attendu",
                "Total_Mises",
                "Resultat_attendu",
                "Total_Gains",
                "Roi",
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

        styled = (
            display_df.style.format(
                {
                    "Cote moyenne": lambda x: f"{x:.2f}",
                    "ROI attendu": lambda x: f"{x:+.1f}%",
                    "Mises": lambda x: f"{x:,.0f}".replace(",", " ") + "€",
                    "Gains": lambda x: f"{x:+,.0f}".replace(",", " ") + "€",
                    "ROI": lambda x: f"{x:+.1f}%",
                    "Resultat.attendu": lambda x: f"{x:+,.0f}".replace(",", " ") + "€",
                }
            )
            .map(gain_color, subset=["Gains", "ROI"])
            .map(gain_color, subset=["ROI attendu"])
            .map(mises_color, subset=["Mises"])
            .map(result_att_color, subset=["Resultat.attendu"])
        )
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
                                    lambda r: f"{int(r[count_field])}p\n{r[y_col_mises]:.0f}€",
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
