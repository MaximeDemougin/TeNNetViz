import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils import fmt_num, fmt_eur, fmt_money
from config import DATA_CACHE_TTL


def sort_competitions(series_or_list):
    """Sort competitions in the standard order: ATP, WTA, Doubles, then others alphabetically.

    Args:
        series_or_list: pandas Series or list of competition names

    Returns:
        Sorted list or Series
    """
    # Define the standard order
    standard_order = ["atp", "wta", "doubles"]

    if isinstance(series_or_list, pd.Series):
        # For pandas Series
        values = series_or_list.unique().tolist()
    else:
        # For lists
        values = list(series_or_list)

    # Normalize for comparison (lowercase)
    values_lower = [str(v).lower() for v in values]

    # Sort: first by standard order, then alphabetically for others
    def sort_key(val):
        val_lower = str(val).lower()
        if val_lower in standard_order:
            return (0, standard_order.index(val_lower))
        else:
            return (1, val_lower)

    sorted_values = sorted(values, key=sort_key)

    if isinstance(series_or_list, pd.Series):
        return pd.Series(sorted_values)
    return sorted_values


def render_cumulative_chart(
    bets_data: pd.DataFrame,
    mode: str = "match",
    unit_mode: bool = False,
    show_drawdown: bool = False,
    show_peaks: bool = True,
) -> list:
    """Render cumulative gains line chart and return the selected points list (may be empty).

    mode: one of 'match' (per-match index), 'horaire' (use Date/time as x-axis),
    or 'jour' (aggregate per day). The function will attempt to map selections
    back to the table where possible. In 'jour' mode chart selections are mapped
    to a date value in session_state["selected_from_chart"].
    unit_mode: if True, plot cumulative units (net_gain / mise) instead of €.
    """

    # Check if bets_data is empty
    if bets_data.empty:
        st.info("Aucune donnée à afficher")
        return []

    # Normalize mode
    mode = (mode or "").lower()

    # Default plotting dataframe (per-point)
    plot_df = None
    x_col = "Match_Num"

    if mode == "jour":
        # Aggregate per day
        if "Date" not in bets_data.columns:
            # fallback to match mode if no Date
            mode = "match"
        else:
            try:
                df = bets_data.copy()
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                df = df.dropna(subset=["Date"])  # drop rows without valid date
                if df.empty:
                    mode = "match"
                else:
                    df["Date_only"] = df["Date"].dt.normalize()
                    grouped = (
                        df.groupby("Date_only", sort=True)
                        .agg({"Gains net": "sum", "Marge attendue": "sum"})
                        .reset_index()
                    )
                    grouped["Cumulative Gains"] = grouped["Gains net"].cumsum()
                    grouped["Cumulative_Marge"] = grouped["Marge attendue"].cumsum()
                    plot_df = grouped.rename(columns={"Date_only": "Date"})
                    x_col = "Date"
            except Exception:
                mode = "match"

    if mode in ("match", "horaire"):
        # reset_index to capture the original index as a column; keep that mapping
        bets_data_reset = bets_data.reset_index()
        # If `_orig_index` not provided, use the first column (previous index)
        if "_orig_index" not in bets_data_reset.columns:
            bets_data_reset["_orig_index"] = bets_data_reset.iloc[:, 0]

        # sequential match number for plotting when not using Date
        bets_data_reset["Match_Num"] = range(len(bets_data_reset))

        # Ensure the cumulative margin column exists (safe get)
        bets_data_reset["Cumulative_Marge"] = bets_data_reset.get(
            "Marge attendue", pd.Series([0] * len(bets_data_reset))
        ).cumsum()

        if mode == "horaire" and "Date" in bets_data_reset.columns:
            try:
                bets_data_reset["Date"] = pd.to_datetime(
                    bets_data_reset["Date"], errors="coerce"
                )
                bets_data_reset = bets_data_reset.sort_values(
                    by="Date", ascending=True
                ).reset_index(drop=True)
                # recompute Match_Num after sorting
                bets_data_reset["Match_Num"] = range(len(bets_data_reset))
                x_col = "Date"
            except Exception:
                x_col = "Match_Num"

        plot_df = bets_data_reset

    # Ensure a fallback plot_df exists and normalize expected columns
    if plot_df is None:
        plot_df = bets_data.reset_index()
    if "_orig_index" not in plot_df.columns:
        plot_df["_orig_index"] = plot_df.iloc[:, 0]
    if "Match_Num" not in plot_df.columns:
        plot_df["Match_Num"] = range(len(plot_df))
    if "Cumulative_Marge" not in plot_df.columns:
        plot_df["Cumulative_Marge"] = plot_df.get(
            "Marge attendue", pd.Series([0] * len(plot_df))
        ).cumsum()

    # In unit mode, compute cumulative values divided by mise (1 unit = 1x stake)
    if unit_mode:
        try:
            if "Gains net" in plot_df.columns and "Mise" in plot_df.columns:
                plot_df = plot_df.copy()
                plot_df["_unit_gain"] = plot_df["Gains net"] / plot_df["Mise"].replace(
                    0, float("nan")
                )
                plot_df["Cumulative Gains"] = plot_df["_unit_gain"].cumsum()
            if "Marge attendue" in plot_df.columns and "Mise" in plot_df.columns:
                plot_df["_unit_marge"] = plot_df["Marge attendue"] / plot_df[
                    "Mise"
                ].replace(0, float("nan"))
                plot_df["Cumulative_Marge"] = plot_df["_unit_marge"].cumsum()
        except Exception:
            pass
    y_label_suffix = " u" if unit_mode else "€"

    # Build gains trace (explicit go.Scatter) to avoid creating duplicate traces
    try:
        gains_trace = go.Scatter(
            x=(
                plot_df[x_col].tolist()
                if x_col in plot_df.columns
                else list(range(len(plot_df)))
            ),
            y=(
                plot_df["Cumulative Gains"].tolist()
                if "Cumulative Gains" in plot_df.columns
                else [0] * len(plot_df)
            ),
            mode="lines+markers",
            name="Gains",
            line=dict(color="#32b296", width=2),
            # Keep markers present for selection but make them invisible by default
            marker=dict(size=0, color="#32b296", opacity=0),
        )
    except Exception:
        # Fallback to an empty trace if something goes wrong
        gains_trace = go.Scatter(x=[], y=[], mode="lines+markers", name="Gains")

    # If a table selection exists in session_state, mark that point as selected
    table_sel = st.session_state.get("selected_from_table")
    if table_sel is not None:
        try:
            if mode == "jour":
                # map original row index to its date, then find aggregated position
                try:
                    orig_row = bets_data.loc[table_sel]
                    row_date = pd.to_datetime(orig_row["Date"], errors="coerce")
                    if not pd.isna(row_date):
                        target_date = row_date.normalize()
                        mask = plot_df["Date"] == target_date
                        if mask.any():
                            pos = int(mask[mask].index[0])
                            gains_trace.update(selectedpoints=[pos])
                except Exception:
                    pass
            else:
                try:
                    mask = plot_df["_orig_index"] == table_sel
                except Exception:
                    mask = pd.Series([False] * len(plot_df))
                if not mask.any():
                    try:
                        mask = plot_df["_orig_index"] == int(table_sel)
                    except Exception:
                        pass
                if mask.any():
                    pos = int(mask[mask].index[0])
                    gains_trace.update(selectedpoints=[pos])
        except Exception:
            pass

    # Build margin trace (explicit go.Scatter): no markers, thin dashed white
    try:
        marge_trace = go.Scatter(
            x=(
                plot_df[x_col].tolist()
                if x_col in plot_df.columns
                else list(range(len(plot_df)))
            ),
            y=(
                plot_df["Cumulative_Marge"].tolist()
                if "Cumulative_Marge" in plot_df.columns
                else [0] * len(plot_df)
            ),
            mode="lines",
            name="Attendu",
            line=dict(color="#ffffff", width=1, dash="dash"),
            marker=dict(size=0),
            opacity=0.9,
        )
    except Exception:
        marge_trace = go.Scatter(x=[], y=[], mode="lines", name="Attendu")

    # Assemble figure with margin first, gains last (so gains receives selection)
    if show_drawdown:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.78, 0.22],
            vertical_spacing=0.04,
        )
    else:
        fig = go.Figure()
    # ensure traces show in legend
    marge_trace.update(showlegend=True)
    gains_trace.update(showlegend=True)
    # add margin first so gains remains on top
    if show_drawdown:
        fig.add_trace(marge_trace, row=1, col=1)
        fig.add_trace(gains_trace, row=1, col=1)
    else:
        fig.add_trace(marge_trace)
        fig.add_trace(gains_trace)

    # --- Peaks annotations (max & min of cumulative gains) ---
    try:
        if show_peaks and "Cumulative Gains" in plot_df.columns and len(plot_df) > 1:
            cum_series = pd.to_numeric(plot_df["Cumulative Gains"], errors="coerce")
            x_series = (
                plot_df[x_col]
                if x_col in plot_df.columns
                else pd.Series(range(len(plot_df)))
            )
            if cum_series.notna().any():
                imax = int(cum_series.idxmax())
                imin = int(cum_series.idxmin())
                peak_y = float(cum_series.loc[imax])
                trough_y = float(cum_series.loc[imin])
                peak_x = x_series.loc[imax]
                trough_x = x_series.loc[imin]
                ann_kwargs = {"row": 1, "col": 1} if show_drawdown else {}
                # Peak (max)
                fig.add_annotation(
                    x=peak_x,
                    y=peak_y,
                    text=f"▲ Peak {fmt_money(peak_y, unit_mode=unit_mode, decimals=2 if unit_mode else 0, sign=True)}",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=1,
                    arrowcolor="#32b296",
                    ax=0,
                    ay=-28,
                    font=dict(color="#32b296", size=11),
                    bgcolor="rgba(20,20,25,0.85)",
                    bordercolor="rgba(50,178,150,0.5)",
                    borderwidth=1,
                    borderpad=3,
                    **ann_kwargs,
                )
                # Trough (min) — only if distinct from peak
                if imin != imax:
                    fig.add_annotation(
                        x=trough_x,
                        y=trough_y,
                        text=f"▼ Low {fmt_money(trough_y, unit_mode=unit_mode, decimals=2 if unit_mode else 0, sign=True)}",
                        showarrow=True,
                        arrowhead=2,
                        arrowsize=1,
                        arrowwidth=1,
                        arrowcolor="#e04e4e",
                        ax=0,
                        ay=28,
                        font=dict(color="#e04e4e", size=11),
                        bgcolor="rgba(20,20,25,0.85)",
                        bordercolor="rgba(224,78,78,0.5)",
                        borderwidth=1,
                        borderpad=3,
                        **ann_kwargs,
                    )
    except Exception:
        pass

    # --- Drawdown trace (row 2) ---
    if show_drawdown:
        try:
            cum_vals = (
                plot_df["Cumulative Gains"].astype(float).tolist()
                if "Cumulative Gains" in plot_df.columns
                else [0.0] * len(plot_df)
            )
            running_max = np.maximum.accumulate(cum_vals) if len(cum_vals) else []
            drawdown_vals = [float(c) - float(m) for c, m in zip(cum_vals, running_max)]
            x_vals = (
                plot_df[x_col].tolist()
                if x_col in plot_df.columns
                else list(range(len(plot_df)))
            )
            dd_trace = go.Scatter(
                x=x_vals,
                y=drawdown_vals,
                mode="lines",
                name="Drawdown",
                line=dict(color="#e04e4e", width=1),
                fill="tozeroy",
                fillcolor="rgba(224,78,78,0.25)",
                hovertemplate=(
                    f"%{{y:{'.2f' if unit_mode else '.0f'}}}{y_label_suffix}"
                    "<extra>Drawdown</extra>"
                ),
                showlegend=True,
            )
            fig.add_trace(dd_trace, row=2, col=1)
            try:
                fig.update_yaxes(
                    title_text="Drawdown",
                    row=2,
                    col=1,
                    zeroline=True,
                    zerolinecolor="rgba(255,255,255,0.2)",
                )
            except Exception:
                pass
            # Max drawdown annotation
            try:
                if drawdown_vals:
                    idx_dd = int(np.argmin(drawdown_vals))
                    dd_min = float(drawdown_vals[idx_dd])
                    if dd_min < 0:
                        fig.add_annotation(
                            x=x_vals[idx_dd],
                            y=dd_min,
                            text=f"Max DD {fmt_money(dd_min, unit_mode=unit_mode, decimals=2 if unit_mode else 0, sign=True)}",
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1,
                            arrowwidth=1,
                            arrowcolor="#e04e4e",
                            ax=0,
                            ay=20,
                            font=dict(color="#e04e4e", size=10),
                            bgcolor="rgba(20,20,25,0.85)",
                            bordercolor="rgba(224,78,78,0.5)",
                            borderwidth=1,
                            borderpad=2,
                            row=2,
                            col=1,
                        )
            except Exception:
                pass
        except Exception:
            pass

    # Improve hover templates to include trace name and formatted value
    try:
        fmt = ".2f" if unit_mode else ".0f"
        gains_trace.update(
            hovertemplate=f"%{{y:{fmt}}}{y_label_suffix}<extra>Gains</extra>"
        )
        marge_trace.update(
            hovertemplate=f"%{{y:{fmt}}}{y_label_suffix}<extra>Attendu</extra>"
        )
    except Exception:
        pass

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
        ),
        margin=dict(t=40, b=20, l=40, r=40),
    )

    # If using date/time on x-axis, ensure axis is shown as date
    try:
        if x_col == "Date":
            fig.update_xaxes(type="date", tickformat="%d %b %Y\n%H:%M")
    except Exception:
        pass

    # Optionally show legend title
    try:
        fig.update_layout(legend_title_text="Légende")
    except Exception:
        pass

    with st.container(border=True):
        event_dict = st.plotly_chart(
            fig,
            height=480 if show_drawdown else 400,
            selection_mode="points",
            on_select="rerun",
            width="stretch",
        )
        # selected points structure depends on streamlit/plotly integration
        selected = (
            event_dict.get("selection", {}).get("points", [])
            if isinstance(event_dict, dict)
            else []
        )

        # persist plot selection into session_state for other components to read
        if selected and len(selected) > 0:
            try:
                pt_idx = int(selected[0].get("point_index"))
                # map point index back to original index value
                try:
                    orig_idx = bets_data_reset.iloc[pt_idx]["_orig_index"]
                    st.session_state["selected_from_chart"] = int(orig_idx)
                except Exception:
                    # fallback: store the point index
                    st.session_state["selected_from_chart"] = pt_idx

                # clear table selection so chart selection takes precedence
                if st.session_state.get("selected_from_table") is not None:
                    del st.session_state["selected_from_table"]
            except Exception:
                pass
        else:
            # remove chart selection key if no selection
            if st.session_state.get("selected_from_chart") is not None:
                del st.session_state["selected_from_chart"]

    return selected


def render_distribution_bar(
    bets_data: pd.DataFrame,
    distribution_type: str,
    column_name: str = None,
    bins: list = None,
    labels: list = None,
    colors: list = None,
    color_mapping: dict = None,
    count_icon: str = "📊",
    count_title: str = "Répartition du nombre de paris",
    mise_icon: str = "💰",
    mise_title: str = "Répartition des mises",
    calculate_bins_fn: callable = None,
) -> None:
    """Render a colored progress bar showing the distribution of bets by a given criterion.

    Args:
        bets_data: DataFrame containing bet data
        distribution_type: Type of distribution ('binned', 'categorical', 'computed')
        column_name: Column name to use for categorical distributions
        bins: Bin edges for binned distributions
        labels: Labels for bins or categories
        colors: List of colors to use (for binned or categorical with labels)
        color_mapping: Dict mapping categories to colors (for categorical)
        count_icon: Icon for count distribution title
        count_title: Title for count distribution
        mise_icon: Icon for mise distribution title
        mise_title: Title for mise distribution
        calculate_bins_fn: Function to calculate bins for 'computed' type (receives df, returns series)
    """
    if bets_data.empty:
        return

    try:
        df_copy = bets_data.copy()

        # Process data based on distribution type
        if distribution_type == "binned":
            # For binned data (cote, marge)
            if calculate_bins_fn:
                values = calculate_bins_fn(df_copy)
            else:
                values = pd.to_numeric(df_copy[column_name], errors="coerce")

            df_copy["bin_category"] = pd.cut(
                values, bins=bins, labels=labels, include_lowest=True
            )
            group_column = "bin_category"
            categories = labels

        elif distribution_type == "categorical":
            # For categorical data (surface, competition)
            if column_name not in df_copy.columns:
                return
            group_column = column_name
            counts_series = df_copy[column_name].value_counts()
            categories = counts_series.index.tolist()

            # Sort competitions in standard order (ATP, WTA, Doubles) if this is the Compétition column
            if column_name == "Compétition":
                categories = sort_competitions(categories)

        else:
            return

        # Count bets in each category
        counts = (
            df_copy[group_column].value_counts().sort_index()
            if distribution_type == "binned"
            else df_copy[group_column].value_counts()
        )
        total_count = counts.sum()

        # Sum of bets (Mise) in each category
        if distribution_type == "binned":
            mise_sums = (
                df_copy.groupby(group_column, observed=True)["Mise"]
                .sum()
                .reindex(categories, fill_value=0)
            )
        else:
            mise_sums = df_copy.groupby(group_column, observed=True)["Mise"].sum()

        total_mise = mise_sums.sum()

        if total_count == 0:
            return

        # Calculate percentages
        count_percentages = (counts / total_count * 100).to_dict()
        mise_percentages = {}
        if total_mise > 0:
            mise_percentages = (mise_sums / total_mise * 100).to_dict()

        # Build progress bar segments for COUNT
        bar_segments_count = []
        for i, category in enumerate(categories):
            pct = count_percentages.get(category, 0)
            if pct > 0:
                if color_mapping:
                    color = color_mapping.get(category, "#64748b")
                elif colors:
                    color = colors[i % len(colors)]
                else:
                    color = "#64748b"
                segment = f"<div style='width: {pct}%; background-color: {color}; display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: 600;'><span style='text-shadow: 0 1px 2px rgba(0,0,0,0.5);'>{pct:.1f}%</span></div>"
                bar_segments_count.append(segment)

        # Build legend items for COUNT
        legend_items_count = []
        for i, category in enumerate(categories):
            pct = count_percentages.get(category, 0)
            count = counts.get(category, 0)
            if color_mapping:
                color = color_mapping.get(category, "#64748b")
            elif colors:
                color = colors[i % len(colors)]
            else:
                color = "#64748b"
            item = f"<div style='display: flex; align-items: center; margin: 4px 8px;'><div style='width: 12px; height: 12px; background-color: {color}; border-radius: 3px; margin-right: 6px;'></div><span style='color: #d1d4dc; font-size: 12px; font-weight: 600;'>{category}: {count} ({pct:.1f}%)</span></div>"
            legend_items_count.append(item)

        # Build progress bar segments for MISE
        bar_segments_mise = []
        for i, category in enumerate(categories):
            pct = mise_percentages.get(category, 0)
            if pct > 0:
                if color_mapping:
                    color = color_mapping.get(category, "#64748b")
                elif colors:
                    color = colors[i % len(colors)]
                else:
                    color = "#64748b"
                segment = f"<div style='width: {pct}%; background-color: {color}; display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: 600;'><span style='text-shadow: 0 1px 2px rgba(0,0,0,0.5);'>{pct:.1f}%</span></div>"
                bar_segments_mise.append(segment)

        # Build legend items for MISE
        legend_items_mise = []
        for i, category in enumerate(categories):
            pct = mise_percentages.get(category, 0)
            mise_val = mise_sums.get(category, 0)
            if color_mapping:
                color = color_mapping.get(category, "#64748b")
            elif colors:
                color = colors[i % len(colors)]
            else:
                color = "#64748b"
            mise_formatted = fmt_num(mise_val)
            item = f"<div style='display: flex; align-items: center; margin: 4px 8px;'><div style='width: 12px; height: 12px; background-color: {color}; border-radius: 3px; margin-right: 6px;'></div><span style='color: #d1d4dc; font-size: 12px; font-weight: 600;'>{category}: {mise_formatted}€ ({pct:.1f}%)</span></div>"
            legend_items_mise.append(item)

        # Assemble final HTML with both bars
        bar_html = f"""
        <div style='margin: 20px 0;'>
            <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px; font-weight: 600;'>{count_icon} {count_title}</div>
            <div style='display: flex; width: 100%; height: 30px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.3);'>
                {"".join(bar_segments_count)}
            </div>
            <div style='display: flex; justify-content: space-around; margin-top: 12px; flex-wrap: wrap;'>
                {"".join(legend_items_count)}
            </div>
        </div>
        
        <div style='margin: 20px 0;'>
            <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px; font-weight: 600;'>{mise_icon} {mise_title}</div>
            <div style='display: flex; width: 100%; height: 30px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.3);'>
                {"".join(bar_segments_mise)}
            </div>
            <div style='display: flex; justify-content: space-around; margin-top: 12px; flex-wrap: wrap;'>
                {"".join(legend_items_mise)}
            </div>
        </div>
        """

        st.markdown(bar_html, unsafe_allow_html=True)

    except Exception as e:
        # Silently fail if there's an issue
        pass


def render_cote_distribution_bar(bets_data: pd.DataFrame) -> None:
    """Render a colored progress bar showing the distribution of bets by odds ranges."""
    render_distribution_bar(
        bets_data=bets_data,
        distribution_type="binned",
        column_name="Cote",
        bins=[0, 1.5, 2.0, 2.5, 3.0, 5, 100],
        labels=["<1.5", "1.5-2.0", "2.0-2.5", "2.5-3.0", "3.0-5.0", "≥5.0"],
        colors=["#10b981", "#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#ef4444"],
        count_icon="📊",
        count_title="Répartition du nombre de paris par cote",
        mise_icon="💰",
        mise_title="Répartition des mises par cote",
    )


def render_marge_distribution_bar(bets_data: pd.DataFrame) -> None:
    """Render a colored progress bar showing the distribution of bets by expected margin (ROI attendu)."""

    def calculate_roi_attendu(df):
        """Calculate ROI attendu = (Cote / Prédiction - 1) * 100"""
        cote_vals = pd.to_numeric(df["Cote"], errors="coerce")
        pred_vals = pd.to_numeric(df["Prédiction"], errors="coerce")
        roi_att = (cote_vals / pred_vals - 1) * 100
        return roi_att.fillna(0)

    render_distribution_bar(
        bets_data=bets_data,
        distribution_type="binned",
        bins=[-100, 0, 2, 5, 10, 20, 100],
        labels=["<0%", "0-2%", "2-5%", "5-10%", "10-20%", "≥20%"],
        colors=["#10b981", "#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#ef4444"],
        count_icon="📈",
        count_title="Répartition du nombre de paris par ROI attendu",
        mise_icon="💵",
        mise_title="Répartition des mises par ROI attendu",
        calculate_bins_fn=calculate_roi_attendu,
    )


def render_surface_distribution_bar(bets_data: pd.DataFrame) -> None:
    """Render a colored progress bar showing the distribution of bets by surface type."""
    render_distribution_bar(
        bets_data=bets_data,
        distribution_type="categorical",
        column_name="Surface",
        color_mapping={
            "Dur": "#3772d1",
            "Terre battue": "#b45715",
            "Gazon": "#22c55e",
            "Carpet": "#8b5cf6",
            "Indoor Hard": "#6366f1",
        },
        count_icon="🎾",
        count_title="Répartition du nombre de paris par surface",
        mise_icon="🏟️",
        mise_title="Répartition des mises par surface",
    )


def render_competition_distribution_bar(bets_data: pd.DataFrame) -> None:
    """Render a colored progress bar showing the distribution of bets by competition/tournament."""
    render_distribution_bar(
        bets_data=bets_data,
        distribution_type="categorical",
        column_name="Compétition",
        color_mapping={
            "atp": "#10b981",  # Vert émeraude pour ATP (masculin)
            "Atp": "#10b981",  # Support both cases
            "wta": "#ec4899",  # Rose pour WTA (féminin)
            "Wta": "#ec4899",  # Support both cases
            "doubles": "#8b5cf6",  # Violet pour Doubles (mixte)
            "Doubles": "#8b5cf6",  # Support both cases
            "challenger": "#6366f1",  # Bleu indigo pour Challenger
            "Challenger": "#6366f1",  # Support both cases
        },
        count_icon="🏆",
        count_title="Répartition du nombre de paris par compétition",
        mise_icon="💸",
        mise_title="Répartition des mises par compétition",
    )


def render_weekly_performance_chart(bets_data: pd.DataFrame) -> None:
    """Two side-by-side weekly charts: Gains (réel + attendu) and ROI (réel + attendu)."""
    if bets_data is None or bets_data.empty:
        return
    df = bets_data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        return

    week_start = df["Date"].dt.to_period("W-SUN").dt.start_time
    grouped = (
        df.assign(_week=week_start)
        .groupby("_week", as_index=False)
        .agg(
            mises=("Mise", "sum"),
            gains=("Gains net", "sum"),
            marges=("Marge attendue", "sum"),
            n=("Mise", "count"),
        )
        .sort_values("_week")
    )
    if grouped.empty:
        return
    grouped["roi"] = np.where(
        grouped["mises"] > 0, grouped["gains"] / grouped["mises"] * 100, 0.0
    )
    grouped["roi_attendu"] = np.where(
        grouped["mises"] > 0, grouped["marges"] / grouped["mises"] * 100, 0.0
    )
    # Rounding cohérent: gains en € entiers, ROI 1 décimale
    grouped["gains"] = grouped["gains"].round(0)
    grouped["marges"] = grouped["marges"].round(0)
    grouped["mises"] = grouped["mises"].round(0)
    grouped["roi"] = grouped["roi"].round(1)
    grouped["roi_attendu"] = grouped["roi_attendu"].round(1)
    grouped["label"] = grouped["_week"].dt.strftime("%d %b %Y")
    bar_colors = ["#32b296" if g >= 0 else "#e04e4e" for g in grouped["gains"]]
    roi_colors = ["#32b296" if r >= 0 else "#e04e4e" for r in grouped["roi"]]

    layout_common = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=50, b=60, l=60, r=20),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        bargap=0.25,
        height=400,
    )

    # --- Gains chart ---
    fig_g = go.Figure()
    fig_g.add_trace(
        go.Bar(
            x=grouped["label"],
            y=grouped["gains"],
            name="Gains réels",
            marker_color=bar_colors,
            hovertemplate=(
                "Semaine du %{x}<br>"
                "Gains: <b>%{y:+.0f}€</b><br>"
                "Paris: %{customdata[0]}<br>"
                "Mises: %{customdata[1]:.0f}€"
                "<extra></extra>"
            ),
            customdata=np.stack([grouped["n"], grouped["mises"]], axis=-1),
        )
    )
    fig_g.add_trace(
        go.Scatter(
            x=grouped["label"],
            y=grouped["marges"],
            name="Gains attendus",
            mode="lines+markers",
            line=dict(color="#3b82f6", width=2, dash="dot"),
            marker=dict(size=6),
            hovertemplate="Attendu: %{y:+.0f}€<extra></extra>",
        )
    )
    fig_g.add_hline(y=0, line_color="#4b5563", line_width=1, line_dash="dash")
    fig_g.update_layout(
        title=dict(
            text="💸 Gains hebdomadaires (réel vs attendu)",
            font=dict(size=15, color="#9ca3af"),
            x=0.5,
            xanchor="center",
        ),
        **layout_common,
    )
    fig_g.update_xaxes(gridcolor="rgba(100,100,120,0.15)", title_text="Semaine")
    fig_g.update_yaxes(
        gridcolor="rgba(100,100,120,0.15)",
        title_text="Gains (€)",
        zeroline=True,
        zerolinecolor="#4b5563",
    )

    # --- ROI chart ---
    fig_r = go.Figure()
    fig_r.add_trace(
        go.Bar(
            x=grouped["label"],
            y=grouped["roi"],
            name="ROI réel",
            marker_color=roi_colors,
            hovertemplate=(
                "Semaine du %{x}<br>"
                "ROI: <b>%{y:+.1f}%</b><br>"
                "Paris: %{customdata[0]}"
                "<extra></extra>"
            ),
            customdata=np.stack([grouped["n"]], axis=-1),
        )
    )
    fig_r.add_trace(
        go.Scatter(
            x=grouped["label"],
            y=grouped["roi_attendu"],
            name="ROI attendu",
            mode="lines+markers",
            line=dict(color="#3b82f6", width=2, dash="dot"),
            marker=dict(size=6),
            hovertemplate="ROI attendu: %{y:+.1f}%<extra></extra>",
        )
    )
    fig_r.add_hline(y=0, line_color="#4b5563", line_width=1, line_dash="dash")
    fig_r.update_layout(
        title=dict(
            text="📈 ROI hebdomadaire (réel vs attendu)",
            font=dict(size=15, color="#9ca3af"),
            x=0.5,
            xanchor="center",
        ),
        **layout_common,
    )
    fig_r.update_xaxes(gridcolor="rgba(100,100,120,0.15)", title_text="Semaine")
    fig_r.update_yaxes(
        gridcolor="rgba(100,100,120,0.15)",
        title_text="ROI (%)",
        zeroline=True,
        zerolinecolor="#4b5563",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig_g, width="stretch")
    with c2:
        st.plotly_chart(fig_r, width="stretch")


def render_weekday_performance_chart(bets_data: pd.DataFrame) -> None:
    """Two side-by-side weekday charts: Gains (réel + attendu) and ROI (réel + attendu)."""
    if bets_data is None or bets_data.empty:
        return
    df = bets_data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        return

    day_names_fr = {
        0: "Lundi",
        1: "Mardi",
        2: "Mercredi",
        3: "Jeudi",
        4: "Vendredi",
        5: "Samedi",
        6: "Dimanche",
    }
    df["_dow"] = df["Date"].dt.dayofweek
    grouped = (
        df.groupby("_dow", as_index=False)
        .agg(
            mises=("Mise", "sum"),
            gains=("Gains net", "sum"),
            marges=("Marge attendue", "sum"),
            n=("Mise", "count"),
            wins=("Gains net", lambda x: int((x > 0).sum())),
        )
        .sort_values("_dow")
    )
    if grouped.empty:
        return
    grouped["jour"] = grouped["_dow"].map(day_names_fr)
    grouped["roi"] = np.where(
        grouped["mises"] > 0, grouped["gains"] / grouped["mises"] * 100, 0.0
    )
    grouped["roi_attendu"] = np.where(
        grouped["mises"] > 0, grouped["marges"] / grouped["mises"] * 100, 0.0
    )
    grouped["winrate"] = np.where(
        grouped["n"] > 0, grouped["wins"] / grouped["n"] * 100, 0.0
    )
    # Rounding cohérent
    grouped["gains"] = grouped["gains"].round(0)
    grouped["marges"] = grouped["marges"].round(0)
    grouped["mises"] = grouped["mises"].round(0)
    grouped["roi"] = grouped["roi"].round(1)
    grouped["roi_attendu"] = grouped["roi_attendu"].round(1)
    grouped["winrate"] = grouped["winrate"].round(0)
    bar_colors_g = ["#32b296" if g >= 0 else "#e04e4e" for g in grouped["gains"]]
    bar_colors_r = ["#32b296" if r >= 0 else "#e04e4e" for r in grouped["roi"]]

    layout_common = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=50, b=60, l=60, r=20),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        bargap=0.3,
        height=380,
    )

    # --- Gains chart ---
    fig_g = go.Figure()
    fig_g.add_trace(
        go.Bar(
            x=grouped["jour"],
            y=grouped["gains"],
            name="Gains réels",
            marker_color=bar_colors_g,
            text=[f"{g:+.0f}€" for g in grouped["gains"]],
            textposition="outside",
            textfont=dict(color="#d1d4dc", size=10, weight=600),
            hovertemplate=(
                "%{x}<br>"
                "Gains: <b>%{y:+.0f}€</b><br>"
                "Paris: %{customdata[0]}<br>"
                "Mises: %{customdata[1]:.0f}€<br>"
                "Winrate: %{customdata[2]:.0f}%"
                "<extra></extra>"
            ),
            customdata=np.stack(
                [grouped["n"], grouped["mises"], grouped["winrate"]], axis=-1
            ),
        )
    )
    fig_g.add_trace(
        go.Scatter(
            x=grouped["jour"],
            y=grouped["marges"],
            name="Gains attendus",
            mode="lines+markers",
            line=dict(color="#3b82f6", width=2, dash="dot"),
            marker=dict(size=8),
            hovertemplate="Attendu %{x}: %{y:+.0f}€<extra></extra>",
        )
    )
    fig_g.add_hline(y=0, line_color="#4b5563", line_width=1, line_dash="dash")
    fig_g.update_layout(
        title=dict(
            text="💸 Gains par jour (réel vs attendu)",
            font=dict(size=15, color="#9ca3af"),
            x=0.5,
            xanchor="center",
        ),
        **layout_common,
    )
    fig_g.update_xaxes(gridcolor="rgba(100,100,120,0.15)", title_text="Jour")
    fig_g.update_yaxes(
        gridcolor="rgba(100,100,120,0.15)",
        title_text="Gains (€)",
        zeroline=True,
        zerolinecolor="#4b5563",
    )

    # --- ROI chart ---
    fig_r = go.Figure()
    fig_r.add_trace(
        go.Bar(
            x=grouped["jour"],
            y=grouped["roi"],
            name="ROI réel",
            marker_color=bar_colors_r,
            text=[f"{r:+.1f}%" for r in grouped["roi"]],
            textposition="outside",
            textfont=dict(color="#d1d4dc", size=10, weight=600),
            hovertemplate=(
                "%{x}<br>"
                "ROI: <b>%{y:+.1f}%</b><br>"
                "Paris: %{customdata[0]}"
                "<extra></extra>"
            ),
            customdata=np.stack([grouped["n"]], axis=-1),
        )
    )
    fig_r.add_trace(
        go.Scatter(
            x=grouped["jour"],
            y=grouped["roi_attendu"],
            name="ROI attendu",
            mode="lines+markers",
            line=dict(color="#3b82f6", width=2, dash="dot"),
            marker=dict(size=8),
            hovertemplate="ROI attendu %{x}: %{y:+.1f}%<extra></extra>",
        )
    )
    fig_r.add_hline(y=0, line_color="#4b5563", line_width=1, line_dash="dash")
    fig_r.update_layout(
        title=dict(
            text="📈 ROI par jour (réel vs attendu)",
            font=dict(size=15, color="#9ca3af"),
            x=0.5,
            xanchor="center",
        ),
        **layout_common,
    )
    fig_r.update_xaxes(gridcolor="rgba(100,100,120,0.15)", title_text="Jour")
    fig_r.update_yaxes(
        gridcolor="rgba(100,100,120,0.15)",
        title_text="ROI (%)",
        zeroline=True,
        zerolinecolor="#4b5563",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig_g, width="stretch")
    with c2:
        st.plotly_chart(fig_r, width="stretch")


def render_cote_histogram(bets_data: pd.DataFrame) -> None:
    """Render a histogram showing the distribution of bets by odds (cote)."""
    if bets_data.empty:
        return

    try:
        df_copy = bets_data.copy()
        cote_vals = pd.to_numeric(df_copy["Cote"], errors="coerce").dropna()

        if len(cote_vals) == 0:
            return

        # Define bins and colors matching the distribution bar
        bins = [0, 1.5, 2.0, 2.5, 3.0, 5, 100]
        labels = ["<1.5", "1.5-2.0", "2.0-2.5", "2.5-3.0", "3.0-5.0", "≥5.0"]
        colors = ["#10b981", "#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#ef4444"]

        # Create binned data
        df_copy["Cote_bin"] = pd.cut(
            cote_vals, bins=bins, labels=labels, include_lowest=True
        )

        # Count bets per bin
        counts = df_copy["Cote_bin"].value_counts().reindex(labels, fill_value=0)

        # Create histogram
        fig = go.Figure()

        for i, label in enumerate(labels):
            fig.add_trace(
                go.Bar(
                    x=[label],
                    y=[counts[label]],
                    name=label,
                    marker_color=colors[i],
                    text=[counts[label]],
                    textposition="outside",
                    textfont=dict(color="#d1d4dc", size=12, weight=600),
                    hovertemplate=f"{label}: %{{y}} paris<extra></extra>",
                    showlegend=False,
                )
            )

        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
            xaxis_title="Plage de cotes",
            yaxis_title="Nombre de paris",
            margin=dict(t=40, b=60, l=60, r=40),
            bargap=0.2,
            title=dict(
                text="📊 Distribution des paris par cote",
                font=dict(size=16, color="#9ca3af"),
                x=0.5,
                xanchor="center",
            ),
        )

        fig.update_xaxes(gridcolor="rgba(100,100,120,0.2)")
        fig.update_yaxes(gridcolor="rgba(100,100,120,0.2)")

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        pass


def render_marge_histogram(bets_data: pd.DataFrame) -> None:
    """Render a histogram showing the distribution of bets by expected margin (ROI attendu)."""
    if bets_data.empty:
        return

    try:
        df_copy = bets_data.copy()

        # Calculate ROI attendu
        cote_vals = pd.to_numeric(df_copy["Cote"], errors="coerce")
        pred_vals = pd.to_numeric(df_copy["Prédiction"], errors="coerce")
        roi_att = ((cote_vals / pred_vals - 1) * 100).dropna()

        if len(roi_att) == 0:
            return

        # Define bins and colors matching the distribution bar
        bins = [-100, 0, 2, 5, 10, 20, 100]
        labels = ["<0%", "0-2%", "2-5%", "5-10%", "10-20%", "≥20%"]
        colors = ["#10b981", "#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#ef4444"]

        # Create binned data
        df_copy["Marge_bin"] = pd.cut(
            roi_att, bins=bins, labels=labels, include_lowest=True
        )

        # Count bets per bin
        counts = df_copy["Marge_bin"].value_counts().reindex(labels, fill_value=0)

        # Create histogram
        fig = go.Figure()

        for i, label in enumerate(labels):
            fig.add_trace(
                go.Bar(
                    x=[label],
                    y=[counts[label]],
                    name=label,
                    marker_color=colors[i],
                    text=[counts[label]],
                    textposition="outside",
                    textfont=dict(color="#d1d4dc", size=12, weight=600),
                    hovertemplate=f"{label}: %{{y}} paris<extra></extra>",
                    showlegend=False,
                )
            )

        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
            xaxis_title="Plage de ROI attendu",
            yaxis_title="Nombre de paris",
            margin=dict(t=40, b=60, l=60, r=40),
            bargap=0.2,
            title=dict(
                text="📈 Distribution des paris par ROI attendu",
                font=dict(size=16, color="#9ca3af"),
                x=0.5,
                xanchor="center",
            ),
        )

        fig.update_xaxes(gridcolor="rgba(100,100,120,0.2)")
        fig.update_yaxes(gridcolor="rgba(100,100,120,0.2)")

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        pass


def render_cote_raw_histogram(bets_data: pd.DataFrame, nbins: int = 50) -> None:
    """Render a histogram showing the raw distribution of bets by odds (cote) - no binning.

    Args:
        bets_data: DataFrame containing bet data
        nbins: Number of bins for the histogram (default: 50)
    """
    if bets_data.empty:
        return

    try:
        df_copy = bets_data.copy()
        cote_vals = pd.to_numeric(df_copy["Cote"], errors="coerce").dropna()

        if len(cote_vals) == 0:
            return

        # Define bins and colors matching the distribution bar
        bins = [0, 1.5, 2.0, 2.5, 3.0, 5, 100]
        colors_map = ["#10b981", "#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#ef4444"]

        # Assign color to each value based on which bin it falls into
        def get_color(val):
            for i in range(len(bins) - 1):
                if bins[i] <= val < bins[i + 1]:
                    return colors_map[i]
            return colors_map[-1]

        # Create histogram data manually for better control over bins
        hist_values, bin_edges = np.histogram(cote_vals, bins=nbins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # Assign colors to bins based on their center values
        bin_colors = [get_color(center) for center in bin_centers]

        # Create figure with bar traces
        fig = go.Figure()

        # Add bars grouped by color for better organization
        for color in colors_map:
            # Get indices where this color is used
            color_indices = [i for i, c in enumerate(bin_colors) if c == color]
            if len(color_indices) > 0:
                fig.add_trace(
                    go.Bar(
                        x=[bin_centers[i] for i in color_indices],
                        y=[hist_values[i] for i in color_indices],
                        marker_color=color,
                        marker_line_color="rgba(255,255,255,0.2)",
                        marker_line_width=1,
                        width=(bin_edges[1] - bin_edges[0]) * 0.9,
                        hovertemplate="Cote: %{x:.2f}<br>Nombre: %{y}<extra></extra>",
                        showlegend=False,
                    )
                )

        # Add smoothed line (moving average)
        try:
            # Reuse histogram data already calculated above
            # Apply smoothing using convolution (moving average)
            # Adaptive window size: better scaling for different nbins
            # More bins = larger window to maintain smoothness
            window_size = max(5, min(nbins // 5, 20))  # Between 5 and 20
            kernel = np.ones(window_size) / window_size
            smoothed_values = np.convolve(hist_values, kernel, mode="same")

            # Apply secondary smoothing for very smooth curve
            if nbins > 30:
                window_size_2 = max(3, window_size // 2)
                kernel_2 = np.ones(window_size_2) / window_size_2
                smoothed_values = np.convolve(smoothed_values, kernel_2, mode="same")

            # Add smoothed line trace
            fig.add_trace(
                go.Scatter(
                    x=bin_centers,
                    y=smoothed_values,
                    mode="lines",
                    name="Tendance lissée",
                    line=dict(color="#fbbf24", width=3, shape="spline"),
                    hovertemplate="Cote: %{x:.2f}<br>Tendance: %{y:.1f}<extra></extra>",
                    showlegend=True,
                )
            )
        except Exception:
            pass

        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
            xaxis_title="Cote",
            yaxis_title="Nombre de paris",
            margin=dict(t=40, b=60, l=60, r=40),
            title=dict(
                text="📊 Distribution continue des cotes",
                font=dict(size=16, color="#9ca3af"),
                x=0.5,
                xanchor="center",
            ),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(0,0,0,0)",
                font=dict(color="#d1d4dc"),
            ),
        )

        fig.update_xaxes(gridcolor="rgba(100,100,120,0.2)")
        fig.update_yaxes(gridcolor="rgba(100,100,120,0.2)")

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        pass


def render_marge_raw_histogram(bets_data: pd.DataFrame, nbins: int = 50) -> None:
    """Render a histogram showing the raw distribution of bets by expected margin (ROI attendu) - no binning.

    Args:
        bets_data: DataFrame containing bet data
        nbins: Number of bins for the histogram (default: 50)
    """
    if bets_data.empty:
        return

    try:
        df_copy = bets_data.copy()

        # Calculate ROI attendu
        cote_vals = pd.to_numeric(df_copy["Cote"], errors="coerce")
        pred_vals = pd.to_numeric(df_copy["Prédiction"], errors="coerce")
        roi_att = ((cote_vals / pred_vals - 1) * 100).dropna()

        if len(roi_att) == 0:
            return

        # Define bins and colors matching the distribution bar
        bins = [-100, 0, 2, 5, 10, 20, 100]
        colors_map = ["#10b981", "#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#ef4444"]

        # Assign color to each value based on which bin it falls into
        def get_color(val):
            for i in range(len(bins) - 1):
                if bins[i] <= val < bins[i + 1]:
                    return colors_map[i]
            return colors_map[-1]

        # Create histogram data manually for better control over bins
        hist_values, bin_edges = np.histogram(roi_att, bins=nbins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # Assign colors to bins based on their center values
        bin_colors = [get_color(center) for center in bin_centers]

        # Create figure with bar traces
        fig = go.Figure()

        # Add bars grouped by color for better organization
        for color in colors_map:
            # Get indices where this color is used
            color_indices = [i for i, c in enumerate(bin_colors) if c == color]
            if len(color_indices) > 0:
                fig.add_trace(
                    go.Bar(
                        x=[bin_centers[i] for i in color_indices],
                        y=[hist_values[i] for i in color_indices],
                        marker_color=color,
                        marker_line_color="rgba(255,255,255,0.2)",
                        marker_line_width=1,
                        width=(bin_edges[1] - bin_edges[0]) * 0.9,
                        hovertemplate="ROI attendu: %{x:.1f}%<br>Nombre: %{y}<extra></extra>",
                        showlegend=False,
                    )
                )

        # Add smoothed line (moving average)
        try:
            # Reuse histogram data already calculated above
            # Apply smoothing using convolution (moving average)
            # Adaptive window size: better scaling for different nbins
            # More bins = larger window to maintain smoothness
            window_size = max(5, min(nbins // 5, 20))  # Between 5 and 20
            kernel = np.ones(window_size) / window_size
            smoothed_values = np.convolve(hist_values, kernel, mode="same")

            # Apply secondary smoothing for very smooth curve
            if nbins > 30:
                window_size_2 = max(3, window_size // 2)
                kernel_2 = np.ones(window_size_2) / window_size_2
                smoothed_values = np.convolve(smoothed_values, kernel_2, mode="same")

            # Add smoothed line trace
            fig.add_trace(
                go.Scatter(
                    x=bin_centers,
                    y=smoothed_values,
                    mode="lines",
                    name="Tendance lissée",
                    line=dict(color="#fbbf24", width=3, shape="spline"),
                    hovertemplate="ROI attendu: %{x:.1f}%<br>Tendance: %{y:.1f}<extra></extra>",
                    showlegend=True,
                )
            )
        except Exception:
            pass

        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
            xaxis_title="ROI attendu (%)",
            yaxis_title="Nombre de paris",
            margin=dict(t=40, b=60, l=60, r=40),
            title=dict(
                text="📈 Distribution continue du ROI attendu",
                font=dict(size=16, color="#9ca3af"),
                x=0.5,
                xanchor="center",
            ),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(0,0,0,0)",
                font=dict(color="#d1d4dc"),
            ),
        )

        fig.update_xaxes(gridcolor="rgba(100,100,120,0.2)")
        fig.update_yaxes(gridcolor="rgba(100,100,120,0.2)")

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        pass


def render_calendar_heatmap(
    bets_data: pd.DataFrame,
    metric: str = "ROI",
    days: int = 365,
) -> None:
    """GitHub-style calendar heatmap of daily betting activity.

    metric: one of {"ROI", "Gains net", "Nb paris", "Mises"}.
    """
    if bets_data is None or bets_data.empty or "Date" not in bets_data.columns:
        st.info("Aucune donnée pour la heatmap calendaire.")
        return

    # Keep only the columns needed and pre-sort to maximise cache hit-rate
    df_in = bets_data[["Date", "Mise", "Gains net"]].copy()
    df_in["Date"] = pd.to_datetime(df_in["Date"], errors="coerce")
    df_in = df_in.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    if df_in.empty:
        st.info("Aucune donnée pour la heatmap calendaire.")
        return

    payload = _compute_heatmap_payload(df_in, metric=metric, days=int(days))
    if payload is None:
        st.info("Aucune donnée pour la heatmap calendaire.")
        return

    _render_heatmap_figure(payload)


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def _compute_heatmap_payload(df_in: pd.DataFrame, metric: str, days: int):
    """Aggregate per-day stats and build the matrices needed by the heatmap.

    Cached: re-runs only when (filtered df, metric, days) change.
    Returns a dict of plain Python / numpy structures (Plotly-ready).
    """
    df = df_in.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        return None

    df["day"] = df["Date"].dt.normalize()
    per_day = df.groupby("day").agg(
        nb=("Mise", "count"),
        mises=("Mise", "sum"),
        gains=("Gains net", "sum"),
    )
    per_day["roi"] = np.where(
        per_day["mises"] > 0, per_day["gains"] / per_day["mises"] * 100, 0.0
    )

    end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=days - 1)
    start = start - pd.Timedelta(days=start.weekday())  # align to Monday
    full_idx = pd.date_range(start=start, end=end, freq="D")
    per_day = per_day.reindex(full_idx).fillna(0.0)
    per_day.index.name = "day"

    # --- Color schemes (GitHub-inspired, muted, dark-mode friendly) ---
    diverging_scale = [
        [0.0, "#7f1d1d"],  # deep red
        [0.25, "#b91c1c"],
        [0.5, "#2a2f3a"],  # neutral / near-zero  (matches background)
        [0.75, "#15803d"],
        [1.0, "#16a34a"],  # rich green
    ]
    sequential_blue = [
        [0.0, "#1e3a5f"],
        [0.25, "#2563eb"],
        [0.5, "#3b82f6"],
        [0.75, "#60a5fa"],
        [1.0, "#93c5fd"],
    ]

    metric_map = {
        "ROI": ("roi", "%", diverging_scale, True),
        "Gains net": ("gains", "€", diverging_scale, True),
        "Nb paris": ("nb", "", sequential_blue, False),
        "Mises": ("mises", "€", sequential_blue, False),
    }
    col, unit, colorscale, diverging = metric_map.get(metric, metric_map["ROI"])
    z_series = per_day[col].astype(float)

    weeks = ((per_day.index - start).days // 7).astype(int).to_numpy()
    weekdays = per_day.index.weekday.to_numpy()
    n_weeks = int(weeks.max()) + 1

    # --- Foreground (active days only) ---
    z_fg = np.full((7, n_weeks), np.nan)
    active = per_day["nb"].to_numpy() > 0
    for w, d, v, a in zip(weeks, weekdays, z_series.to_numpy(), active):
        if a:
            z_fg[d, w] = v

    # --- Background (light dotted grid via a constant trace) ---
    z_bg = np.zeros((7, n_weeks))

    # Color range
    if diverging:
        valid = z_series[per_day["nb"] > 0]
        amax = float(np.nanmax(np.abs(valid))) if not valid.empty else 1.0
        amax = amax if amax > 0 else 1.0
        zmin, zmid, zmax = -amax, 0.0, amax
    else:
        zmin = 0.0
        zmid = None
        zmax = float(np.nanmax(z_fg)) if np.any(~np.isnan(z_fg)) else 1.0
        if zmax <= 0:
            zmax = 1.0

    # --- Hover text matrix (covers all cells) ---
    text = np.empty((7, n_weeks), dtype=object)
    text[:] = ""
    for w, d, day_idx in zip(weeks, weekdays, per_day.index):
        nb = int(per_day.loc[day_idx, "nb"])
        date_str = day_idx.strftime("%d %b %Y")
        if nb == 0:
            text[d, w] = (
                f"<b>{date_str}</b><br><span style='color:#6b7280'>Aucun pari</span>"
            )
        else:
            text[d, w] = (
                f"<b>{date_str}</b><br>"
                f"Paris: <b>{nb}</b><br>"
                f"Mises: {fmt_eur(per_day.loc[day_idx, 'mises'])}<br>"
                f"Gains: <b>{fmt_eur(per_day.loc[day_idx, 'gains'], sign=True)}</b><br>"
                f"ROI: <b>{per_day.loc[day_idx, 'roi']:+.1f}%</b>"
            ).replace(",", " ")

    # --- Month ticks: center each month on its middle week ---
    months = [
        (start + pd.Timedelta(weeks=int(w))).to_period("M") for w in range(n_weeks)
    ]
    tick_vals, tick_text = [], []
    seen = {}
    for i, m in enumerate(months):
        seen.setdefault(m, []).append(i)
    month_fr = {
        1: "janv",
        2: "févr",
        3: "mars",
        4: "avr",
        5: "mai",
        6: "juin",
        7: "juil",
        8: "août",
        9: "sept",
        10: "oct",
        11: "nov",
        12: "déc",
    }
    for m, idxs in seen.items():
        if len(idxs) >= 2:  # skip half-visible months at the edges
            tick_vals.append(idxs[len(idxs) // 2])
            tick_text.append(month_fr[m.month])

    return {
        "z_bg": z_bg,
        "z_fg": z_fg,
        "text": text,
        "colorscale": colorscale,
        "zmin": zmin,
        "zmax": zmax,
        "zmid": zmid,
        "tick_vals": tick_vals,
        "tick_text": tick_text,
        "metric": metric,
        "unit": unit,
        "n_weeks": n_weeks,
        "days": int(days),
    }


def _render_heatmap_figure(payload: dict) -> None:
    z_bg = payload["z_bg"]
    z_fg = payload["z_fg"]
    text = payload["text"]
    colorscale = payload["colorscale"]
    zmin = payload["zmin"]
    zmax = payload["zmax"]
    zmid = payload["zmid"]
    tick_vals = payload["tick_vals"]
    tick_text = payload["tick_text"]
    metric = payload["metric"]
    unit = payload["unit"]
    days = payload.get("days", 0)

    fig = go.Figure()

    # Background grid: muted dark squares for every cell
    fig.add_trace(
        go.Heatmap(
            z=z_bg,
            colorscale=[[0, "#1f2530"], [1, "#1f2530"]],
            showscale=False,
            hoverinfo="skip",
            xgap=3,
            ygap=3,
            zmin=0,
            zmax=1,
        )
    )

    # Foreground: actual data
    fig.add_trace(
        go.Heatmap(
            z=z_fg,
            text=text,
            hoverinfo="text",
            hoverongaps=True,  # let hover work even on NaN cells
            colorscale=colorscale,
            zmin=zmin,
            zmax=zmax,
            zmid=zmid,
            xgap=3,
            ygap=3,
            showscale=True,
            colorbar=dict(
                title=dict(
                    text=f"{metric}{(' (' + unit + ')') if unit else ''}",
                    side="right",
                    font=dict(color="#9ca3af", size=11),
                ),
                thickness=8,
                len=0.85,
                outlinewidth=0,
                tickfont=dict(color="#9ca3af", size=10),
            ),
        )
    )

    # Hover layer over background to expose tooltips on inactive days
    fig.add_trace(
        go.Heatmap(
            z=np.where(np.isnan(z_fg), 0, np.nan),
            text=text,
            hoverinfo="text",
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            showscale=False,
            xgap=3,
            ygap=3,
        )
    )

    fig.update_layout(
        title=dict(
            text=f"📅 {metric} par jour"
            + (f" — {days} derniers jours" if days else ""),
            x=0.0,
            xanchor="left",
            font=dict(color="#e5e7eb", size=15, family="Inter, system-ui, sans-serif"),
        ),
        height=230,
        margin=dict(l=30, r=10, t=40, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickvals=tick_vals,
            ticktext=tick_text,
            showgrid=False,
            zeroline=False,
            showline=False,
            ticks="",
            tickfont=dict(color="#9ca3af", size=11),
            fixedrange=True,
        ),
        yaxis=dict(
            tickvals=[0, 2, 4],  # show only Lun / Mer / Ven
            ticktext=["Lun", "Mer", "Ven"],
            showgrid=False,
            zeroline=False,
            showline=False,
            ticks="",
            tickfont=dict(color="#9ca3af", size=11),
            autorange="reversed",
            scaleanchor="x",  # square cells
            scaleratio=1,
            fixedrange=True,
        ),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"calendar_heatmap_{metric}_{days}",
        config={"displayModeBar": False},
    )
