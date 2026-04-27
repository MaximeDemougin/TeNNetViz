"""Composant partagé : dialog Streamlit pour afficher les features d'un match."""

import pandas as pd
import streamlit as st

from data import (
    load_match_features,
    load_match_odds,
    load_match_predictions,
    load_odds_latest_maj_time,
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

    ts = _to_real_utc_naive(timestamp)
    if ts is None:
        return None
    now = _to_real_utc_naive(pd.Timestamp.now())
    if now is None:
        now = pd.Timestamp.now()
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

    if str(table_name).strip().lower() == "odds":
        timestamp = load_odds_latest_maj_time()
    else:
        timestamp = load_table_update_time(table_name)
    if timestamp is None:
        return

    ts = _to_real_utc_naive(timestamp)
    if ts is None:
        return

    elapsed = _format_elapsed_hm(timestamp)
    formatted_date = ts.strftime("%d/%m/%Y %H:%M")
    suffix = f" · il y a {elapsed}" if elapsed is not None else ""
    st.caption(f"{label} mis a jour le {formatted_date}{suffix} (table {table_name})")


def get_tables_update_text(table_names, label: str = "Maj base") -> str | None:
    timestamps = []
    for table_name in dict.fromkeys(table_names):
        if not table_name:
            continue
        if str(table_name).strip().lower() == "odds":
            timestamp = load_odds_latest_maj_time()
        else:
            timestamp = load_table_update_time(table_name)
        if timestamp is None:
            continue
        ts = _to_real_utc_naive(timestamp)
        if ts is not None:
            timestamps.append(ts)

    if not timestamps:
        return None

    latest = max(timestamps)
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


def _build_paired_table(
    row: pd.Series, pairs: list[tuple[str, str, str]]
) -> pd.DataFrame:
    rows = []
    for stat, w_col, l_col in pairs:
        if w_col in row.index and l_col in row.index:
            rows.append(
                {
                    "Stat": stat,
                    "Winner": row.get(w_col),
                    "Loser": row.get(l_col),
                }
            )
    return pd.DataFrame(rows)


def _frame_height(n_rows: int, min_height: int = 90, max_height: int = 360) -> int:
    # Approx: header + n rows with compact padding.
    return max(min_height, min(max_height, 38 + max(int(n_rows), 1) * 35))


def _format_exact_ts(value) -> str | None:
    ts = _to_real_utc_naive(value)
    if ts is not None:
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip() if value is not None else ""
    return text or None


def _to_real_utc_naive(value) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.notna(ts):
        out = pd.Timestamp(ts)
        # Affichage en heure réelle (UTC).
        # Si naive, on considère qu'il provient de Europe/Paris puis on convertit en UTC.
        if out.tzinfo is None:
            out = out.tz_localize("Europe/Paris")
        return out.tz_convert("UTC").tz_localize(None)
    return None


@st.dialog("📊 Features du match", width="large")
def show_features_dialog(match_id, compet: str, match_label: str, id_match=None):
    match_id = _coerce_id(match_id)
    id_match = _coerce_id(id_match) if id_match is not None else None
    st.markdown(f"**{match_label}**")
    cap = f"Clé : `{match_id}` — Compétition : {compet}"
    if id_match is not None and id_match != match_id:
        cap += f" — ID_MATCH : `{id_match}`"
    st.caption(cap)

    pred_lookup = id_match if id_match is not None else match_id
    with st.spinner("Chargement des odds…"):
        odds = load_match_odds(pred_lookup)

    # Source de vérité: timestamp de la ligne odds du match (fallback table odds).
    if odds is not None and not odds.empty:
        odds_row = odds.iloc[0]
        cols_lower = {str(col).lower(): col for col in odds_row.index}
        maj_col = cols_lower.get("maj")
        if maj_col is not None:
            maj_text = _format_exact_ts(odds_row.get(maj_col))
            if maj_text:
                st.caption(f"maj : {maj_text}")
            else:
                _, odds_ts = _find_update_timestamp(odds_row)
                formatted = _format_exact_ts(odds_ts)
                if formatted:
                    st.caption(f"maj : {formatted}")
        else:
            _, odds_ts = _find_update_timestamp(odds_row)
            formatted = _format_exact_ts(odds_ts)
            if formatted:
                st.caption(f"maj : {formatted}")
            else:
                table_ts = load_odds_latest_maj_time()
                formatted = _format_exact_ts(table_ts)
                if formatted:
                    st.caption(f"maj : {formatted}")
    else:
        table_ts = load_odds_latest_maj_time()
        formatted = _format_exact_ts(table_ts)
        if formatted:
            st.caption(f"maj : {formatted}")

    if match_id is None:
        st.warning("Aucune clé disponible pour ce match.")
        return

    # ---- Prédictions ----------------------------------------------------
    with st.spinner("Chargement des prédictions…"):
        preds = load_match_predictions(pred_lookup)
    if preds is not None and not preds.empty:
        prow = preds.iloc[0]
        with st.expander("🔮 Prédictions", expanded=True):
            pred_pairs = _build_paired_table(
                prow,
                [
                    ("pred_used", "pred_w_used", "pred_l_used"),
                    ("pred", "pred_w", "pred_l"),
                    ("proba", "proba_w", "proba_l"),
                ],
            )
            if pred_pairs.empty:

                def _fmt_pred(v):
                    try:
                        return f"{float(v):.4g}"
                    except (TypeError, ValueError):
                        return (
                            "—"
                            if v is None or (isinstance(v, float) and pd.isna(v))
                            else str(v)
                        )

                fallback = pd.DataFrame(
                    {
                        "Champ": list(prow.index),
                        "Valeur": [_fmt_pred(prow[c]) for c in prow.index],
                    }
                )
                st.dataframe(
                    fallback,
                    width="stretch",
                    hide_index=True,
                    height=_frame_height(len(fallback)),
                )
            else:
                for c in ("Winner", "Loser"):
                    pred_pairs[c] = pd.to_numeric(pred_pairs[c], errors="ignore")
                st.dataframe(
                    pred_pairs.style.format(
                        {
                            "Winner": "{:.4g}",
                            "Loser": "{:.4g}",
                        },
                        na_rep="—",
                    ),
                    width="stretch",
                    hide_index=True,
                    height=_frame_height(len(pred_pairs)),
                )
    else:
        st.caption("ℹ️ Aucune prédiction trouvée pour ce match.")

    # ---- Odds -----------------------------------------------------------
    if odds is not None and not odds.empty:
        orow = odds.iloc[0]
        with st.expander("💸 Odds", expanded=True):
            odds_pairs = _build_paired_table(
                orow,
                [
                    ("Avg", "AvgW", "AvgL"),
                    ("Max", "MaxW", "MaxL"),
                ],
            )
            if odds_pairs.empty:

                def _fmt_odds(v):
                    try:
                        return f"{float(v):.4g}"
                    except (TypeError, ValueError):
                        return (
                            "—"
                            if v is None or (isinstance(v, float) and pd.isna(v))
                            else str(v)
                        )

                fallback = pd.DataFrame(
                    {
                        "Champ": list(orow.index),
                        "Valeur": [_fmt_odds(orow[c]) for c in orow.index],
                    }
                )
                st.dataframe(
                    fallback,
                    width="stretch",
                    hide_index=True,
                    height=_frame_height(len(fallback)),
                )
            else:
                for c in ("Winner", "Loser"):
                    odds_pairs[c] = pd.to_numeric(odds_pairs[c], errors="ignore")
                st.dataframe(
                    odds_pairs.style.format(
                        {
                            "Winner": "{:.4g}",
                            "Loser": "{:.4g}",
                        },
                        na_rep="—",
                    ),
                    width="stretch",
                    hide_index=True,
                    height=_frame_height(len(odds_pairs)),
                )
    else:
        st.caption("ℹ️ Aucune ligne odds trouvée pour ce match.")

    # ---- Features --------------------------------------------------------
    with st.spinner("Chargement des features…"):
        feats = load_match_features(match_id, compet)
    if feats is None or feats.empty:
        st.info("Aucune feature trouvée pour ce match.")
        return

    row = feats.iloc[0]

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
