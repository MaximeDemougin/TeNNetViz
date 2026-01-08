import streamlit as st
import plotly.express as px
import pandas as pd
import plotly.graph_objects as go


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
