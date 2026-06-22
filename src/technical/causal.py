"""Causal validation using Granger causality tests for AITrader.

Validates which features actually have predictive power for price movement.
Uses Granger causality to test if one time series helps predict another.
"""

from __future__ import annotations

import warnings
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import grangercausalitytests


def granger_causality(
    target: pd.Series,
    feature: pd.Series,
    max_lag: int = 5,
    significance: float = 0.05,
) -> dict[str, any]:
    """Test if feature Granger-causes target."""
    df = pd.DataFrame({"target": target, "feature": feature}).dropna()

    if len(df) < max_lag + 10:
        return {"is_causal": False, "reason": "insufficient_data"}

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = grangercausalitytests(df[["target", "feature"]], maxlag=max_lag)

        is_causal = False
        best_lag = None
        best_pvalue = 1.0

        for lag in range(1, max_lag + 1):
            pvalue = results[lag][0]["ssr_ftest"][1]

            if pvalue < best_pvalue:
                best_pvalue = pvalue
                best_lag = lag

            if pvalue < significance:
                is_causal = True

        return {
            "is_causal": is_causal,
            "best_lag": best_lag,
            "best_pvalue": best_pvalue,
            "significance": significance,
        }

    except Exception as e:
        return {"is_causal": False, "reason": f"error: {str(e)}"}


def validate_features(
    target: pd.Series,
    features: pd.DataFrame,
    max_lag: int = 5,
    significance: float = 0.05,
) -> pd.DataFrame:
    """Validate multiple features for causality."""
    results = []

    for col in features.columns:
        result = granger_causality(target, features[col], max_lag, significance)
        results.append({
            "feature": col,
            **result,
        })

    return pd.DataFrame(results).sort_values("best_pvalue")


def select_causal_features(
    target: pd.Series,
    features: pd.DataFrame,
    max_lag: int = 5,
    significance: float = 0.05,
) -> list[str]:
    """Select only features that Granger-cause the target.

    Logs a metric for D11 observability if a high percentage of features are dropped.
    """
    if features.empty:
        return []

    results = validate_features(target, features, max_lag, significance)
    causal = results[results["is_causal"] == True]
    causal_cols = causal["feature"].tolist()

    dropped_pct = (len(features.columns) - len(causal_cols)) / len(features.columns) * 100
    
    # We can print/log this metric. In Phase 7 / D11, this can be hooked into a metric system.
    # For now, we log it.
    from src.core.logging import get_logger
    logger = get_logger("D04-TECHNICAL")
    logger.info(
        "causal_feature_selection",
        total_features=len(features.columns),
        causal_features=len(causal_cols),
        dropped_percentage=dropped_pct,
    )

    if dropped_pct > 50.0:
        logger.warning(
            "high_causal_drop_rate",
            message=f"Causal filter dropped {dropped_pct:.1f}% of features. Verify validator config.",
        )

    return causal_cols
