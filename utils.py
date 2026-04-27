import base64
import streamlit as st


def fmt_num(value, decimals: int = 0, sign: bool = False) -> str:
    """Format a number with non-breaking thin space as thousands separator.

    Returns "—" for None / NaN. Uses U+202F (NARROW NO-BREAK SPACE) so the
    grouping never wraps and renders cleanly in HTML.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v != v:  # NaN check
        return "—"
    spec = f"{'+' if sign else ''},.{decimals}f"
    return format(v, spec).replace(",", "\u202f")


def fmt_eur(value, decimals: int = 0, sign: bool = False) -> str:
    return f"{fmt_num(value, decimals=decimals, sign=sign)}€"


def fmt_unit(value, decimals: int = 1, sign: bool = False) -> str:
    return f"{fmt_num(value, decimals=decimals, sign=sign)} u"


def fmt_money(
    value, unit_mode: bool = False, decimals: int | None = None, sign: bool = False
) -> str:
    if unit_mode:
        return fmt_unit(value, decimals=1 if decimals is None else decimals, sign=sign)
    return fmt_eur(value, decimals=0 if decimals is None else decimals, sign=sign)


# Place the logo as the last element in the sidebar and push it to the very bottom (centered)
def _sidebar_logo_bottom_center(
    path: str = "logo_TeNNet.png", width: int = 100, padding_bottom: int = 0
):
    st.markdown(
        "<style>"
        "section[data-testid='stSidebar'] > div:first-child{display:flex;flex-direction:column;height:100vh !important;}"
        "section[data-testid='stSidebar'] .tnp-logo{margin-top:auto;display:flex;justify-content:center;padding-bottom:"
        + str(padding_bottom)
        + "px;width:100%;}"
        "section[data-testid='stSidebar'] .tnp-logo img{display:block;margin:0;padding:0;}"
        "</style>",
        unsafe_allow_html=True,
    )
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        html = f"<div class='tnp-logo'><img src='data:image/png;base64,{b64}' width='{width}'/></div>"
        # append as last element in sidebar so CSS pushes it to bottom
        st.sidebar.markdown(html, unsafe_allow_html=True)
    except Exception:
        # fallback: add spacer then image
        st.sidebar.markdown("<div style='height:70vh;'></div>", unsafe_allow_html=True)
        st.sidebar.image(path, width=width)


# ---------------------------------------------------------------------------
# Centralized mappings (used in data preparation and UI rendering)
# ---------------------------------------------------------------------------
SURFACE_MAP = {
    "Hard": "Dur",
    "Grass": "Gazon",
    "Clay": "Terre battue",
}

LEVEL_MAP = {
    "C": "Challenger",
    "A": "ATP 250/500",
    "G": "Grand Chelem",
    "M": "Masters 1000",
    "I": "WTA 250",
    "P": "WTA 500",
    "PM": "WTA 1000",
}

ROUND_MAP = {
    "F": "Finale",
    "SF": "Demi-finale",
    "QF": "Quart de finale",
    "R16": "8emes de finale",
    "R32": "16emes de finale",
    "R64": "32emes de finale",
    "R128": "64emes de finale",
    "RR": "Round Robin",
}

SURFACE_COLORS = {
    "Dur": "#3772d1",
    "Terre battue": "#b45715",
    "Gazon": "#22c55e",
    "Carpet": "#8b5cf6",
    "Indoor Hard": "#6366f1",
}

COMPET_COLORS = {
    "atp": "#10b981",
    "wta": "#ec4899",
    "doubles": "#8b5cf6",
    "challenger": "#6366f1",
}


def cote_bucket(c) -> str | None:
    """Bucketize a cote (decimal odd) into a coarse band, or return None for NaN."""
    try:
        v = float(c)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    if v < 1.5:
        return "<1.5"
    if v < 2.0:
        return "1.5-2.0"
    if v < 2.5:
        return "2.0-2.5"
    if v < 3.0:
        return "2.5-3.0"
    if v < 5.0:
        return "3.0-5.0"
    return ">=5.0"


def to_csv_bytes(df) -> bytes:
    """Serialize a DataFrame to UTF-8 CSV bytes (BOM-prefixed for Excel compatibility)."""
    try:
        import pandas as pd  # noqa: F401

        return ("\ufeff" + df.to_csv(index=False)).encode("utf-8")
    except Exception:
        return b""


def csv_download_button(
    df,
    label: str = "📥 Exporter CSV",
    filename: str = "export.csv",
    key: str | None = None,
):
    """Render a Streamlit download button for a DataFrame."""
    try:
        if df is None or len(df) == 0:
            return
        st.download_button(
            label=label,
            data=to_csv_bytes(df),
            file_name=filename,
            mime="text/csv",
            key=key,
            use_container_width=False,
        )
    except Exception:
        pass
