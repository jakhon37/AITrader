"""Streamlit dashboard for exploring features and data.

Run with:
    streamlit run dashboards/feature_explorer.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data.loaders.csv_loader import load_ohlcv_csv
from features.feature_engine import FeatureEngine

# Page config
st.set_page_config(
    page_title="AITrader Feature Explorer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔍 Feature Explorer")
st.markdown("Explore market data, features, and correlations")


@st.cache_data
def load_data(symbol, timeframe="1d"):
    """Load market data."""
    try:
        # Try timeframe-specific file first, fallback to daily
        csv_filename = f"data/raw/{symbol}_{timeframe}.csv"
        if not Path(csv_filename).exists():
            csv_filename = f"data/raw/{symbol}_daily.csv"
        df = load_ohlcv_csv(csv_filename)
        return df
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return pd.DataFrame()


@st.cache_data
def compute_features(symbol, lookback_days, timeframe="1d"):
    """Compute features for a symbol."""
    try:
        df = load_data(symbol, timeframe)
        if df.empty:
            return pd.DataFrame()

        # Take last N days
        df = df.tail(lookback_days).copy()

        # Compute features
        engine = FeatureEngine()
        features = engine.compute_features(df, {})

        return features
    except Exception as e:
        st.error(f"Failed to compute features: {e}")
        return pd.DataFrame()


def plot_ohlc(df, symbol):
    """Plot OHLC candlestick chart."""
    if df.empty:
        st.warning("No data to plot")
        return

    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
        )
    )

    fig.update_layout(
        title=f"{symbol.upper()} Price Chart",
        xaxis_title="Date",
        yaxis_title="Price",
        height=400,
        xaxis_rangeslider_visible=False,
    )

    st.plotly_chart(fig, width="stretch")


def plot_volume(df):
    """Plot volume bars."""
    if df.empty or "volume" not in df.columns:
        return

    fig = go.Figure()

    colors = ["green" if df["close"].iloc[i] > df["open"].iloc[i] else "red" 
              for i in range(len(df))]

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["volume"],
            marker_color=colors,
            name="Volume",
            opacity=0.6,
        )
    )

    fig.update_layout(
        title="Volume",
        xaxis_title="Date",
        yaxis_title="Volume",
        height=200,
        showlegend=False,
    )

    st.plotly_chart(fig, width="stretch")


def plot_feature_timeseries(features, selected_features):
    """Plot selected features over time."""
    if features.empty:
        st.warning("No features to plot")
        return

    fig = go.Figure()

    for feature in selected_features:
        if feature in features.columns:
            fig.add_trace(
                go.Scatter(
                    x=features.index,
                    y=features[feature],
                    mode="lines",
                    name=feature,
                )
            )

    fig.update_layout(
        title="Feature Values Over Time",
        xaxis_title="Date",
        yaxis_title="Value",
        height=400,
        hovermode="x unified",
    )

    st.plotly_chart(fig, width="stretch")


def plot_correlation_heatmap(features):
    """Plot feature correlation heatmap."""
    if features.empty:
        st.warning("No features to correlate")
        return

    # Select only numeric columns
    numeric_features = features.select_dtypes(include=["float64", "int64"])

    if numeric_features.empty:
        st.warning("No numeric features")
        return

    # Compute correlation
    corr = numeric_features.corr()

    fig = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=corr.columns,
            y=corr.columns,
            colorscale="RdBu",
            zmid=0,
            text=corr.values,
            texttemplate="%{text:.2f}",
            textfont={"size": 8},
        )
    )

    fig.update_layout(
        title="Feature Correlation Matrix",
        height=600,
        width=800,
    )

    st.plotly_chart(fig, width="stretch")


def plot_feature_distribution(features, selected_feature):
    """Plot distribution of a single feature."""
    if features.empty or selected_feature not in features.columns:
        return

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=features[selected_feature],
            nbinsx=50,
            name=selected_feature,
            marker_color="#00D9FF",
        )
    )

    fig.update_layout(
        title=f"Distribution of {selected_feature}",
        xaxis_title="Value",
        yaxis_title="Frequency",
        height=300,
        showlegend=False,
    )

    st.plotly_chart(fig, width="stretch")


def show_feature_stats(features):
    """Show feature statistics."""
    if features.empty:
        st.warning("No features available")
        return

    st.subheader("📊 Feature Statistics")

    numeric_features = features.select_dtypes(include=["float64", "int64"])

    if numeric_features.empty:
        st.warning("No numeric features")
        return

    stats = numeric_features.describe().T
    stats["missing"] = numeric_features.isnull().sum()
    stats["missing_pct"] = (stats["missing"] / len(features)) * 100

    st.dataframe(stats, width="stretch")


# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")

    symbol = st.selectbox(
        "Symbol",
        ["eurusd", "gbpusd", "usdjpy", "gold", "btcusd"],
        index=0,
    )

    timeframe = st.selectbox(
        "Timeframe",
        ["1m", "5m", "15m", "30m", "1h", "1d"],
        index=5,  # Default to 1d
        help="Select data timeframe (1m requires recent downloaded data)"
    )

    lookback_days = st.slider(
        "Lookback Days", min_value=30, max_value=365, value=90, step=10
    )

    st.divider()

    st.header("🎯 Quick Stats")

    data = load_data(symbol, timeframe)
    if not data.empty:
        st.metric("Total Bars", len(data))
        st.metric("Latest Close", f"${data['close'].iloc[-1]:.4f}")

        returns = data["close"].pct_change()
        st.metric(f"Last Return", f"{returns.iloc[-1]:.2%}")
        st.metric("Volatility (30 bars)", f"{returns.tail(30).std():.2%}")


# Main content
features = compute_features(symbol, lookback_days, timeframe)
data = load_data(symbol, timeframe).tail(lookback_days)

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📈 Price Chart", "🔢 Features", "🔗 Correlations", "📊 Stats"])

with tab1:
    st.subheader(f"Price and Volume for {symbol.upper()}")
    plot_ohlc(data, symbol)
    plot_volume(data)

with tab2:
    st.subheader("Feature Time Series")

    if not features.empty:
        # Feature selector
        numeric_cols = features.select_dtypes(include=["float64", "int64"]).columns
        selected_features = st.multiselect(
            "Select features to plot",
            options=numeric_cols.tolist(),
            default=numeric_cols[:3].tolist() if len(numeric_cols) >= 3 else numeric_cols.tolist(),
            max_selections=5,
        )

        if selected_features:
            plot_feature_timeseries(features, selected_features)

            # Distribution for first selected feature
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                plot_feature_distribution(features, selected_features[0])
            if len(selected_features) > 1:
                with col2:
                    plot_feature_distribution(features, selected_features[1])
    else:
        st.warning("No features computed")

with tab3:
    st.subheader("Feature Correlations")
    plot_correlation_heatmap(features)

with tab4:
    show_feature_stats(features)

st.divider()

st.markdown(
    """
    ### 💡 Tips
    - Use the correlation heatmap to identify redundant features
    - Check feature distributions for outliers or skewness
    - Monitor missing values in the stats table
    - Increase lookback days for longer-term patterns
    """
)
