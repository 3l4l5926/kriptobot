import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


CONFIG = "config.json"
STRATEGY = "QuantumMomentumStrategy"

CANDIDATE_FILE = Path("data/candidate_pairs.json")
PARAM_FILE = Path("data/pair_params.json")

RESULT_FILE = Path(
    "data/walk_forward_results.json"
)

ACTIVE_FILE = Path(
    "data/active_pairs.json"
)

STRATEGY_DIR = Path(
    "user_data/strategies"
)

TEMP_STRATEGY = (
    STRATEGY_DIR /
    "PairSpecificStrategy.py"
)


TRAIN_DAYS = 90
TEST_DAYS = 30

MIN_TRADES = 3
MIN_PROFIT_FACTOR = 1.20
MAX_DRAWDOWN = 0.20


def load_json(path, default):

    if not path.exists():
        return default

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return default


def save_json(path, data):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def date_range():

    today = datetime.now(
        timezone.utc
    ).date()

    test_end = today

    test_start = (
        test_end -
        timedelta(
            days=TEST_DAYS
        )
    )

    train_start = (
        test_start -
        timedelta(
            days=TRAIN_DAYS
        )
    )

    return (
        train_start.strftime("%Y%m%d"),
        test_start.strftime("%Y%m%d"),
        test_end.strftime("%Y%m%d")
    )


def create_pair_strategy(params):

    STRATEGY_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    code = f'''
from freqtrade.strategy import (
    IntParameter,
    DecimalParameter
)

from QuantumMomentumStrategy import (
    QuantumMomentumStrategy
)


class PairSpecificStrategy(
    QuantumMomentumStrategy
):

    buy_rsi = IntParameter(
        35,
        55,
        default={int(params["buy_rsi"])},
        space="buy"
    )

    short_rsi = IntParameter(
        45,
        65,
        default={int(params["short_rsi"])},
        space="buy"
    )

    trend_adx = IntParameter(
        20,
        40,
        default={int(params["trend_adx"])},
        space="buy"
    )

    sl_multiplier = DecimalParameter(
        1.2,
        4.0,
        decimals=3,
        default={float(params["sl_multiplier"])},
        space="sell"
    )

    tp_multiplier = DecimalParameter(
        2.5,
        8.0,
        decimals=3,
        default={float(params["tp_multiplier"])},
        space="sell"
    )
'''

    with open(
        TEMP_STRATEGY,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(code)


def run_backtest(
    pair,
    timerange,
    params
):

    create_pair_strategy(
        params
    )

    command = [

        "freqtrade",
        "backtesting",

        "--config",
        CONFIG,

        "--strategy",
        "PairSpecificStrategy",

        "--strategy-path",
        str(STRATEGY_DIR),

        "--pairs",
        pair,

        "--timerange",
        timerange,

        "--export",
        "trades",

        "--cache",
        "none",

        "--backtest-directory",
        "data/backtests"
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    output = (
        result.stdout
        + "\n"
        + result.stderr
    )

    print(
        output[-8000:]
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"OOS backtest başarısız: {pair}"
        )

    return output


def parse_metrics(output):

    metrics = {
        "trades": 0,
        "profit_factor": 0.0,
        "drawdown": 0.0,
        "profit_percent": 0.0
    }

    patterns = [

        r"Total\s+trades\s*\|\s*(\d+)",

        r"Total\s+trades\s*[:|]\s*(\d+)",

        r"(\d+)\s+trades"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            output,
            re.IGNORECASE
        )

        if match:

            metrics["trades"] = int(
                match.group(1)
            )

            break


    patterns = [

        r"Profit\s*Factor\s*\|\s*([0-9.]+)",

        r"Profit\s*Factor\s*[:|]\s*([0-9.]+)"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            output,
            re.IGNORECASE
        )

        if match:

            metrics["profit_factor"] = float(
                match.group(1)
            )

            break


    patterns = [

        r"Tot\s+Profit\s*%\s*\|\s*(-?[0-9.]+)",

        r"Tot\s+Profit\s*%\s*[:|]\s*(-?[0-9.]+)"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            output,
            re.IGNORECASE
        )

        if match:

            metrics["profit_percent"] = float(
                match.group(1)
            )

            break


    patterns = [

        r"Drawdown.*?\|\s*(-?[0-9.]+)\s*%",

        r"Drawdown.*?(-?[0-9.]+)\s*%"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            output,
            re.IGNORECASE
        )

        if match:

            metrics["drawdown"] = (
                abs(
                    float(
                        match.group(1)
                    )
                ) / 100
            )

            break

    return metrics


def is_good(metrics):

    return (

        metrics["trades"] >= MIN_TRADES

        and

        metrics["profit_factor"]
        >= MIN_PROFIT_FACTOR

        and

        metrics["drawdown"]
        <= MAX_DRAWDOWN

        and

        metrics["profit_percent"]
        > 0

    )


def main():

    train_start, test_start, test_end = (
        date_range()
    )

    train_range = (
        f"{train_start}-{test_start}"
    )

    test_range = (
        f"{test_start}-{test_end}"
    )

    candidate_data = load_json(
        CANDIDATE_FILE,
        {}
    )

    pairs = candidate_data.get(
        "pairs",
        []
    )

    pair_params = load_json(
        PARAM_FILE,
        {}
    )

    results = {}
    active = []

    print("")
    print("=" * 70)
    print("WALK FORWARD")
    print("=" * 70)

    print(
        f"TRAIN : {train_range}"
    )

    print(
        f"TEST  : {test_range}"
    )

    print(
        f"COINS : {len(pairs)}"
    )

    print("=" * 70)


    for pair in pairs:

        params = pair_params.get(
            pair
        )

        if not params:

            print(
                f"⚠️ {pair}: "
                "parametre yok."
            )

            continue

        try:

            output = run_backtest(
                pair,
                test_range,
                params
            )

            metrics = parse_metrics(
                output
            )

            good = is_good(
                metrics
            )

            results[pair] = {

                "train_timerange":
                    train_range,

                "test_timerange":
                    test_range,

                "params":
                    params,

                "metrics":
                    metrics,

                "active":
                    good,

                "updated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat()
            }

            if good:

                active.append(
                    pair
                )

            print("")
            print(
                f"{pair}: "
                f"TRADES={metrics['trades']} "
                f"PF={metrics['profit_factor']} "
                f"PROFIT={metrics['profit_percent']}% "
                f"DD={metrics['drawdown']:.2%} "
                f"ACTIVE={good}"
            )

        except Exception as e:

            print(
                f"❌ {pair}: {e}"
            )


    save_json(
        RESULT_FILE,
        results
    )

    save_json(
        ACTIVE_FILE,
        {
            "pairs": active,
            "count": len(active),
            "updated_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }
    )


    if TEMP_STRATEGY.exists():

        TEMP_STRATEGY.unlink()


    print("")
    print("=" * 70)
    print(
        f"ACTIVE COINS: {len(active)}"
    )
    print("=" * 70)

    for pair in active:

        print(
            f"✅ {pair}"
        )


if __name__ == "__main__":
    main()
