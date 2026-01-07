# ruff: noqa: E402
import hashlib
import streamlit as st
import os

os.chdir(st.session_state["project_path"])
import sys

sys.path.append(st.session_state["project_path"])
from db_utils.db_utils import read_sql_query

BDD = "FootNet"


def check_usr_pass(username: str, password: str) -> bool:
    """
    Authenticates the username and password.
    """
    query_user = f"""SELECT ID_USER,username,password_st FROM {BDD}.Users"""
    user_data = read_sql_query(BDD, query_user)
    if (
        username in user_data["username"].values
        and hashlib.md5(password.encode()).hexdigest()
        in user_data["password_st"].values
    ):
        print("User authenticated successfully.")
        return True, user_data[user_data["username"] == username]["ID_USER"].values[0]
    return False, None
