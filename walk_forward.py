import json
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


CONFIG = "config.json"
BASE_STRATEGY = "QuantumMomentumStrategy"

CANDIDATE_FILE = Path("data/candidate_pairs.json")
PARAM_FILE = Path("data/pair_params.json")
RESULT_FILE = Path("data/walk_forward_results.json")
ACTIVE_FILE = Path("data/active_pairs.json")

STRATEGY_DIR = Path("user_data/strategies")
RESULT_DIR = Path("user_data/backtest_results")

TEMP_STRATEGY = STRATEGY_DIR / "PairSpecificStrategy.py"

TRAIN_DAYS = 90
TEST_DAYS = 30

MIN_TRADES = 3
MIN_PROFIT_FACTOR = 1.20
MAX_DRAWDOWN = 0.20


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def get_dates():

    today = datetime.now(
        timezone.utc
    ).date()

    test_end = today

    test_start = (
        test_end -
        timedelta(days=TEST_DAYS)
    )

    train_start = (
        test_start -
        timedelta(days=TRAIN_DAYS)
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


def load_latest_backtest_metrics(strategy_name="PairSpecificStrategy"):
    """
    NOT: Eskiden bu bilgi freqtrade'in konsola bastığı özet tablo
    metninden regex ile çekiliyordu. Güncel freqtrade sürümleri
    (2025+) bu tabloyu artık ASCII '|' ile değil, 'rich' kütüphanesiyle
    Unicode kutu çizgileriyle basıyor ve satır başlıkları da değişti
    (ör. "Total trades" yerine "Total/Daily Avg Trades" gibi birleşik
    bir satır). Bu yüzden regex hiçbir zaman eşleşmiyordu, metrikler
    hep 0 kalıyordu ve is_good() hiçbir zaman True dönmüyordu.

    Bunun yerine, freqtrade'in "--export signals --backtest-directory"
    ile diske yazdığı yapılandırılmış sonucu (.last_result.json ->
    backtest-result-<ts>.zip içindeki JSON) doğrudan okuyoruz. Bu,
    konsol çıktısının formatından bağımsız ve çok daha güvenilir.
    """

    last_result_path = RESULT_DIR / ".last_result.json"

    if not last_result_path.exists():
        raise RuntimeError(
            "Backtest sonuç dosyası (.last_result.json) bulunamadı. "
            "freqtrade backtesting komutu sonuç export etmemiş olabilir."
        )

    with open(last_result_path, "r", encoding="utf-8") as f:
        latest = json.load(f)

    zip_name = latest.get("latest_backtest")

    if not zip_name:
        raise RuntimeError(
            ".last_result.json içinde 'latest_backtest' bulunamadı."
        )

    zip_path = RESULT_DIR / zip_name

    if not zip_path.exists():
        raise RuntimeError(
            f"Backtest sonuç zip dosyası yok: {zip_path}"
        )

    json_name = zip_path.stem + ".json"

    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(json_name) as jf:
            data = json.load(jf)

    strat_results = data.get("strategy", {}).get(strategy_name)

    if not strat_results:
        raise RuntimeError(
            f"'{strategy_name}' için sonuç bulunamadı "
            f"(mevcut anahtarlar: {list(data.get('strategy', {}).keys())})."
        )

    trades = strat_results.get("total_trades", 0)

    profit_factor = strat_results.get("profit_factor")
    if profit_factor is None:
        profit_factor = 0.0

    drawdown = strat_results.get(
        "max_drawdown_account",
        strat_results.get("max_drawdown", 0.0)
    )

    profit_percent = strat_results.get("profit_total", 0.0) * 100

    return {
        "trades": trades,
        "profit_factor": float(profit_factor),
        "drawdown": float(drawdown),
        "profit_percent": float(profit_percent)
    }


def is_good(metrics):

    return (
        metrics["trades"] >= MIN_TRADES
        and
        metrics["profit_factor"] >= MIN_PROFIT_FACTOR
        and
        metrics["drawdown"] <= MAX_DRAWDOWN
        and
        metrics["profit_percent"] > 0
    )


def run_backtest(pair, timerange, params):

    create_pair_strategy(params)

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True
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

        "--backtest-directory",
        str(RESULT_DIR),

        "--cache",
        "none"
    ]

    print("")
    print("=" * 70)
    print("BACKTEST")
    print("PAIR:", pair)
    print("TIMERANGE:", timerange)
    print(
        "PARAMS:",
        json.dumps(params)
    )
    print("=" * 70)

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

    print(output[-15000:])

    if result.returncode != 0:

        raise RuntimeError(
            f"Backtest başarısız: {pair}"
        )

    return load_latest_backtest_metrics()


def main():

    train_start, test_start, test_end = (
        get_dates()
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
    print("WALK FORWARD TEST")
    print("=" * 70)
    print("TRAIN:", train_range)
    print("TEST :", test_range)
    print("PAIRS:", len(pairs))
    print("=" * 70)

    for pair in pairs:

        params = pair_params.get(pair)

        if not params:

            print(
                f"SKIP {pair}: parametre yok."
            )

            continue

        try:

            metrics = run_backtest(
                pair,
                test_range,
                params
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
                active_pairs.append(pair)

            print("")
            print("RESULT:", pair)
            print("TRADES:", metrics["trades"])
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

                "metrics": {
                    "trades": 0,
                    "profit_factor": 0.0,
                    "drawdown": 1.0,
                    "profit_percent": 0.0
                },

                "active": False,

                "error": str(e),

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
            "pairs": active_pairs,
            "count": len(active_pairs),
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
        "ACTIVE PAIRS:",
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
