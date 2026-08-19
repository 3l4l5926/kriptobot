import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


CONFIG = "config.json"

BASE_STRATEGY = "QuantumMomentumStrategy"

CANDIDATE_FILE = Path(
    "data/candidate_pairs.json"
)

PARAM_FILE = Path(
    "data/pair_params.json"
)

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

    minimal_roi = {{
        "0": 100.0
    }}

    stoploss = -0.99

    use_custom_stoploss = False
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
        "signals",

        "--cache",
        "none",

        "--backtest-directory",
        "data/backtests"
    ]

    print("")
    print(
        "BACKTEST:",
        pair
    )

    print(
        "TIMERANGE:",
        timerange
    )

    print(
        "PARAMS:",
        json.dumps(
            params
        )
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    output = (
        result.stdout
        +
        "\n"
        +
        result.stderr
    )

    print(
        output[-12000:]
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"Backtest başarısız: {pair}"
        )

    return output


def parse_metrics(output):

    metrics = {

        "trades": 0,

        "profit_factor": 0.0,

        "drawdown": 0.0,

        "profit_percent": 0.0
    }

    trade_patterns = [

        r"Total\s+trades\s*\|\s*(\d+)",

        r"Total\s+trades\s*[:|]\s*(\d+)",

        r"(\d+)\s+trades"
    ]

    for pattern in trade_patterns:

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


    pf_patterns = [

        r"Profit\s*Factor\s*\|\s*([0-9.]+)",

        r"Profit\s*Factor\s*[:|]\s*([0-9.]+)"
    ]

    for pattern in pf_patterns:

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


    profit_patterns = [

        r"Tot\s+Profit\s*%\s*\|\s*(-?[0-9.]+)",

        r"Tot\s+Profit\s*%\s*[:|]\s*(-?[0-9.]+)"
    ]

    for pattern in profit_patterns:

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


    dd_patterns = [

        r"Drawdown.*?\|\s*(-?[0-9.]+)\s*%",

        r"Drawdown.*?(-?[0-9.]+)\s*%"
    ]

    for pattern in dd_patterns:

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
                )

                / 100.0
            )

            break

    return metrics


def is_good(metrics):

    return (

        metrics["trades"]
        >=
        MIN_TRADES

        and

        metrics["profit_factor"]
        >=
        MIN_PROFIT_FACTOR

        and

        metrics["drawdown"]
        <=
        MAX_DRAWDOWN

        and

        metrics["profit_percent"]
        >
        0
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

    if not pairs:

        raise RuntimeError(
            "candidate_pairs.json boş!"
        )

    if not pair_params:

        raise RuntimeError(
            "pair_params.json boş!"
        )

    results = {}

    active_pairs = []

    print("")
    print("=" * 70)

    print(
        "WALK FORWARD TEST"
    )

    print(
        "TRAIN:",
        train_range
    )

    print(
        "TEST:",
        test_range
    )

    print(
        "PAIRS:",
        len(pairs)
    )

    print("=" * 70)


    for pair in pairs:

        params = pair_params.get(
            pair
        )

        if not params:

            print(
                f"SKIP {pair}: "
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

                active_pairs.append(
                    pair
                )

            print("")
            print(
                "RESULT:",
                pair
            )

            print(
                "TRADES:",
                metrics["trades"]
            )

            print(
                "PF:",
                metrics["profit_factor"]
            )

            print(
                "PROFIT:",
                metrics["profit_percent"]
            )

            print(
                "DD:",
                metrics["drawdown"]
            )

            print(
                "ACTIVE:",
                good
            )

        except Exception as e:

            print(
                f"ERROR {pair}: {e}"
            )

            results[pair] = {

                "train_timerange":
                    train_range,

                "test_timerange":
                    test_range,

                "params":
                    params,

                "error":
                    str(e),

                "active":
                    False,

                "updated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat()
            }


    save_json(
        RESULT_FILE,
        results
    )

    save_json(
        ACTIVE_FILE,
        {

            "pairs":
                active_pairs,

            "count":
                len(active_pairs),

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
        "ACTIVE COINS:",
        len(active_pairs)
    )

    print("=" * 70)

    for pair in active_pairs:

        print(
            "ACTIVE:",
            pair
        )


if __name__ == "__main__":
    main()
