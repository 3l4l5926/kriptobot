import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


CONFIG = "config.json"

STRATEGY = "QuantumMomentumStrategy"

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


TRAIN_DAYS = 90

TEST_DAYS = 30

MIN_TRADES = 30

MIN_PROFIT_FACTOR = 1.20

MAX_DRAWDOWN = 0.20


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
            indent=2
        )


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


def date_range():

    now = datetime.now(
        timezone.utc
    )

    test_end = now.date()

    test_start = (
        test_end
        -
        timedelta(
            days=TEST_DAYS
        )
    )

    train_start = (
        test_start
        -
        timedelta(
            days=TRAIN_DAYS
        )
    )

    return (
        train_start.strftime("%Y%m%d"),
        test_start.strftime("%Y%m%d"),
        test_end.strftime("%Y%m%d")
    )


def run_backtest(
    pair,
    timerange
):

    print(
        f"BACKTEST {pair} {timerange}"
    )

    command = [
        "freqtrade",
        "backtesting",

        "--config",
        CONFIG,

        "--strategy",
        STRATEGY,

        "--pairs",
        pair,

        "--timerange",
        timerange,

        "--export",
        "trades",

        "--cache",
        "none",

        "--backtest-directory",
        "data/backtests",
    ]

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

    if result.returncode != 0:

        print(output)

        raise RuntimeError(
            f"Backtest başarısız: {pair}"
        )

    return output


def parse_metrics(output):

    metrics = {
        "trades": 0,
        "profit_factor": 0,
        "drawdown": 1,
        "profit_percent": 0
    }

    # ---------------------------------------------------------
    # Trades
    # ---------------------------------------------------------

    match = re.search(
        r"(\d+)\s+trades",
        output,
        re.IGNORECASE
    )

    if match:

        metrics["trades"] = int(
            match.group(1)
        )

    # ---------------------------------------------------------
    # Profit factor
    # ---------------------------------------------------------

    match = re.search(
        r"Profit Factor.*?([0-9.]+)",
        output,
        re.IGNORECASE
    )

    if match:

        metrics["profit_factor"] = float(
            match.group(1)
        )

    # ---------------------------------------------------------
    # Profit %
    # ---------------------------------------------------------

    match = re.search(
        r"Tot Profit %.*?(-?[0-9.]+)",
        output,
        re.IGNORECASE
    )

    if match:

        metrics["profit_percent"] = float(
            match.group(1)
        )

    # ---------------------------------------------------------
    # Drawdown
    # ---------------------------------------------------------

    match = re.search(
        r"Drawdown.*?(-?[0-9.]+)\s*%",
        output,
        re.IGNORECASE
    )

    if match:

        metrics["drawdown"] = (
            float(match.group(1))
            /
            100.0
        )

    return metrics


def is_good(metrics):

    if metrics["trades"] < MIN_TRADES:
        return False

    if metrics["profit_factor"] < MIN_PROFIT_FACTOR:
        return False

    if metrics["drawdown"] > MAX_DRAWDOWN:
        return False

    if metrics["profit_percent"] <= 0:
        return False

    return True


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

    data = load_json(
        CANDIDATE_FILE,
        {"pairs": []}
    )

    pairs = data.get(
        "pairs",
        []
    )

    results = load_json(
        RESULT_FILE,
        {}
    )

    active_pairs = []

    print(
        "\n===================================="
    )

    print(
        "WALK FORWARD"
    )

    print(
        f"TRAIN : {train_range}"
    )

    print(
        f"TEST  : {test_range}"
    )

    print(
        "===================================="
    )

    for pair in pairs:

        try:

            # -------------------------------------------------
            # Önce parametrelerin mevcut olması gerekiyor.
            # Optimizer çalıştırılmadıysa bu coin atlanır.
            # -------------------------------------------------

            params = load_json(
                PARAM_FILE,
                {}
            ).get(pair)

            if not params:

                print(
                    f"{pair}: parametre yok, atlandı."
                )

                continue

            output = run_backtest(
                pair,
                test_range
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

            print(
                f"{pair}: "
                f"PF={metrics['profit_factor']} "
                f"Trades={metrics['trades']} "
                f"DD={metrics['drawdown']:.2%} "
                f"ACTIVE={good}"
            )

        except Exception as e:

            print(
                f"{pair} ERROR: {e}"
            )

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

    print(
        "\nAKTİF COINLER:"
    )

    for pair in active_pairs:

        print(pair)


if __name__ == "__main__":
    main()
