import optuna
import logging
import argparse
import pandas as pd
import numpy as np
import yaml
from yaml import Loader
from datetime import datetime
import os
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

    # Get MACD
    df = pd.read_csv(config["tick_path"])
    k = df["close"].ewm(span=12, adjust=False, min_periods=12).mean()
    d = df["close"].ewm(span=26, adjust=False, min_periods=26).mean()
    macd = k - d

    macd_s = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    macd_h = macd - macd_s

    # Get RSI (https://stackoverflow.com/questions/57006437/calculate-rsi-indicator-from-pandas-dataframe)
    change = df["close"].diff(1)
    gain = change.mask(change < 0, 0.0)
    loss = -change.mask(change > 0, -0.0)

    def rma(x, n):
        """Running moving average"""
        a = np.full_like(x, np.nan)
        a[n] = x[1:n+1].mean()
        for i in range(n+1, len(x)):
            a[i] = (a[i-1] * (n - 1) + x[i]) / n
        return a

    avg_gain = rma(gain.to_numpy(), 14)
    avg_loss = rma(loss.to_numpy(), 14)

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    def objective(trial):
        rsi_oversold = trial.suggest_int("rsi_oversold", 0, 100, step=5)
        rsi_overbought = trial.suggest_int("rsi_overbought", 0, 100, step=5)

        # Declare long, short
        long = (macd_h.shift(1) < 0) & (macd_h > 0) & (rsi <= rsi_oversold)
        short = (macd_h.shift(1) > 0) & (macd_h < 0) & (rsi >= rsi_overbought)

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
        return sharpe, sortino, mdd, information_ratio, fee.sum(), asset.iloc[-1]

    search_space = {
        "rsi_oversold": range(0, 101, 5), 
        "rsi_overbought": range(0, 101, 5)
    }
    study = optuna.create_study(
        directions=[
            "maximize",
            "maximize",
            "maximize",
            "maximize",
            "minimize",
            "maximize",
        ],
        sampler=optuna.samplers.GridSampler(search_space)
    )

    study.optimize(objective)

    logger.info(f"Number of finished trials: {len(study.trials)}")

    completed = [t for t in study.trials if t.values is not None]
    completed.sort(key=lambda t: t.values[0], reverse=True)  # Sharpe

    logger.info("Top 10 by Sharpe")
    for i, trial in enumerate(completed[:10], 1):
        logger.info(
            f"{i:2d}. "
            f"OS={trial.params['rsi_oversold']:3d} "
            f"OB={trial.params['rsi_overbought']:3d} | "
            f"Sharpe={trial.values[0]:7.4f} "
            f"Sortino={trial.values[1]:7.4f} "
            f"MDD={trial.values[2]:7.4f} "
            f"IR={trial.values[3]:7.4f} "
            f"Fee={trial.values[4]:10.2f} "
            f"Asset={trial.values[5]:10.2f}"
        )

    print("Saved Optuna results at", log_dir)