"""Generate backtest visualizations.

Usage:
    python scripts/generate_plots.py --symbol eurusd --model lstm_transformer
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backtest.engine import BacktestConfig
from visualization.backtest_plots import (
    plot_equity_curve,
    plot_drawdown,
    plot_returns_distribution,
    plot_monthly_returns_heatmap,
    plot_trade_analysis,
)
from visualization.report_generator import generate_html_report

# Import run_backtest from the other script
import importlib.util
spec = importlib.util.spec_from_file_location("run_backtest", Path(__file__).parent / "run_backtest.py")
run_backtest_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_backtest_module)


def main():
    parser = argparse.ArgumentParser(description="Generate backtest plots")
    parser.add_argument("--symbol", default="eurusd")
    parser.add_argument("--model", default="lstm_transformer")
    parser.add_argument("--model-version", help="Model version (default: latest)")
    parser.add_argument("--output-dir", default="reports", help="Output directory")
    parser.add_argument("--show", action="store_true", help="Show plots interactively")
    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run backtest
    print(f"\nRunning backtest for {args.model} on {args.symbol}...\n")
    
    config = BacktestConfig()
    result, metrics = run_backtest_module.run_backtest(
        args.symbol,
        args.model,
        args.model_version or run_backtest_module.ModelRegistry(base_path="models/registry").index["models"][args.model][-1],
        backtest_config=config,
    )

    # Generate plots
    print(f"\n{'='*70}")
    print("GENERATING PLOTS")
    print('='*70)

    # 1. Equity curve
    fig1 = plot_equity_curve(
        result,
        title=f"Equity Curve: {args.model} on {args.symbol.upper()}",
        save_path=output_dir / f"{args.symbol}_{args.model}_equity.png",
    )
    print(f"✓ Equity curve saved to {output_dir / f'{args.symbol}_{args.model}_equity.png'}")

    # 2. Drawdown
    fig2 = plot_drawdown(
        result,
        title=f"Drawdown: {args.model} on {args.symbol.upper()}",
        save_path=output_dir / f"{args.symbol}_{args.model}_drawdown.png",
    )
    print(f"✓ Drawdown plot saved to {output_dir / f'{args.symbol}_{args.model}_drawdown.png'}")

    # 3. Returns distribution
    fig3 = plot_returns_distribution(
        result,
        title=f"Returns Distribution: {args.model} on {args.symbol.upper()}",
        save_path=output_dir / f"{args.symbol}_{args.model}_returns_dist.png",
    )
    print(f"✓ Returns distribution saved to {output_dir / f'{args.symbol}_{args.model}_returns_dist.png'}")

    # 4. Monthly returns heatmap
    fig4 = plot_monthly_returns_heatmap(
        result,
        title=f"Monthly Returns: {args.model} on {args.symbol.upper()}",
        save_path=output_dir / f"{args.symbol}_{args.model}_monthly.png",
    )
    print(f"✓ Monthly heatmap saved to {output_dir / f'{args.symbol}_{args.model}_monthly.png'}")

    # 5. Trade analysis
    if len(result.trades) > 0:
        fig5 = plot_trade_analysis(
            result,
            title=f"Trade Analysis: {args.model} on {args.symbol.upper()}",
            save_path=output_dir / f"{args.symbol}_{args.model}_trades.png",
        )
        print(f"✓ Trade analysis saved to {output_dir / f'{args.symbol}_{args.model}_trades.png'}")

    # 6. Generate HTML report
    plot_files = {
        "equity_curve": output_dir / f"{args.symbol}_{args.model}_equity.png",
        "drawdown": output_dir / f"{args.symbol}_{args.model}_drawdown.png",
        "returns_dist": output_dir / f"{args.symbol}_{args.model}_returns_dist.png",
        "monthly_heatmap": output_dir / f"{args.symbol}_{args.model}_monthly.png",
    }
    if len(result.trades) > 0:
        plot_files["trade_analysis"] = output_dir / f"{args.symbol}_{args.model}_trades.png"

    html_path = generate_html_report(
        result,
        metrics,
        args.model,
        args.symbol,
        plot_files=plot_files,
        output_path=output_dir / f"{args.symbol}_{args.model}_report.html",
    )
    print(f"✓ HTML report saved to {html_path}")

    print('='*70)
    print(f"\nAll plots and report saved to: {output_dir}/")
    print(f"Open report in browser: file://{html_path.absolute()}")
    print('='*70 + '\n')

    if args.show:
        import matplotlib.pyplot as plt
        plt.show()

    return 0


if __name__ == "__main__":
    sys.exit(main())
