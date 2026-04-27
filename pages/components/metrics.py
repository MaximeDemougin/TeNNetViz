import streamlit as st
import pandas as pd
import numpy as np

from utils import fmt_num, fmt_eur, fmt_money


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sparkline_svg(
    values,
    color: str = "#32b296",
    width: int = 140,
    height: int = 36,
    fill: bool = True,
    expected_values=None,
    expected_color: str = "#3b82f6",
    show_markers: bool = False,
    diverging_fill: bool = False,
    reference_line: float | None = None,
    tooltips: list | None = None,
) -> str:
    """Return an inline SVG sparkline for the given numeric series.

    Optional overlays:
      * `expected_values`  dashed second line (e.g. expected vs realised)
      * `show_markers`     highlight peak (max) and trough (min) of the main series
      * `diverging_fill`   split fill in green above zero / red below zero
      * `reference_line`   draw a dashed horizontal line at this y-value (e.g. 0)
    Empty / single-point series produce a tiny placeholder.
    """
    arr = np.asarray(list(values), dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size < 2:
        return (
            f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
            f"<line x1='0' y1='{height/2:.1f}' x2='{width}' y2='{height/2:.1f}' "
            f"stroke='#374151' stroke-width='1' stroke-dasharray='2,3'/></svg>"
        )

    # Combine series for a shared y-range so both lines are comparable.
    all_vals = arr.copy()
    exp_arr = None
    if expected_values is not None:
        exp_arr = np.asarray(list(expected_values), dtype=float)
        exp_arr = exp_arr[~np.isnan(exp_arr)]
        if exp_arr.size >= 2:
            all_vals = np.concatenate([all_vals, exp_arr])
        else:
            exp_arr = None

    vmin, vmax = float(np.min(all_vals)), float(np.max(all_vals))
    # Always include zero in range when diverging_fill or reference_line=0
    if diverging_fill or reference_line == 0:
        vmin = min(vmin, 0.0)
        vmax = max(vmax, 0.0)
    if vmax - vmin < 1e-9:
        vmin -= 0.5
        vmax += 0.5
    pad = 2  # vertical padding
    h = height - 2 * pad

    def _y(v: float) -> float:
        return pad + (vmax - v) / (vmax - vmin) * h

    def _to_path(values_arr: np.ndarray) -> str:
        n = values_arr.size
        xs = np.linspace(0, width, n)
        ys = pad + (vmax - values_arr) / (vmax - vmin) * h
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))

    pts = _to_path(arr)
    n = arr.size
    xs = np.linspace(0, width, n)
    ys = np.array([_y(v) for v in arr])
    last_y = ys[-1]
    last_x = float(xs[-1])

    # Reference / zero line
    ref_line = ""
    ref_y = None
    if reference_line is not None and vmin <= reference_line <= vmax:
        ref_y = _y(float(reference_line))
    elif vmin < 0 < vmax:
        ref_y = _y(0.0)
    if ref_y is not None:
        ref_line = (
            f"<line x1='0' y1='{ref_y:.1f}' x2='{width}' y2='{ref_y:.1f}' "
            f"stroke='#4b5563' stroke-width='0.5' stroke-dasharray='2,2'/>"
        )

    # Fill area below the main curve (or diverging vs zero baseline)
    fill_path = ""
    if fill:
        if diverging_fill and vmin < 0 < vmax:
            zero_y = _y(0.0)
            # Green clip above zero, red clip below — use two separate areas
            # clipped at the zero line via SVG <clipPath>.
            uid = f"sp{abs(hash(tuple(arr.tolist()))) % 10**8}"
            area = (
                f"M0,{zero_y:.1f} L"
                + pts.replace(" ", " L")
                + f" L{width},{zero_y:.1f} Z"
            )
            fill_path = (
                f"<defs>"
                f"<clipPath id='clipPos{uid}'>"
                f"<rect x='0' y='0' width='{width}' height='{zero_y:.1f}'/></clipPath>"
                f"<clipPath id='clipNeg{uid}'>"
                f"<rect x='0' y='{zero_y:.1f}' width='{width}' "
                f"height='{height - zero_y:.1f}'/></clipPath>"
                f"</defs>"
                f"<path d='{area}' fill='#32b296' fill-opacity='0.18' "
                f"clip-path='url(#clipPos{uid})'/>"
                f"<path d='{area}' fill='#e04e4e' fill-opacity='0.18' "
                f"clip-path='url(#clipNeg{uid})'/>"
            )
        else:
            area = f"M0,{height} L" + pts.replace(" ", " L") + f" L{width},{height} Z"
            fill_path = (
                f"<path d='{area}' fill='{color}' fill-opacity='0.12' stroke='none'/>"
            )

    expected_path = ""
    if exp_arr is not None:
        ep = _to_path(exp_arr)
        expected_path = (
            f"<polyline fill='none' stroke='{expected_color}' stroke-width='1.2' "
            f"stroke-dasharray='3,2' stroke-opacity='0.85' points='{ep}'/>"
        )

    markers = ""
    if show_markers and n >= 3:
        i_max = int(np.argmax(arr))
        i_min = int(np.argmin(arr))
        if i_max not in (0, n - 1):
            markers += (
                f"<circle cx='{xs[i_max]:.1f}' cy='{ys[i_max]:.1f}' r='2' "
                f"fill='#22c55e' stroke='#0b1220' stroke-width='0.6'/>"
            )
        if i_min not in (0, n - 1) and i_min != i_max:
            markers += (
                f"<circle cx='{xs[i_min]:.1f}' cy='{ys[i_min]:.1f}' r='2' "
                f"fill='#ef4444' stroke='#0b1220' stroke-width='0.6'/>"
            )

    # Invisible HTML hover hit-areas with native HTML title= tooltips per point
    hover_html = ""
    if tooltips:
        tt = list(tooltips)
        if len(tt) >= n:
            tt = tt[-n:]
        else:
            tt = [""] * (n - len(tt)) + tt
        cell_w_pct = 100.0 / n
        cells = []
        for i in range(n):
            label = str(tt[i])
            if not label:
                continue
            esc = (
                label.replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            left_pct = i * cell_w_pct
            cells.append(
                f'<div title="{esc}" style=\'position:absolute; '
                f"left:{left_pct:.3f}%; top:0; width:{cell_w_pct:.3f}%; "
                f"height:100%; cursor:default;'></div>"
            )
        hover_html = "".join(cells)

    svg = (
        f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' "
        f"style='display:block;'>"
        f"{ref_line}"
        f"{fill_path}"
        f"{expected_path}"
        f"<polyline fill='none' stroke='{color}' stroke-width='1.6' points='{pts}'/>"
        f"{markers}"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='2.2' fill='{color}'/>"
        f"</svg>"
    )
    if hover_html:
        return (
            f"<div style='position:relative; width:{width}px; height:{height}px;'>"
            f"{svg}"
            f"<div style='position:absolute; inset:0;'>{hover_html}</div>"
            f"</div>"
        )
    return svg


def _sparkbars_svg(
    values,
    color: str = "#32b296",
    neg_color: str | None = None,
    width: int = 140,
    height: int = 36,
    tooltips: list | None = None,
) -> str:
    """Return an HTML bar sparkline. Negative bars use `neg_color` if given.

    Uses pure HTML divs (not SVG) so each bar gets a native HTML ``title``
    attribute tooltip on hover (immediate, no sanitizer issues).
    """
    arr = np.asarray(list(values), dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return (
            f"<div style='width:{width}px; height:{height}px; "
            f"border-bottom:1px dashed #374151;'></div>"
        )
    vmin = float(np.min(arr)) if neg_color else 0.0
    vmax = float(np.max(arr))
    vmin = min(vmin, 0.0)
    if vmax - vmin < 1e-9:
        vmax = vmin + 1.0
    n = arr.size
    h = height
    # Zero baseline position from top (px), used to split positive / negative
    zero_top = (vmax - 0.0) / (vmax - vmin) * h
    pos_h = zero_top  # available height for positive bars
    neg_h = h - zero_top  # available height for negative bars
    tt_list = list(tooltips) if tooltips else None

    bars_html = []
    for i, v in enumerate(arr):
        if v >= 0:
            bh = (v / vmax * pos_h) if vmax > 0 else 0
            bh = max(1.0, bh)
            top = pos_h - bh
            c = color
        else:
            bh = (abs(v) / abs(vmin) * neg_h) if vmin < 0 else 0
            bh = max(1.0, bh)
            top = pos_h
            c = neg_color if neg_color is not None else color
        title_attr = ""
        if tt_list and i < len(tt_list):
            esc = (
                str(tt_list[i])
                .replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            title_attr = f' title="{esc}"'
        # Outer cell takes full column width so hover hit-area is generous
        bars_html.append(
            f"<div{title_attr} style='flex:1; height:{h}px; position:relative; "
            f"display:flex; align-items:flex-end; cursor:default;'>"
            f"<div style='position:absolute; left:10%; right:10%; "
            f"top:{top:.2f}px; height:{bh:.2f}px; background:{c}; "
            f"opacity:0.88; border-radius:1px;'></div>"
            f"</div>"
        )
    baseline_css = ""
    if neg_color is not None and vmin < 0:
        baseline_css = (
            f"<div style='position:absolute; left:0; right:0; top:{zero_top:.1f}px; "
            f"height:1px; background:#4b5563; opacity:0.6; "
            f"border-top:1px dashed #4b5563; pointer-events:none;'></div>"
        )
    return (
        f"<div style='width:{width}px; height:{h}px; position:relative;'>"
        f"<div style='display:flex; gap:1px; width:100%; height:100%; "
        f"align-items:stretch;'>{''.join(bars_html)}</div>"
        f"{baseline_css}"
        f"</div>"
    )


def _delta_badge(
    current: float,
    previous: float,
    suffix: str = "",
    as_pct: bool = False,
    label: str = "évolution",
) -> str:
    """Render a coloured delta pill comparing current to previous period."""
    if previous is None or (
        isinstance(previous, float) and (np.isnan(previous) or previous == 0)
    ):
        if current == 0 or previous == 0:
            return "<span style='color:#6b7280; font-size:11px;'>—</span>"
    if as_pct:
        delta = current - previous
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "·")
        color = "#32b296" if delta > 0 else ("#e04e4e" if delta < 0 else "#9ca3af")
        tip = (
            f"{label} (30j vs 30j précédents)&#10;"
            f"Avant: {previous:+.1f}{suffix}&#10;"
            f"Après: {current:+.1f}{suffix}&#10;"
            f"Δ: {delta:+.1f}{suffix}"
        )
        return (
            f'<span title="{tip}" style=\'color:{color}; font-size:11px; '
            f"font-weight:600; cursor:help;'>{arrow} {delta:+.1f}{suffix}</span>"
        )
    # Relative % change
    if previous == 0:
        return "<span style='color:#6b7280; font-size:11px;'>nouveau</span>"
    pct = (current - previous) / abs(previous) * 100
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "·")
    color = "#32b296" if pct > 0 else ("#e04e4e" if pct < 0 else "#9ca3af")

    # Format raw values for tooltip
    def _fmt_raw(v):
        if abs(v) >= 1000:
            return f"{v:,.0f}".replace(",", "\u202f")
        return f"{v:,.2f}".replace(",", "\u202f")

    tip = (
        f"{label} (30j vs 30j précédents)&#10;"
        f"Avant: {_fmt_raw(previous)}&#10;"
        f"Après: {_fmt_raw(current)}&#10;"
        f"Δ: {pct:+.1f}%"
    )
    return (
        f'<span title="{tip}" style=\'color:{color}; font-size:11px; '
        f"font-weight:600; cursor:help;'>{arrow} {pct:+.1f}%</span>"
    )


def _split_periods(bets_data: pd.DataFrame, days: int = 30):
    """Split bets in two consecutive windows of `days` ending at last bet date.

    Returns (previous_window_df, current_window_df) where:
      * current_window: bets in the last `days` (relative to max date)
      * previous_window: bets in the `days` immediately before that
    Returns (None, None) if data is insufficient.
    """
    if bets_data is None or bets_data.empty or "Date" not in bets_data.columns:
        return None, None
    df = bets_data.copy()
    try:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    except Exception:
        return None, None
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if df.empty:
        return None, None
    end = df["Date"].max().normalize() + pd.Timedelta(days=1)
    curr_start = end - pd.Timedelta(days=days)
    prev_start = curr_start - pd.Timedelta(days=days)
    curr = df[(df["Date"] >= curr_start) & (df["Date"] < end)]
    prev = df[(df["Date"] >= prev_start) & (df["Date"] < curr_start)]
    if curr.empty and prev.empty:
        return None, None
    return prev, curr


def _agg(df: pd.DataFrame, unit_mode: bool) -> dict:
    """Aggregate the metrics block for either € or unit mode."""
    if df is None or df.empty:
        return {
            "bets": 0,
            "mises": 0.0,
            "gains": 0.0,
            "marges": 0.0,
            "roi": 0.0,
            "wins": 0,
        }
    bets = len(df)
    if unit_mode:
        mises = float(bets)
        m = df["Mise"].replace(0, float("nan"))
        gains = float((df["Gains net"] / m).sum(skipna=True))
        marges = float((df["Marge attendue"] / m).sum(skipna=True))
    else:
        mises = float(df["Mise"].sum())
        gains = float(df["Gains net"].sum())
        marges = float(df["Marge attendue"].sum())
    roi = (gains / mises * 100) if mises > 0 else 0.0
    wins = int((df["Gains net"] > 0).sum())
    return {
        "bets": bets,
        "mises": mises,
        "gains": gains,
        "marges": marges,
        "roi": roi,
        "wins": wins,
    }


def _running_series(bets_data: pd.DataFrame, unit_mode: bool):
    """Return cumulative series for sparklines (one value per bet, chronological)."""
    if bets_data is None or bets_data.empty:
        return None
    df = bets_data.copy()
    try:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    except Exception:
        pass
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if df.empty:
        return None
    if unit_mode:
        m = df["Mise"].replace(0, float("nan"))
        gains_step = (df["Gains net"] / m).fillna(0)
        marges_step = (df["Marge attendue"] / m).fillna(0)
        mises_step = pd.Series(1.0, index=df.index)
    else:
        gains_step = df["Gains net"].fillna(0)
        marges_step = df["Marge attendue"].fillna(0)
        mises_step = df["Mise"].fillna(0)
    return {
        "cum_gains": gains_step.cumsum().to_numpy(),
        "cum_marges": marges_step.cumsum().to_numpy(),
        "cum_mises": mises_step.cumsum().to_numpy(),
        "cum_count": np.arange(1, len(df) + 1, dtype=float),
        "cum_roi": np.where(
            mises_step.cumsum().to_numpy() > 0,
            gains_step.cumsum().to_numpy()
            / np.maximum(mises_step.cumsum().to_numpy(), 1e-9)
            * 100,
            0.0,
        ),
    }


def _bucket_series(
    bets_data: pd.DataFrame, n_buckets: int = 14, unit_mode: bool = False
) -> dict | None:
    """Return per-week aggregates suitable for bar sparklines.

    Buckets bets by ISO calendar week (Monday-anchored). Empty weeks within
    the active span are kept (zero bars) so quiet periods show as gaps.
    `n_buckets` caps the number of most-recent weeks shown.
    """
    if bets_data is None or bets_data.empty:
        return None
    df = bets_data.copy()
    try:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    except Exception:
        pass
    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    if df.empty:
        return None

    # Anchor each bet to the Monday of its week
    week_start = df["Date"].dt.to_period("W-SUN").dt.start_time
    df = df.assign(_week=week_start)

    t0 = df["_week"].min()
    t1 = df["_week"].max()
    all_weeks = pd.date_range(start=t0, end=t1, freq="W-MON")
    if len(all_weeks) == 0 or all_weeks[0] != t0:
        # Ensure we start exactly at the first observed week
        all_weeks = pd.DatetimeIndex([t0]).append(all_weeks[all_weeks > t0])

    # Cap to last n_buckets weeks
    if n_buckets and len(all_weeks) > n_buckets:
        all_weeks = all_weeks[-n_buckets:]

    counts, mises, gains, marges, labels = [], [], [], [], []
    grouped = dict(tuple(df.groupby("_week")))
    for wk in all_weeks:
        chunk = grouped.get(wk, df.iloc[0:0])
        wk_end = wk + pd.Timedelta(days=6)
        try:
            labels.append(
                f"Sem. {pd.Timestamp(wk).strftime('%d %b')} \u2192 "
                f"{pd.Timestamp(wk_end).strftime('%d %b %Y')}"
            )
        except Exception:
            labels.append("")
        counts.append(len(chunk))
        if chunk.empty:
            mises.append(0.0)
            gains.append(0.0)
            marges.append(0.0)
            continue
        if unit_mode:
            m = chunk["Mise"].replace(0, float("nan"))
            mises.append(float(len(chunk)))
            gains.append(float((chunk["Gains net"] / m).sum(skipna=True)))
            marges.append(float((chunk["Marge attendue"] / m).sum(skipna=True)))
        else:
            mises.append(float(chunk["Mise"].sum()))
            gains.append(float(chunk["Gains net"].sum()))
            marges.append(float(chunk["Marge attendue"].sum()))
    return {
        "counts": counts,
        "mises": mises,
        "gains": gains,
        "marges": marges,
        "labels": labels,
    }


def _rolling_roi_attendu(bets_data: pd.DataFrame, window: int = 30) -> tuple | None:
    """Rolling expected ROI (%) over the last `window` bets, chronological.

    Returns (values, dates) where values is a numpy array of ROI % and dates is
    a list of pandas Timestamps (one per value). Returns None if not enough data.
    """
    if bets_data is None or bets_data.empty:
        return None
    df = bets_data.copy()
    try:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    except Exception:
        pass
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if len(df) < 3:
        return None
    w = max(3, min(window, len(df)))
    marges = df["Marge attendue"].fillna(0)
    mises = df["Mise"].fillna(0)
    rm = marges.rolling(window=w, min_periods=max(3, w // 3)).sum()
    rs = mises.rolling(window=w, min_periods=max(3, w // 3)).sum()
    out = np.where(rs > 0, rm / rs * 100.0, np.nan)
    return out, list(df["Date"])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def render_metrics(bets_data: pd.DataFrame, unit_mode: bool = False) -> dict:
    """Calculate statistics and render the four metric cards.

    Each card now includes:
      • a tiny inline SVG sparkline showing the cumulative trend,
      • a delta badge comparing the most recent half vs the previous half,
      • for Gains nets, a dashed overlay of the *expected* trajectory.

    Returns a dict with the calculated totals for downstream use.
    """
    cur = _agg(bets_data, unit_mode)
    prev_df, curr_df = _split_periods(bets_data)
    prev = _agg(prev_df, unit_mode) if prev_df is not None else None
    curr = _agg(curr_df, unit_mode) if curr_df is not None else None

    series = _running_series(bets_data, unit_mode)
    buckets = _bucket_series(bets_data, n_buckets=14, unit_mode=unit_mode)
    rolling_roi_exp = _rolling_roi_attendu(bets_data, window=30)

    # Build tooltip labels per bucket (used for hover on bar sparklines)
    bucket_count_tt: list = []
    bucket_mises_tt: list = []
    bucket_gains_tt: list = []
    bucket_marges_tt: list = []
    if buckets:
        labels = buckets.get("labels", [""] * len(buckets["counts"]))
        for i, lbl in enumerate(labels):
            c = buckets["counts"][i]
            m = buckets["mises"][i]
            g = buckets["gains"][i]
            mg = buckets["marges"][i]
            bucket_count_tt.append(f"{lbl}\n{fmt_num(c)} pari{'s' if c != 1 else ''}")
            bucket_mises_tt.append(f"{lbl}\nMises: {fmt_money(m, unit_mode=unit_mode)}")
            bucket_gains_tt.append(
                f"{lbl}\nGains: {fmt_money(g, unit_mode=unit_mode, sign=True)}"
            )
            bucket_marges_tt.append(
                f"{lbl}\nGains attendus: {fmt_money(mg, unit_mode=unit_mode, sign=True)}"
            )

    # Backwards-compatible naming used downstream
    total_bets = cur["bets"]
    total_mises = cur["mises"]
    total_gains = cur["gains"]
    total_marges = cur["marges"]
    wins = cur["wins"]
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    roi = cur["roi"]
    marge_percentage = (total_marges / total_mises * 100) if total_mises > 0 else 0

    # Common card style (centralised)
    card_base = (
        "padding:14px 16px; border-radius:12px; "
        "background:linear-gradient(180deg, rgba(30,33,40,0.85), rgba(20,22,28,0.85)); "
        "box-shadow:0 1px 2px rgba(0,0,0,0.25);"
    )

    col1, col2, col3, col4 = st.columns(4)

    # --- Card 1: Total paris -------------------------------------------------
    with col1:
        # Bars = paris par bucket (cadence d'activité dans le temps)
        spark = (
            _sparkbars_svg(buckets["counts"], color="#32b296", tooltips=bucket_count_tt)
            if buckets
            else _sparkline_svg([], "#32b296")
        )
        delta = (
            _delta_badge(curr["bets"], prev["bets"], label="Nb paris")
            if prev and curr
            else "—"
        )
        total_bets_fmt = fmt_num(total_bets)
        wins_fmt = fmt_num(wins)
        wr_fmt = f"{win_rate:.0f}%"
        wr_tip = (
            f"Taux de victoire&#10;{fmt_num(wins)} gagn\u00e9s sur "
            f"{fmt_num(total_bets)} paris&#10;= {win_rate:.2f}%"
        )
        st.markdown(
            f"""
        <div class='metric-card card-green' style='border: 1px solid rgba(50,178,150,0.2); {card_base}'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <div style='color:#9ca3af; font-size:13px;'>📝 Total Paris</div>
                {delta}
            </div>
            <div style='font-size:30px; font-weight:700; color:#32b296; line-height:1.1; margin-top:4px;'>{total_bets_fmt}</div>
            <div style='display:flex; justify-content:space-between; align-items:flex-end; margin-top:6px;'>
                <div style='color:#9ca3af; font-size:11px;'>{wins_fmt} gagnés · <span title="{wr_tip}" style='cursor:help; border-bottom:1px dotted #6b7280;'>{wr_fmt}</span></div>
                <div>{spark}</div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # --- Card 2: Mises totales ----------------------------------------------
    with col2:
        if unit_mode:
            mises_formatted = fmt_money(total_mises, unit_mode=True, decimals=0)
            mises_subtitle = "unités engagées"
        else:
            mises_formatted = fmt_eur(total_mises)
            mises_subtitle = "Total misé"
        avg_stake = (total_mises / total_bets) if total_bets > 0 else 0
        avg_fmt = fmt_money(avg_stake, unit_mode=unit_mode, decimals=1)
        # Bars = mise par bucket (montre les variations de stake dans le temps)
        spark = (
            _sparkbars_svg(buckets["mises"], color="#fbbf24", tooltips=bucket_mises_tt)
            if buckets
            else _sparkline_svg([], "#fbbf24")
        )
        delta = (
            _delta_badge(curr["mises"], prev["mises"], label="Mises")
            if prev and curr
            else "—"
        )
        st.markdown(
            f"""
        <div class='metric-card card-yellow' style='border: 1px solid rgba(251,191,36,0.2); {card_base}'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <div style='color:#9ca3af; font-size:13px;'>💰 Mises totales</div>
                {delta}
            </div>
            <div style='font-size:30px; font-weight:700; color:#fbbf24; line-height:1.1; margin-top:4px;'>{mises_formatted}</div>
            <div style='display:flex; justify-content:space-between; align-items:flex-end; margin-top:6px;'>
                <div style='color:#9ca3af; font-size:11px;'>{mises_subtitle} · ⌀ {avg_fmt}</div>
                <div>{spark}</div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # --- Card 3: Gains nets (with expected overlay) -------------------------
    with col3:
        gains_value = total_gains
        if unit_mode:
            gains_formatted = fmt_money(
                total_gains, unit_mode=True, decimals=2, sign=True
            )
        else:
            gains_formatted = fmt_eur(total_gains, sign=True)
        roi_formatted = f"{roi:+.1f}%"
        gain_color = "#32b296" if gains_value >= 0 else "#e04e4e"
        gain_card_class = (
            "card-gains-positive" if gains_value >= 0 else "card-gains-negative"
        )
        border_color = (
            "rgba(50,178,150,0.2)" if gains_value >= 0 else "rgba(224,78,78,0.2)"
        )
        # Expected gains delta vs actual ⇒ over/underperformance
        diff_vs_exp = total_gains - total_marges
        diff_color = "#32b296" if diff_vs_exp >= 0 else "#e04e4e"
        diff_label = "vs attendu"
        diff_str = fmt_money(diff_vs_exp, unit_mode=unit_mode, sign=True)
        spark = (
            _sparkbars_svg(
                buckets["gains"],
                color="#32b296",
                neg_color="#e04e4e",
                tooltips=bucket_gains_tt,
            )
            if buckets
            else _sparkline_svg([], gain_color)
        )
        # Delta vs previous half — show absolute change (already in € or u)
        delta = (
            _delta_badge(curr["gains"], prev["gains"], label="Gains nets")
            if prev and curr
            else "—"
        )
        roi_tip = (
            f"Return On Investment&#10;Gains nets / Mises totales&#10;"
            f"= {fmt_money(total_gains, unit_mode=unit_mode, sign=True)} / "
            f"{fmt_money(total_mises, unit_mode=unit_mode)}&#10;= {roi:+.2f}%"
        )
        diff_tip = (
            f"Performance r\u00e9elle vs attendue&#10;"
            f"R\u00e9el: {fmt_money(total_gains, unit_mode=unit_mode, sign=True)}&#10;"
            f"Attendu: {fmt_money(total_marges, unit_mode=unit_mode, sign=True)}&#10;"
            f"\u0394: {diff_str}"
        )
        st.markdown(
            f"""
        <div class='metric-card {gain_card_class}' style='border: 1px solid {border_color}; {card_base}'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <div style='color:#9ca3af; font-size:13px;'>💸 Gains nets</div>
                {delta}
            </div>
            <div style='font-size:30px; font-weight:700; color:{gain_color}; line-height:1.1; margin-top:4px;'>{gains_formatted}</div>
            <div style='display:flex; justify-content:space-between; align-items:flex-end; margin-top:6px;'>
                <div style='color:#9ca3af; font-size:11px;'>
                    ROI: <b title="{roi_tip}" style='color:{gain_color}; cursor:help; border-bottom:1px dotted {gain_color};'>{roi_formatted}</b>
                    · <span title="{diff_tip}" style='color:{diff_color}; cursor:help; border-bottom:1px dotted {diff_color};'>{diff_str}</span>
                    <span style='color:#6b7280;'> {diff_label}</span>
                </div>
                <div>{spark}</div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # --- Card 4: Gains attendus ---------------------------------------------
    with col4:
        if unit_mode:
            total_marges_fmt = fmt_money(
                total_marges, unit_mode=True, decimals=2, sign=True
            )
        else:
            total_marges_fmt = fmt_eur(total_marges, sign=True)
        marge_pct_fmt = f"{marge_percentage:+.1f}%"
        marge_color = "#3b82f6" if total_marges > 0 else "#e04e4e"
        # Bars = gains attendus par semaine (fill divergent bleu/rouge)
        spark = (
            _sparkbars_svg(
                buckets["marges"],
                color="#3b82f6",
                neg_color="#e04e4e",
                tooltips=bucket_marges_tt,
            )
            if buckets
            else _sparkline_svg([], marge_color)
        )
        delta = (
            _delta_badge(curr["marges"], prev["marges"], label="Gains attendus")
            if prev and curr
            else "—"
        )
        marge_pct_tip = (
            f"Edge attendu&#10;Marge attendue / Mises&#10;"
            f"= {fmt_money(total_marges, unit_mode=unit_mode, sign=True)} / "
            f"{fmt_money(total_mises, unit_mode=unit_mode)}&#10;= {marge_percentage:+.2f}%"
        )
        st.markdown(
            f"""
        <div class='metric-card card-blue' style='border: 1px solid rgba(59,130,246,0.2); {card_base}'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <div style='color:#9ca3af; font-size:13px;'>📈 Gains attendus</div>
                {delta}
            </div>
            <div style='font-size:30px; font-weight:700; color:{marge_color}; line-height:1.1; margin-top:4px;'>{total_marges_fmt}</div>
            <div style='display:flex; justify-content:space-between; align-items:flex-end; margin-top:6px;'>
                <div style='color:#9ca3af; font-size:11px;'><span title="{marge_pct_tip}" style='cursor:help; border-bottom:1px dotted #6b7280;'>{marge_pct_fmt}</span> des mises</div>
                <div>{spark}</div>
            </div>
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
