import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import plotly.graph_objects as go


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


def render_cumulative_chart(bets_data: pd.DataFrame) -> list:
    """Render cumulative gains line chart and return the selected points list (may be empty).

    Building traces separately and adding the margin trace first ensures the
    gains trace is on top and receives selection events. If the user selected
    a row in the grouped table, it will be stored in st.session_state["selected_from_table"]
    and we pre-select that point on the chart using the trace.selectedpoints property.
    """
    bets_data_reset = bets_data.reset_index(drop=True)
    bets_data_reset["Match_Num"] = range(len(bets_data_reset))

    # Ensure the cumulative margin column exists
    bets_data_reset["Cumulative_Marge"] = bets_data_reset["Marge attendue"].cumsum()

    # Build gains trace (with markers) using px for convenience, extract its trace
    gains_fig = px.line(
        bets_data_reset,
        x="Match_Num",
        y="Cumulative Gains",
        markers=True,
        labels={"Match_Num": "Match #", "Cumulative Gains": "Gains nets cumulés"},
    )
    gains_trace = gains_fig.data[0]
    gains_trace.update(
        name="Gains",
        line=dict(color="#32b296", width=2),
        marker=dict(size=1, color="#32b296"),
    )

    # If a table selection exists in session_state, mark that point as selected
    table_sel = st.session_state.get("selected_from_table")
    if table_sel is not None:
        try:
            if 0 <= int(table_sel) < len(bets_data_reset):
                gains_trace.update(selectedpoints=[int(table_sel)])
        except Exception:
            pass

    # Build margin trace (no markers, thin dashed white)
    marge_fig = px.line(
        bets_data_reset,
        x="Match_Num",
        y="Cumulative_Marge",
        labels={"Match_Num": "Match #", "Cumulative_Marge": "Attendu cumulé"},
    )
    marge_trace = marge_fig.data[0]
    marge_trace.update(
        name="Attendu",
        line=dict(color="#ffffff", width=1, dash="dash"),
        marker=dict(size=0),
        opacity=0.9,
    )

    # Assemble figure with margin first, gains last (so gains receives selection)
    fig = go.Figure()
    # ensure traces show in legend
    marge_trace.update(showlegend=True)
    gains_trace.update(showlegend=True)
    # add margin first so gains remains on top
    fig.add_trace(marge_trace)
    fig.add_trace(gains_trace)

    # Improve hover templates to include trace name and formatted value
    try:
        gains_trace.update(hovertemplate="%{y:.0f}€<extra>Gains</extra>")
        marge_trace.update(hovertemplate="%{y:.0f}€<extra>Attendu</extra>")
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

    # Optionally show legend title
    try:
        fig.update_layout(legend_title_text="Légende")
    except Exception:
        pass

    with st.container(border=True):
        event_dict = st.plotly_chart(
            fig,
            height=400,
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
            mise_formatted = f"{mise_val:,.0f}".replace(",", " ")
            item = f"<div style='display: flex; align-items: center; margin: 4px 8px;'><div style='width: 12px; height: 12px; background-color: {color}; border-radius: 3px; margin-right: 6px;'></div><span style='color: #d1d4dc; font-size: 12px; font-weight: 600;'>{category}: {mise_formatted}€ ({pct:.1f}%)</span></div>"
            legend_items_mise.append(item)

        # Assemble final HTML with both bars
        bar_html = f"""
        <div style='margin: 20px 0;'>
            <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px; font-weight: 600;'>{count_icon} {count_title}</div>
            <div style='display: flex; width: 100%; height: 30px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.3);'>
                {''.join(bar_segments_count)}
            </div>
            <div style='display: flex; justify-content: space-around; margin-top: 12px; flex-wrap: wrap;'>
                {''.join(legend_items_count)}
            </div>
        </div>
        
        <div style='margin: 20px 0;'>
            <div style='color: #9ca3af; font-size: 14px; margin-bottom: 8px; font-weight: 600;'>{mise_icon} {mise_title}</div>
            <div style='display: flex; width: 100%; height: 30px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.3);'>
                {''.join(bar_segments_mise)}
            </div>
            <div style='display: flex; justify-content: space-around; margin-top: 12px; flex-wrap: wrap;'>
                {''.join(legend_items_mise)}
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
