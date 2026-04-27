# ruff: noqa: E402
import hashlib
import hmac
import logging
import streamlit as st
import os

os.chdir(st.session_state["project_path"])
import sys

sys.path.append(st.session_state["project_path"])
from db_utils.db_utils import read_sql_query
from config import BDD_USERS as BDD

logger = logging.getLogger(__name__)


def _is_valid_username(username: str) -> bool:
    if not isinstance(username, str):
        return False
    u = username.strip()
    return 1 <= len(u) <= 64


def check_usr_pass(username: str, password: str):
    """Authenticate a username / password pair.

    Returns ``(True, ID_USER)`` on success, ``(False, None)`` otherwise.

    SECURITY NOTES
    --------------
    - Uses a parameterized query (no SQL injection).
    - Uses ``hmac.compare_digest`` for constant-time comparison.
    - Passwords are still stored as MD5 hashes in the legacy schema.
      MD5 is cryptographically broken; migrate to argon2/bcrypt as soon as
      a schema change is acceptable (add ``password_algo`` column, re-hash
      on next successful login).
    """
    if not _is_valid_username(username) or not isinstance(password, str):
        return False, None

    query_user = (
        "SELECT ID_USER, username, password_st FROM Users WHERE username = :username"
    )
    try:
        user_data = read_sql_query(BDD, query_user, params={"username": username})
    except Exception:
        logger.exception("check_usr_pass: DB error while looking up user")
        return False, None

    if user_data is None or user_data.empty:
        return False, None

    expected_hash = str(user_data["password_st"].iloc[0])
    provided_hash = hashlib.md5(password.encode()).hexdigest()
    if hmac.compare_digest(expected_hash, provided_hash):
        logger.info("User authenticated successfully.")
        return True, int(user_data["ID_USER"].iloc[0])
    return False, None
