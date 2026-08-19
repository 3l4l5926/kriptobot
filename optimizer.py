import json
import re
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

EPOCHS = 250


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

    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with open(
        temp,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2
        )

    temp.replace(path)


def extract_params(text):

    # Freqtrade JSON çıktısından
    # params bölümünü yakalamaya çalış.

    matches = re.findall(
        r'"params"\s*:\s*(\{.*?\})',
        text,
        flags=re.DOTALL
    )

    for match in reversed(matches):

        try:

            params = json.loads(match)

            if isinstance(params, dict):

                return params

        except Exception:

            pass

    return None


def normalize_params(params):

    result = DEFAULT_PARAMS.copy()

    if not params:
        return result

    # buy
    buy = params.get(
        "buy",
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

    # sell
    sell = params.get(
        "sell",
        {}
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


def optimize_pair(
    pair,
    train_timerange
):

    print(
        f"\n{'=' * 70}"
    )

    print(
        f"OPTIMIZE: {pair}"
    )

    print(
        f"TRAIN: {train_timerange}"
    )

    print(
        f"{'=' * 70}"
    )

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
        train_timerange,

        "--epochs",
        str(EPOCHS),

        "--spaces",
        "buy",
        "sell",

        "--hyperopt-loss",
        "SharpeHyperOptLossDaily",

        "--print-json",

        "--random-state",
        "42",

        "-j",
        "-1",
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
            f"Hyperopt başarısız: {pair}"
        )

    params = extract_params(
        output
    )

    if params is None:

        print(output)

        raise RuntimeError(
            f"Hyperopt parametreleri "
            f"okunamadı: {pair}"
        )

    return normalize_params(
        params
    )


def main():

    train_timerange = None

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--timerange",
        required=True
    )

    parser.add_argument(
        "--pair"
    )

    args = parser.parse_args()

    train_timerange = args.timerange

    candidate_data = load_json(
        CANDIDATE_FILE,
        {"pairs": []}
    )

    pairs = candidate_data.get(
        "pairs",
        []
    )

    if args.pair:

        pairs = [
            args.pair
        ]

    if not pairs:

        raise RuntimeError(
            "Taranacak coin bulunamadı."
        )

    pair_params = load_json(
        PARAM_FILE,
        {}
    )

    history = load_json(
        HISTORY_FILE,
        []
    )

    for pair in pairs:

        try:

            params = optimize_pair(
                pair,
                train_timerange
            )

            pair_params[pair] = params

            history.append({
                "pair": pair,
                "train_timerange":
                    train_timerange,
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

            print(
                f"{pair} PARAMETRELERİ:"
            )

            print(
                json.dumps(
                    params,
                    indent=2
                )
            )

        except Exception as e:

            print(
                f"{pair} başarısız: {e}"
            )

    print(
        "\nOPTİMİZASYON TAMAMLANDI."
    )


if __name__ == "__main__":
    main()
