"""Causal validation using Granger causality tests.

Validates which features actually have predictive power for price movement.
Uses Granger causality to test if one time series helps predict another.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests


def granger_causality(
    target: pd.Series,
    feature: pd.Series,
    max_lag: int = 5,
    significance: float = 0.05,
) -> dict[str, any]:
    """Test if feature Granger-causes target.

    Args:
        target: Target series (e.g., returns)
        feature: Feature series to test
        max_lag: Maximum lag to test
        significance: Significance level for causality

    Returns:
        Dict with test results and whether feature is causal
    """
    # Combine into DataFrame and drop NaN
    df = pd.DataFrame({"target": target, "feature": feature}).dropna()

    if len(df) < max_lag + 10:
        return {"is_causal": False, "reason": "insufficient_data"}

    try:
        # Run Granger causality test (verbose parameter removed as it's deprecated)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = grangercausalitytests(df[["target", "feature"]], maxlag=max_lag)

        # Check if any lag shows causality
        is_causal = False
        best_lag = None
        best_pvalue = 1.0

        for lag in range(1, max_lag + 1):
            # Use F-test p-value
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
    """Validate multiple features for causality.

    Args:
        target: Target series
        features: DataFrame of features to test
        max_lag: Maximum lag
        significance: Significance level

    Returns:
        DataFrame with causality results for each feature
    """
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

    Args:
        target: Target series
        features: DataFrame of features
        max_lag: Maximum lag
        significance: Significance level

    Returns:
        List of causal feature names
    """
    results = validate_features(target, features, max_lag, significance)
    causal = results[results["is_causal"] == True]
    return causal["feature"].tolist()
