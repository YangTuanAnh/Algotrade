import yaml
from yaml import Loader
import argparse
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input_path", help="-i config/insample.yaml")
    parser.add_argument("-o", "--output_dir", default="logs", help="-o logs")
    args = parser.parse_args()

    with open(args.input_path, "r") as f:
        config = yaml.load(f, Loader=Loader)

    log_time = str(int(datetime.now().timestamp()))
    log_dir = os.path.join(args.output_dir, log_time)
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, "results.log"), level=logging.INFO
    )

    # Get signals (MACD)
    df = pd.read_csv(config["tick_path"])
    k = df["close"].ewm(span=12, adjust=False, min_periods=12).mean()
    d = df["close"].ewm(span=26, adjust=False, min_periods=26).mean()
    macd = k - d

    macd_s = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    macd_h = macd - macd_s

    # Declare long, short
    long = (macd_h.shift(1) < 0) & (macd_h > 0)
    short = (macd_h.shift(1) > 0) & (macd_h < 0)

    position = pd.Series(np.nan, index=df.index)

    position[long] = 1
    position[short] = -1

    # Evaluate
    inventory = position.ffill().fillna(0).astype(int)
    trade = inventory.diff().fillna(inventory)
    cash_flow = trade * df["close"]

    buy_cost = np.where(trade > 0, trade * df["close"] * config["buy_fee"], 0)
    sell_cost = np.where(trade < 0, -trade * df["close"] * config["sell_fee"], 0)
    fee = buy_cost + sell_cost

    # Assets after cash flow, fee costs and holdings
    cash = config["initial_asset"] - cash_flow.cumsum() - fee.cumsum()
    holdings = inventory * df["close"]
    asset = cash + holdings

    # Sharpe
    returns = asset.pct_change().dropna()
    excess = returns - config["risk_free"] / config["periods_per_year"]

    sharpe = np.sqrt(config["periods_per_year"]) * excess.mean() / excess.std(ddof=1)

    # Sortino
    downside = excess[excess < 0]
    sortino = np.sqrt(config["periods_per_year"]) * excess.mean() / downside.std(ddof=1)

    # Maximum drawdown
    cummax = asset.cummax()
    drawdown = asset / cummax - 1
    mdd = drawdown.min()

    # Validate against VNINDEX Benchmark
    vnindex_df = pd.read_csv(config["vnindex_path"])
    benchmark_returns = vnindex_df["close"].pct_change().fillna(0)
    benchmark = config["initial_asset"] * (1 + benchmark_returns).cumprod()
    active_return = returns - benchmark_returns

    information_ratio = (
        np.sqrt(config["periods_per_year"])
        * active_return.mean()
        / active_return.std(ddof=1)
    )

    logger.info(f"Inital assets: {(config['initial_asset'] * 1e6):.3f}")
    logger.info(f"Final assets: {(asset.iloc[-1] * 1e6):.3f}")
    logger.info(f"Total fee: {(fee.sum() * 1e6):.3f}")
    logger.info(f"Sharpe : {sharpe:.3f}")
    logger.info(f"Sortino: {sortino:.3f}")
    logger.info(f"MDD    : {mdd:.2%}")
    logger.info(f"Information Ratio: {information_ratio:.3f}")

    # Plot
    fig, ax = plt.subplots(3, 1, figsize=(12, 8), sharex=True)

    long_idx = np.where(long)[0]
    short_idx = np.where(short)[0]
    ax[0].plot(df["close"], label="Close")
    ax[0].scatter(
        long_idx, df["close"].iloc[long_idx], marker="^", color="green", label="Long"
    )
    ax[0].scatter(
        short_idx, df["close"].iloc[short_idx], marker="v", color="red", label="Short"
    )
    ax[0].grid("on")
    ax[0].legend()

    ax[1].plot(macd, label="MACD")
    ax[1].plot(macd_s, label="Signal")
    ax[1].bar(range(len(macd_h)), macd_h, alpha=0.4, label="Histogram")
    ax[1].axhline(0, color="black", linewidth=0.8)
    ax[1].grid("on")
    ax[1].legend()

    ax[2].plot(asset, label="Portfolio")
    ax[2].plot(benchmark, label="VNINDEX")
    ax[2].grid("on")
    ax[2].legend()

    fig.savefig(os.path.join(log_dir, "plot.png"), dpi=200)
    print("Saved backtest results at", log_dir)
