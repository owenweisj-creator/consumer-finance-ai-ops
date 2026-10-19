from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split

from src.analytics.metrics import query_df
from src.config import DATA_PROCESSED, REPORTS_DIR

NUMERIC_FEATURES = [
    "age_years",
    "employed_years",
    "income",
    "credit_amount",
    "annuity",
    "goods_price",
    "credit_income_ratio",
    "annuity_income_ratio",
    "ext_source_mean",
    "region_rating",
    "region_population_relative",
    "children_count",
    "family_members",
]

CATEGORICAL_FEATURES = [
    "contract_type",
    "gender",
    "education",
    "family_status",
    "housing_type",
    "income_type",
    "occupation",
    "organization_type",
]


@dataclass
class BinningRule:
    feature: str
    kind: str
    mapping: dict
    iv: float


def _woe_iv(frame: pd.DataFrame, feature: str, target: str = "target") -> tuple[dict, float]:
    grouped = (
        frame.groupby(feature, dropna=False)[target]
        .agg(["count", "sum"])
        .rename(columns={"count": "total", "sum": "bad"})
        .reset_index()
    )
    grouped["good"] = grouped["total"] - grouped["bad"]
    total_bad = max(grouped["bad"].sum(), 1)
    total_good = max(grouped["good"].sum(), 1)
    grouped["bad_rate"] = grouped["bad"] / grouped["total"].replace(0, np.nan)
    grouped["bad_share"] = (grouped["bad"] + 0.5) / (total_bad + 0.5 * len(grouped))
    grouped["good_share"] = (grouped["good"] + 0.5) / (total_good + 0.5 * len(grouped))
    grouped["woe"] = np.log(grouped["bad_share"] / grouped["good_share"])
    grouped["iv_component"] = (grouped["bad_share"] - grouped["good_share"]) * grouped["woe"]
    iv = float(grouped["iv_component"].sum())
    mapping = {
        (None if pd.isna(row[feature]) else str(row[feature])): float(row["woe"])
        for _, row in grouped.iterrows()
    }
    return mapping, iv


def _numeric_bins(train: pd.DataFrame, feature: str, bins: int = 8) -> tuple[list[float], dict, float]:
    series = pd.to_numeric(train[feature], errors="coerce")
    edges = np.unique(np.nanquantile(series, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return [], {}, 0.0
    edges[0] = -np.inf
    edges[-1] = np.inf
    binned = pd.cut(series, bins=edges, include_lowest=True, duplicates="drop")
    temp = train.assign(_bin=binned.astype(str))
    mapping, iv = _woe_iv(temp, "_bin")
    return list(edges), mapping, iv


def fit_scorecard(sample_size: int | None = None) -> dict:
    df = query_df(
        """
        SELECT *
        FROM mart.fact_application
        WHERE target IS NOT NULL
        """
    )
    if sample_size and len(df) > sample_size:
        df = df.sample(sample_size, random_state=42)
    df = df.dropna(subset=["target"]).copy()
    df["target"] = df["target"].astype(int)

    train, test = train_test_split(df, test_size=0.3, random_state=42, stratify=df["target"])
    rules: list[BinningRule] = []
    for feature in NUMERIC_FEATURES:
        if feature not in train.columns:
            continue
        edges, mapping, iv = _numeric_bins(train, feature)
        if mapping:
            rules.append(BinningRule(feature, "numeric", {"edges": edges, "woe": mapping}, iv))
    for feature in CATEGORICAL_FEATURES:
        if feature not in train.columns:
            continue
        series = train[feature].astype("string").fillna("Missing")
        value_counts = series.value_counts(normalize=True)
        keep = set(value_counts[value_counts >= 0.01].index)
        transformed = series.where(series.isin(keep), "Other")
        temp = train.assign(_cat=transformed)
        mapping, iv = _woe_iv(temp, "_cat")
        rules.append(BinningRule(feature, "categorical", {"woe": mapping, "keep": sorted(keep)}, iv))

    rules = [rule for rule in rules if rule.iv >= 0.02]
    rules.sort(key=lambda item: item.iv, reverse=True)

    def transform(frame: pd.DataFrame) -> pd.DataFrame:
        output = pd.DataFrame(index=frame.index)
        for rule in rules:
            if rule.kind == "numeric":
                series = pd.to_numeric(frame[rule.feature], errors="coerce")
                binned = pd.cut(series, bins=rule.mapping["edges"], include_lowest=True, duplicates="drop")
                keys = binned.astype(str)
                output[rule.feature] = keys.map(rule.mapping["woe"]).fillna(0.0)
            else:
                series = frame[rule.feature].astype("string").fillna("Missing")
                series = series.where(series.isin(rule.mapping["keep"]), "Other")
                output[rule.feature] = series.map(rule.mapping["woe"]).fillna(0.0)
        return output

    train_x = transform(train)
    test_x = transform(test)
    # Keep the model calibrated: class_weight="balanced" would inflate PD and
    # make the risk bands look far worse than the observed bad rate.
    model = LogisticRegression(max_iter=2000, class_weight=None, solver="lbfgs")
    model.fit(train_x, train["target"])
    train_pd = model.predict_proba(train_x)[:, 1]
    test_pd = model.predict_proba(test_x)[:, 1]

    auc = float(roc_auc_score(test["target"], test_pd))
    fpr, tpr, _ = roc_curve(test["target"], test_pd)
    ks = float(np.max(tpr - fpr))

    full_x = transform(df)
    df["predicted_pd"] = model.predict_proba(full_x)[:, 1]
    df["risk_band"] = pd.qcut(
        df["predicted_pd"], q=5, labels=["A-低风险", "B-较低风险", "C-中风险", "D-较高风险", "E-高风险"]
    ).astype(str)

    metrics = {
        "rows": int(len(df)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "bad_rate": round(float(df["target"].mean()), 4),
        "auc": round(auc, 4),
        "ks": round(ks, 4),
        "features_used": len(rules),
        "features": [
            {
                "feature": rule.feature,
                "kind": rule.kind,
                "iv": round(rule.iv, 4),
                "coefficient": round(float(coef), 4),
            }
            for rule, coef in zip(rules, model.coef_[0])
        ],
        "risk_band_summary": (
            df.groupby("risk_band", observed=True)
            .agg(customers=("customer_id", "count"), bad_rate=("target", "mean"), avg_pd=("predicted_pd", "mean"))
            .reset_index()
            .assign(bad_rate=lambda x: x["bad_rate"].round(4), avg_pd=lambda x: x["avg_pd"].round(4))
            .to_dict(orient="records")
        ),
        "note": "AUC < 0.72 is treated as a segmentation tool, not a production credit model."
        if auc < 0.72
        else "Model performance is sufficient for portfolio segmentation; production use still requires validation.",
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "scorecard_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df[["customer_id", "predicted_pd", "risk_band"]].to_csv(
        DATA_PROCESSED / "customer_risk_scores.csv", index=False, encoding="utf-8-sig"
    )
    return metrics


if __name__ == "__main__":
    print(json.dumps(fit_scorecard(), ensure_ascii=False, indent=2))
