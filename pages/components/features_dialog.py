"""Composant partagé : dialog Streamlit pour afficher les features d'un match."""

import pandas as pd
import streamlit as st

from data import (
    get_features_table_name,
    load_match_features,
    load_match_predictions,
    load_table_update_time,
)
from utils import csv_download_button


def _coerce_id(value):
    """Convertit un ID en int si possible (les NULL UNION le passent en float)."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _find_update_timestamp(row: pd.Series):
    candidates = (
        "date_maj",
        "dt_maj",
        "updated_at",
        "update_at",
        "last_update",
        "last_updated",
        "created_at",
        "timestamp",
        "ts",
    )
    cols_lower = {str(col).lower(): col for col in row.index}

    for name in candidates:
        col = cols_lower.get(name)
        if col is None:
            continue
        ts = pd.to_datetime(row.get(col), errors="coerce")
        if pd.notna(ts):
            return col, ts

    for col in row.index:
        col_name = str(col).lower()
        if not any(
            token in col_name for token in ("maj", "update", "timestamp", "date")
        ):
            continue
        ts = pd.to_datetime(row.get(col), errors="coerce")
        if pd.notna(ts):
            return col, ts

    return None, None


def _format_elapsed_hm(timestamp) -> str | None:
    if timestamp is None or pd.isna(timestamp):
        return None

    ts = pd.Timestamp(timestamp)
    now = pd.Timestamp.now(tz=ts.tz) if ts.tzinfo is not None else pd.Timestamp.now()
    delta = now - ts
    total_minutes = max(int(delta.total_seconds() // 60), 0)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _render_update_caption(row: pd.Series, label: str):
    col, timestamp = _find_update_timestamp(row)
    if timestamp is None:
        return

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)

    elapsed = _format_elapsed_hm(timestamp)
    formatted_date = ts.strftime("%d/%m/%Y %H:%M")
    if elapsed is None:
        st.caption(f"{label} mis a jour le {formatted_date}")
        return

    st.caption(f"{label} mis a jour le {formatted_date} · il y a {elapsed} ({col})")


def _render_table_update_caption(table_name: str | None, label: str):
    if not table_name:
        return

    timestamp = load_table_update_time(table_name)
    if timestamp is None:
        return

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)

    elapsed = _format_elapsed_hm(timestamp)
    formatted_date = ts.strftime("%d/%m/%Y %H:%M")
    suffix = f" · il y a {elapsed}" if elapsed is not None else ""
    st.caption(f"{label} mis a jour le {formatted_date}{suffix} (table {table_name})")


def get_tables_update_text(table_names, label: str = "Maj base") -> str | None:
    timestamps = []
    for table_name in dict.fromkeys(table_names):
        if not table_name:
            continue
        timestamp = load_table_update_time(table_name)
        if timestamp is None:
            continue
        timestamps.append(pd.Timestamp(timestamp))

    if not timestamps:
        return None

    latest = max(timestamps)
    if latest.tzinfo is not None:
        latest = latest.tz_convert(None)

    elapsed = _format_elapsed_hm(latest)
    formatted_date = latest.strftime("%d/%m/%Y %H:%M")
    if elapsed is None:
        return f"{label} {formatted_date}"

    return f"{label} {formatted_date} · {elapsed}"


def get_features_key(row, compet: str | None = None):
    """Retourne (key_label, key_value) selon la compétition.
    - Doubles → ID_MATCH
    - Simples → ID_TENNET
    """
    compet = (compet or row.get("Compétition") or "").strip().lower()
    is_doubles = compet == "doubles"
    if is_doubles:
        return "ID_MATCH", _coerce_id(row.get("ID_MATCH"))
    # ID_TENNET (case-insensitive)
    for cand in ("ID_TENNET", "id_tennet", "Id_TENNET"):
        if cand in row:
            return "ID_TENNET", _coerce_id(row.get(cand))
    return "ID_TENNET", None


@st.dialog("📊 Features du match", width="large")
def show_features_dialog(match_id, compet: str, match_label: str, id_match=None):
    match_id = _coerce_id(match_id)
    id_match = _coerce_id(id_match) if id_match is not None else None
    st.markdown(f"**{match_label}**")
    cap = f"Clé : `{match_id}` — Compétition : {compet}"
    if id_match is not None and id_match != match_id:
        cap += f" — ID_MATCH : `{id_match}`"
    st.caption(cap)

    if match_id is None:
        st.warning("Aucune clé disponible pour ce match.")
        return

    # ---- Prédictions ----------------------------------------------------
    pred_lookup = id_match if id_match is not None else match_id
    with st.spinner("Chargement des prédictions…"):
        preds = load_match_predictions(pred_lookup)
    if preds is not None and not preds.empty:
        prow = preds.iloc[0]
        with st.expander("🔮 Prédictions", expanded=True):
            _render_update_caption(prow, "Predictions")
            _render_table_update_caption("predictions", "Predictions")
            # Affiche en priorité quelques colonnes connues, puis le reste
            preferred = [
                "pred_w_used",
                "pred_l_used",
                "pred_w",
                "pred_l",
                "proba_w",
                "proba_l",
                "model_used",
                "model",
                "ID_MATCH",
            ]
            cols_lower = {c.lower(): c for c in prow.index}
            ordered = []
            for k in preferred:
                if k.lower() in cols_lower:
                    ordered.append(cols_lower[k.lower()])
            for c in prow.index:
                if c not in ordered:
                    ordered.append(c)

            def _fmt_pred(v):
                try:
                    return f"{float(v):.4g}"
                except (TypeError, ValueError):
                    return (
                        "—"
                        if v is None or (isinstance(v, float) and pd.isna(v))
                        else str(v)
                    )

            df_pred = pd.DataFrame(
                {"Champ": ordered, "Valeur": [_fmt_pred(prow[c]) for c in ordered]}
            )
            st.dataframe(df_pred, width="stretch", hide_index=True, height=260)
    else:
        st.caption("ℹ️ Aucune prédiction trouvée pour ce match.")

    # ---- Features --------------------------------------------------------
    with st.spinner("Chargement des features…"):
        feats = load_match_features(match_id, compet)
    if feats is None or feats.empty:
        st.info("Aucune feature trouvée pour ce match.")
        return

    row = feats.iloc[0]
    _render_update_caption(row, "Features")
    _render_table_update_caption(get_features_table_name(compet), "Features")

    # Pairing winner_/loser_
    paired = []
    others = []
    seen = set()
    for col in row.index:
        if col in seen:
            continue
        low = col.lower()
        if low.startswith("winner_"):
            stat = col[len("winner_") :]
            counterpart = next(
                (
                    c
                    for c in (f"loser_{stat}", f"Loser_{stat}", f"LOSER_{stat}")
                    if c in row.index
                ),
                None,
            )
            if counterpart is not None:
                vw, vl = row[col], row[counterpart]
                try:
                    diff = float(vw) - float(vl)
                except (TypeError, ValueError):
                    diff = None
                paired.append(
                    {"Stat": stat, "Winner": vw, "Loser": vl, "Diff (W-L)": diff}
                )
                seen.update({col, counterpart})
                continue
        if low.startswith("loser_"):
            stat = col[len("loser_") :]
            counterpart = next(
                (
                    c
                    for c in (f"winner_{stat}", f"Winner_{stat}", f"WINNER_{stat}")
                    if c in row.index
                ),
                None,
            )
            if counterpart is not None:
                vw, vl = row[counterpart], row[col]
                try:
                    diff = float(vw) - float(vl)
                except (TypeError, ValueError):
                    diff = None
                paired.append(
                    {"Stat": stat, "Winner": vw, "Loser": vl, "Diff (W-L)": diff}
                )
                seen.update({col, counterpart})
                continue
        others.append(col)

    df_pair = pd.DataFrame(paired)
    df_other = pd.DataFrame({"Feature": others, "Valeur": [row[c] for c in others]})

    q = st.text_input("🔎 Filtrer", value="", placeholder="Tape une partie du nom…")
    if q:
        if not df_pair.empty:
            df_pair = df_pair[
                df_pair["Stat"].astype(str).str.contains(q, case=False, na=False)
            ]
        if not df_other.empty:
            df_other = df_other[
                df_other["Feature"].astype(str).str.contains(q, case=False, na=False)
            ]

    if df_pair.empty:
        st.info("Aucune paire winner_/loser_ détectée.")
    else:
        for c in ("Winner", "Loser", "Diff (W-L)"):
            df_pair[c] = pd.to_numeric(df_pair[c], errors="ignore")
        styler = df_pair.style.format(
            {"Winner": "{:.4g}", "Loser": "{:.4g}", "Diff (W-L)": "{:+.4g}"},
            na_rep="—",
        )

        def _diff_color(v):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return ""
            if f > 0:
                return "color:#32b296; font-weight:700;"
            if f < 0:
                return "color:#e04e4e; font-weight:700;"
            return "color:#9ca3af;"

        try:
            styler = styler.map(_diff_color, subset=["Diff (W-L)"])
        except Exception:
            pass
        st.dataframe(styler, width="stretch", hide_index=True, height=500)

    if not df_other.empty:
        with st.expander(f"🔑 Méta-données ({len(df_other)})", expanded=False):
            st.dataframe(df_other, width="stretch", hide_index=True)

    export_df = df_pair if not df_pair.empty else df_other
    csv_download_button(
        export_df,
        label="📥 Exporter CSV",
        filename=f"features_{match_id}.csv",
        key=f"feat_csv_{match_id}",
    )
