"""Pytest configuration: prepare Streamlit session_state before tests import data.py."""

import os
import sys

import streamlit as st

PROJECT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# data.py reads st.session_state["project_path"] at import time.
try:
    st.session_state["project_path"] = PROJECT_PATH
except Exception:
    # Streamlit raises outside a script run; fall back to a plain dict shim.
    class _SS(dict):
        def __getattr__(self, k):
            return self.get(k)

        def __setattr__(self, k, v):
            self[k] = v

    st.session_state = _SS({"project_path": PROJECT_PATH})  # type: ignore[attr-defined]
