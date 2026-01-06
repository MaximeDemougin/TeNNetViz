import base64
import streamlit as st


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
