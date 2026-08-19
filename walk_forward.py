import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


CONFIG = "config.json"
BASE_STRATEGY = "QuantumMomentumStrategy"

CANDIDATE_FILE = Path("data/candidate_pairs.json")
PARAM_FILE = Path("data/pair_params.json")
RESULT_FILE = Path("data/walk_forward_results.json")
ACTIVE_FILE = Path("data/active_pairs.json")

STRATEGY_DIR = Path("user_data/strategies")
TEMP_STRATEGY_FILE = STRATEGY_DIR / "PairSpecificStrategy.py"

TRAIN_DAYS = 90
TEST_DAYS = 30

MIN_TRADES = 10
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
            indent=2,
            ensure_ascii=False
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


def create_pair_strategy(params):

    """
    Optimizer tarafından bulunan parametreleri
    gerçekten backtest sırasında kullanacak
    geçici strateji oluşturur.
    """

    STRATEGY_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    buy_rsi = int(
        params["buy_rsi"]
    )

    short_rsi = int(
        params["short_rsi"]
    )

    trend_adx = int(
        params["trend_adx"]
    )

    sl_multiplier = float(
        params["sl_multiplier"]
    )

    tp_multiplier = float(
        params["tp_multiplier"]
    )

    code = f'''
from freqtrade.strategy import IntParameter, DecimalParameter

from QuantumMomentumStrategy import QuantumMomentumStrategy


class PairSpecificStrategy(QuantumMomentumStrategy):

    buy_rsi = IntParameter(
        40,
        70,
        default={buy_rsi},
        space="buy"
    )

    short_rsi = IntParameter(
        30,
        70,
        default={short_rsi},
        space="buy"
    )

    trend_adx = IntParameter(
        20,
        45,
        default={trend_adx},
        space="buy"
    )

    sl_multiplier = DecimalParameter(
        1.0,
        4.0,
        default={sl_multiplier},
        space="sell"
    )

    tp_multiplier = DecimalParameter(
        2.0,
        7.0,
        default={tp_multiplier},
        space="sell"
    )
'''

    with open(
        TEMP_STRATEGY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(code)


def run_backtest(
    pair,
    timerange,
    params
):

    print("")
    print("=" * 70)
    print(
        f"OOS BACKTEST: {pair}"
    )
    print(
        f"TIMERANGE: {timerange}"
    )

    print(
        "PARAMETRELER:"
    )

    print(
        json.dumps(
            params,
            indent=2
        )
    )

    print("=" * 70)

    # ---------------------------------------------------------
    # Coin'e özel strateji oluştur
    # ---------------------------------------------------------

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
        +
        "\n"
        +
        result.stderr
    )

    print(
        output[-8000:]
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

    # ---------------------------------------------------------
    # Önce Total trades
    # ---------------------------------------------------------

    patterns = [
        r"Total\s+trades\s*[:|]\s*(\d+)",
        r"(\d+)\s+trades",
        r"Trades\s*[:|]\s*(\d+)"
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

    # ---------------------------------------------------------
    # Profit Factor
    # ---------------------------------------------------------

    patterns = [
        r"Profit\s*Factor\s*[:|]\s*([0-9.]+)",
        r"Profit Factor.*?([0-9]+\.[0-9]+)"
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

    # ---------------------------------------------------------
    # Total Profit %
    # ---------------------------------------------------------

    patterns = [
        r"Tot\s+Profit\s*%\s*[:|]\s*(-?[0-9.]+)",
        r"Total\s+profit\s*%\s*[:|]\s*(-?[0-9.]+)",
        r"Total profit.*?(-?[0-9.]+)\s*%"
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

    # ---------------------------------------------------------
    # Drawdown %
    # ---------------------------------------------------------

    patterns = [
        r"Drawdown.*?(-?[0-9.]+)\s*%",
        r"Max Drawdown.*?(-?[0-9.]+)\s*%"
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
                )
                /
                100.0
            )

            break

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

    candidate_data = load_json(
        CANDIDATE_FILE,
        {"pairs": []}
    )

    pairs = candidate_data.get(
        "pairs",
        []
    )

    if not pairs:

        raise RuntimeError(
            "candidate_pairs.json boş!"
        )

    pair_params = load_json(
        PARAM_FILE,
        {}
    )

    results = {}

    active_pairs = []

    print("")
    print("=" * 70)
    print("WALK-FORWARD TEST")
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

        try:

            params = pair_params.get(
                pair
            )

            if not params:

                print(
                    f"❌ {pair}: "
                    "Parametre bulunamadı."
                )

                continue

            # -------------------------------------------------
            # Coin'e özel OOS backtest
            # -------------------------------------------------

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
                f"{pair}:"
            )

            print(
                f"Trades = "
                f"{metrics['trades']}"
            )

            print(
                f"PF = "
                f"{metrics['profit_factor']}"
            )

            print(
                f"Profit = "
                f"{metrics['profit_percent']}%"
            )

            print(
                f"DD = "
                f"{metrics['drawdown']:.2%}"
            )

            print(
                f"ACTIVE = {good}"
            )

        except Exception as e:

            print("")
            print(
                f"❌ {pair} ERROR:"
            )

            print(
                str(e)
            )

    # ---------------------------------------------------------
    # Sonuçları kaydet
    # ---------------------------------------------------------

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

    print("")
    print("=" * 70)
    print("WALK-FORWARD SONUCU")
    print("=" * 70)

    print(
        f"Test edilen: {len(results)}"
    )

    print(
        f"Aktif coin: {len(active_pairs)}"
    )

    if active_pairs:

        print("")
        print(
            "AKTİF COINLER:"
        )

        for pair in active_pairs:

            print(
                f"✅ {pair}"
            )

    else:

        print("")
        print(
            "⚠️ Hiçbir coin aktif kriterlerini karşılamadı."
        )

    # ---------------------------------------------------------
    # Geçici stratejiyi temizle
    # ---------------------------------------------------------

    if TEMP_STRATEGY_FILE.exists():

        TEMP_STRATEGY_FILE.unlink()


if __name__ == "__main__":

    main()
