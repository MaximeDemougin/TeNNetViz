import pandas as pd

from pages.components.insights import _build_insights, _cote_bucket


def _make_df():
    rows = []
    # 12 winning bets on Clay
    for i in range(12):
        rows.append(
            {
                "Surface": "Clay",
                "Type de tournoi": "ATP 250",
                "Round": "R32",
                "Compétition": "ATP",
                "Mise": 10.0,
                "Cote": 1.8,
                "Gains net": 8.0,
                "Marge attendue": 1.0,
            }
        )
    # 12 losing bets on Hard
    for i in range(12):
        rows.append(
            {
                "Surface": "Hard",
                "Type de tournoi": "ATP 250",
                "Round": "R32",
                "Compétition": "ATP",
                "Mise": 10.0,
                "Cote": 1.8,
                "Gains net": -10.0,
                "Marge attendue": 1.0,
            }
        )
    # 5 bets on Grass (below min_n threshold)
    for i in range(5):
        rows.append(
            {
                "Surface": "Grass",
                "Type de tournoi": "ATP 500",
                "Round": "R16",
                "Compétition": "ATP",
                "Mise": 10.0,
                "Cote": 2.0,
                "Gains net": 50.0,
                "Marge attendue": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_cote_bucket_boundaries():
    assert _cote_bucket(1.2) == "Cote < 1.5"
    assert _cote_bucket(1.5) == "Cote 1.5–2.0"
    assert _cote_bucket(2.0) == "Cote 2.0–2.5"
    assert _cote_bucket(3.4) == "Cote 2.5–3.5"
    assert _cote_bucket(3.5) == "Cote ≥ 3.5"


def test_build_insights_respects_min_n_and_roi():
    df = _make_df()
    out = _build_insights(df, min_n=10)
    assert not out.empty
    surfaces = out[out["dim"] == "Surface"]
    # Grass has only 5 → must be filtered out
    assert "Grass" not in surfaces["value"].tolist()
    clay = surfaces[surfaces["value"] == "Clay"].iloc[0]
    hard = surfaces[surfaces["value"] == "Hard"].iloc[0]
    assert clay["ROI"] > 0
    assert hard["ROI"] < 0


def test_build_insights_empty():
    assert _build_insights(pd.DataFrame()).empty
