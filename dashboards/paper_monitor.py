"""Streamlit dashboard for monitoring paper trading.

Run with:
    streamlit run dashboards/paper_monitor.py
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from execution.audit_log import AuditLog


# Page config
st.set_page_config(
    page_title="AITrader Paper Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 AITrader Paper Trading Monitor")
st.markdown("Real-time monitoring of paper trading performance")


@st.cache_data(ttl=5)
def load_audit_events(limit=1000):
    """Load recent audit events."""
    try:
        audit = AuditLog()
        events = audit.read_events(limit=limit)
        stats = audit.get_stats()
        return events, stats
    except Exception as e:
        st.error(f"Failed to load audit log: {e}")
        return [], {}


def parse_pnl_from_events(events):
    """Extract PnL timeline from audit events."""
    pnl_data = []
    cumulative_pnl = 0.0

    for event in events:
        # Handle dict format (from read_events)
        event_type = event.get("event_type", "")
        
        if event_type == "position_close":
            metadata = event.get("metadata", {})
            pnl = metadata.get("pnl", 0)
            cumulative_pnl += pnl

            pnl_data.append(
                {
                    "timestamp": event.get("timestamp", ""),
                    "symbol": metadata.get("symbol", ""),
                    "pnl": pnl,
                    "cumulative_pnl": cumulative_pnl,
                }
            )

    return pd.DataFrame(pnl_data)


def plot_equity_curve(pnl_df, initial_capital=100000):
    """Plot equity curve from PnL data."""
    if pnl_df.empty:
        st.info("No trades yet")
        return

    fig = go.Figure()

    equity = initial_capital + pnl_df["cumulative_pnl"]

    fig.add_trace(
        go.Scatter(
            x=pnl_df["timestamp"],
            y=equity,
            mode="lines+markers",
            name="Portfolio Value",
            line=dict(color="#00D9FF", width=2),
            marker=dict(size=6),
        )
    )

    # Add initial capital line
    fig.add_hline(
        y=initial_capital,
        line_dash="dash",
        line_color="gray",
        annotation_text="Initial Capital",
    )

    fig.update_layout(
        title="Portfolio Value Over Time",
        xaxis_title="Time",
        yaxis_title="Portfolio Value ($)",
        hovermode="x unified",
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)


def plot_trade_pnl(pnl_df):
    """Plot individual trade PnL."""
    if pnl_df.empty:
        st.info("No trades yet")
        return

    colors = ["green" if x > 0 else "red" for x in pnl_df["pnl"]]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=pnl_df.index,
            y=pnl_df["pnl"],
            marker_color=colors,
            text=pnl_df["symbol"],
            textposition="outside",
            name="Trade PnL",
        )
    )

    fig.update_layout(
        title="Individual Trade PnL",
        xaxis_title="Trade #",
        yaxis_title="PnL ($)",
        height=300,
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)


def show_metrics(pnl_df, initial_capital=100000):
    """Show key metrics."""
    if pnl_df.empty:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", 0)
        col2.metric("Total PnL", "$0.00")
        col3.metric("Win Rate", "0%")
        col4.metric("Return", "0.00%")
        return

    total_trades = len(pnl_df)
    total_pnl = pnl_df["pnl"].sum()
    wins = (pnl_df["pnl"] > 0).sum()
    win_rate = wins / total_trades if total_trades > 0 else 0
    total_return = (total_pnl / initial_capital) * 100

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Trades", total_trades)
    col2.metric(
        "Total PnL", f"${total_pnl:,.2f}", delta=f"{total_return:+.2f}%"
    )
    col3.metric("Win Rate", f"{win_rate:.1%}")
    col4.metric("Return", f"{total_return:+.2f}%")


def show_recent_events(events, limit=10):
    """Show recent events table."""
    st.subheader("📋 Recent Events")

    if not events:
        st.info("No events yet")
        return

    # Convert to dataframe
    event_data = []
    for event in events[-limit:]:
        # Handle dict format
        timestamp = event.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%H:%M:%S")
            except:
                time_str = str(timestamp)
        else:
            time_str = ""
            
        event_data.append(
            {
                "Time": time_str,
                "Type": event.get("event_type", ""),
                "Message": event.get("message", ""),
            }
        )

    df = pd.DataFrame(event_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def show_event_stats(stats):
    """Show event statistics."""
    st.subheader("📊 Event Statistics")

    if not stats:
        st.info("No stats available")
        return

    total_events = stats.get("total_events", 0)
    event_counts = stats.get("event_counts", {})

    col1, col2 = st.columns([1, 2])

    with col1:
        st.metric("Total Events", total_events)

    with col2:
        if event_counts:
            st.write("**Event Breakdown:**")
            for event_type, count in sorted(
                event_counts.items(), key=lambda x: x[1], reverse=True
            ):
                st.write(f"- {event_type}: {count}")


def show_open_positions():
    """Show open positions (mock for now)."""
    st.subheader("📈 Open Positions")
    st.info("No open positions (connected to paper trading when running)")


# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")

    initial_capital = st.number_input(
        "Initial Capital ($)", value=100000, step=1000, format="%d"
    )

    auto_refresh = st.checkbox("Auto-refresh (5s)", value=True)

    if auto_refresh:
        st.markdown("🔄 Auto-refreshing...")

    st.divider()

    st.header("🎯 Quick Actions")

    if st.button("🔄 Refresh Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    st.markdown("**Status:** 🟢 Paper Trading")
    st.markdown("**Started:** Just now")


# Main content
events, stats = load_audit_events(limit=1000)
pnl_df = parse_pnl_from_events(events)

# Metrics row
show_metrics(pnl_df, initial_capital)

st.divider()

# Charts
col1, col2 = st.columns([2, 1])

with col1:
    plot_equity_curve(pnl_df, initial_capital)

with col2:
    plot_trade_pnl(pnl_df)

st.divider()

# Bottom section
col1, col2 = st.columns(2)

with col1:
    show_recent_events(events, limit=10)

with col2:
    show_event_stats(stats)
    st.divider()
    show_open_positions()

# Auto-refresh
if auto_refresh:
    import time

    time.sleep(5)
    st.rerun()
