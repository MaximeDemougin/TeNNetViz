# ruff: noqa: E402
import streamlit as st
import os
import re


os.chdir(st.session_state["project_path"])
import sys

sys.path.append(st.session_state["project_path"])
from login_ui.utils import check_usr_pass

from pathlib import Path
import base64

logo_path = Path(st.session_state["project_path"]) / "logo_TeNNet.png"
logo_base64 = base64.b64encode(logo_path.read_bytes()).decode()


st.set_page_config(
    layout="centered", page_icon="logo_TeNNet.png", page_title="Login - TeNNet"
)
st.markdown("## Login to  TeNNet", text_alignment="center")
st.markdown("###", text_alignment="center")
del_login = st.empty()
with del_login.form("Login Form", width="stretch", border=False):
    col1, colu2, col3 = st.columns([1, 5, 1])
    with colu2:
        username = st.text_input(
            "Username", placeholder="Username", label_visibility="collapsed"
        )
        password = st.text_input(
            "Password",
            placeholder="Password",
            type="password",
            label_visibility="collapsed",
        )
    # st.markdown("######")
    # st.html(""" <br> """)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        login_submit_button = st.form_submit_button(
            label="Login", type="primary", width="stretch"
        )

    if login_submit_button:
        authenticate_user_check, id_user = check_usr_pass(username, password)

        if not authenticate_user_check:
            with colu2:
                st.error("Invalid Username or Password!")

        else:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["ID_USER"] = id_user
            st.session_state["bankroll"] = None
            # self.cookies["__streamlit_login_signup_ui_username__"] = (
            #     username
            # )
            # self.cookies.save()
            # del_login.empty()
            with colu2:
                st.success("Logged In Successfully!")
            st.rerun()
        # add logo
        # st.markdown("##", text_alignment="center")

    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown(
            """
                    <style>
                    section.main > div {
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                    }

                    .logo {
                        margin-bottom: 1.5rem;

                    }

                    @media (max-width: 768px) {
                        .logo img {
                            width: 200px;
                            margin: 0 auto;
                            display: block;
                        }
                    }
                    </style>
                    """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
                <div class="logo">
                    <img src="data:image/png;base64,{logo_base64}" width="260">
                </div>
                """,
            unsafe_allow_html=True,
        )
