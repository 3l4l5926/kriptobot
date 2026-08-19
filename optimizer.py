import argparse
import json
import subprocess
from pathlib import Path


CONFIG = "config.json"

STRATEGY = "QuantumMomentumStrategy"

CANDIDATE_FILE = Path(
    "data/candidate_pairs.json"
)

PARAM_FILE = Path(
    "data/pair_params.json"
)

HISTORY_FILE = Path(
    "data/optimization_history.json"
)

# İlk test.
# Sistem çalışınca 100 -> 250 -> 500 yapabiliriz.
EPOCHS = 50


DEFAULT_PARAMS = {
    "buy_rsi": 45,
    "short_rsi": 55,
    "trend_adx": 30,
    "sl_multiplier": 2.2,
    "tp_multiplier": 5.0,
}


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
            indent=2
        )


def run_hyperopt(
    pair,
    timerange
):

    print("")
    print("=" * 70)
    print(
        f"HYPEROPT: {pair}"
    )
    print(
        f"TRAIN: {timerange}"
    )
    print("=" * 70)

    command = [
        "freqtrade",
        "hyperopt",

        "--config",
        CONFIG,

        "--strategy",
        STRATEGY,

        "--pairs",
        pair,

        "--timerange",
        timerange,

        "--epochs",
        str(EPOCHS),

        "--spaces",
        "buy",
        "sell",

        "--hyperopt-loss",
        "SharpeHyperOptLossDaily",

        "--random-state",
        "42",

        "--print-json",

        "-j",
        "2",
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

    print(output[-6000:])

    if result.returncode != 0:

        raise RuntimeError(
            f"Hyperopt başarısız: {pair}"
        )

    # ---------------------------------------------------------
    # Hyperopt'ın ürettiği JSON'u bul.
    # ---------------------------------------------------------

    best_params = None

    for line in output.splitlines():

        line = line.strip()

        if not line.startswith("{"):
            continue

        try:

            data = json.loads(line)

            if "params" in data:

                best_params = data["params"]

        except Exception:
            continue

    if not best_params:

        raise RuntimeError(
            f"{pair}: Hyperopt sonucu bulunamadı."
        )

    return normalize_params(
        best_params
    )


def normalize_params(params):

    result = DEFAULT_PARAMS.copy()

    buy = params.get(
        "buy",
        {}
    )

    sell = params.get(
        "sell",
        {}
    )

    if "buy_rsi" in buy:

        result["buy_rsi"] = int(
            buy["buy_rsi"]
        )

    if "short_rsi" in buy:

        result["short_rsi"] = int(
            buy["short_rsi"]
        )

    if "trend_adx" in buy:

        result["trend_adx"] = int(
            buy["trend_adx"]
        )

    if "sl_multiplier" in sell:

        result["sl_multiplier"] = float(
            sell["sl_multiplier"]
        )

    if "tp_multiplier" in sell:

        result["tp_multiplier"] = float(
            sell["tp_multiplier"]
        )

    return result


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--timerange",
        required=True
    )

    args = parser.parse_args()

    candidate_data = load_json(
        CANDIDATE_FILE,
        {}
    )

    pairs = candidate_data.get(
        "pairs",
        []
    )

    if not pairs:

        raise RuntimeError(
            "candidate_pairs.json boş!"
        )

    print("")
    print(
        f"Optimize edilecek coin: "
        f"{len(pairs)}"
    )

    pair_params = load_json(
        PARAM_FILE,
        {}
    )

    history = load_json(
        HISTORY_FILE,
        []
    )

    successful = 0
    failed = 0

    errors = []

    for pair in pairs:

        try:

            params = run_hyperopt(
                pair,
                args.timerange
            )

            pair_params[pair] = params

            history.append({
                "pair": pair,
                "train_timerange":
                    args.timerange,
                "params": params
            })

            save_json(
                PARAM_FILE,
                pair_params
            )

            save_json(
                HISTORY_FILE,
                history
            )

            successful += 1

            print("")
            print(
                f"✅ {pair} BAŞARILI"
            )

            print(
                json.dumps(
                    params,
                    indent=2
                )
            )

        except Exception as e:

            failed += 1

            errors.append({
                "pair": pair,
                "error": str(e)
            })

            print("")
            print(
                f"❌ {pair} BAŞARISIZ"
            )

            print(e)

    print("")
    print("=" * 70)
    print("HYPEROPT ÖZET")
    print("=" * 70)

    print(
        f"Toplam : {len(pairs)}"
    )

    print(
        f"Başarılı: {successful}"
    )

    print(
        f"Başarısız: {failed}"
    )

    # ---------------------------------------------------------
    # Hiçbir coin optimize olmadıysa workflow kesinlikle
    # başarısız olsun.
    # ---------------------------------------------------------

    if successful == 0:

        save_json(
            Path(
                "data/optimization_errors.json"
            ),
            errors
        )

        raise RuntimeError(
            "HİÇBİR COIN İÇİN HYPEROPT BAŞARILI OLMADI!"
        )

    # Bazı coinler hata verdi ama bazıları başarılıysa
    # sonucu yine kaydet.
    if errors:

        save_json(
            Path(
                "data/optimization_errors.json"
            ),
            errors
        )

        print(
            "⚠️ Bazı coinler optimize edilemedi."
        )

    print("")
    print(
        "OPTİMİZASYON TAMAMLANDI."
    )


if __name__ == "__main__":
    main()
