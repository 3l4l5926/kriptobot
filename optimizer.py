import argparse
import json
import subprocess
from pathlib import Path


CONFIG = "config.json"
STRATEGY = "QuantumMomentumStrategy"

CANDIDATE_FILE = Path("data/candidate_pairs.json")
PARAM_FILE = Path("data/pair_params.json")
HISTORY_FILE = Path("data/optimization_history.json")
ERROR_FILE = Path("data/optimization_errors.json")

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


def extract_json_objects(text):

    """
    Freqtrade --print-json çıktısından JSON nesnelerini bulur.
    """

    results = []

    lines = text.splitlines()

    for line in lines:

        line = line.strip()

        if not line.startswith("{"):
            continue

        try:
            obj = json.loads(line)
            results.append(obj)
        except Exception:
            continue

    return results


def normalize_params(raw_params):

    """
    Freqtrade 2026.x --print-json çıktısı:

    {
        "params": {
            "buy_rsi": ...,
            "short_rsi": ...,
            "trend_adx": ...,
            "sl_multiplier": ...,
            "tp_multiplier": ...
        }
    }

    şeklindedir.

    Hem düz hem de eski nested formatı destekliyoruz.
    """

    result = DEFAULT_PARAMS.copy()

    if not isinstance(raw_params, dict):
        return None

    # ---------------------------------------------------------
    # Yeni / güncel Freqtrade formatı
    # ---------------------------------------------------------

    direct_keys = [
        "buy_rsi",
        "short_rsi",
        "trend_adx",
        "sl_multiplier",
        "tp_multiplier"
    ]

    found = False

    for key in direct_keys:

        if key in raw_params:

            result[key] = raw_params[key]
            found = True

    # ---------------------------------------------------------
    # Eski nested format desteği
    # ---------------------------------------------------------

    buy = raw_params.get("buy", {})

    sell = raw_params.get("sell", {})

    if isinstance(buy, dict):

        for key in [
            "buy_rsi",
            "short_rsi",
            "trend_adx"
        ]:

            if key in buy:

                result[key] = buy[key]
                found = True

    if isinstance(sell, dict):

        for key in [
            "sl_multiplier",
            "tp_multiplier"
        ]:

            if key in sell:

                result[key] = sell[key]
                found = True

    if not found:
        return None

    # Tipleri güvenli hale getir

    try:

        result["buy_rsi"] = int(
            result["buy_rsi"]
        )

        result["short_rsi"] = int(
            result["short_rsi"]
        )

        result["trend_adx"] = int(
            result["trend_adx"]
        )

        result["sl_multiplier"] = float(
            result["sl_multiplier"]
        )

        result["tp_multiplier"] = float(
            result["tp_multiplier"]
        )

    except Exception:

        return None

    return result


def run_hyperopt(pair, timerange):

    print("")
    print("=" * 70)
    print(f"HYPEROPT: {pair}")
    print(f"TRAIN: {timerange}")
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

        "--min-trades",
        "1",

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
        + "\n"
        + result.stderr
    )

    print(output[-10000:])

    if result.returncode != 0:

        raise RuntimeError(
            f"Freqtrade Hyperopt başarısız: {pair}"
        )

    json_objects = extract_json_objects(
        result.stdout
    )

    if not json_objects:

        # Bazı durumlarda JSON stderr'e düşebilir.
        json_objects = extract_json_objects(
            output
        )

    best_params = None

    # Son JSON nesnelerinden başlayarak ara.
    for obj in reversed(json_objects):

        if not isinstance(obj, dict):
            continue

        params = obj.get("params")

        if isinstance(params, dict):

            normalized = normalize_params(
                params
            )

            if normalized is not None:

                best_params = normalized
                break

    if best_params is None:

        raise RuntimeError(
            f"{pair}: Hyperopt sonucu "
            "okunamadı."
        )

    return best_params


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
    print("=" * 70)
    print(
        f"Optimize edilecek coin: {len(pairs)}"
    )
    print(
        f"Eğitim dönemi: {args.timerange}"
    )
    print("=" * 70)

    pair_params = {}

    history = []

    errors = []

    successful = 0
    failed = 0

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

            successful += 1

            print("")
            print(
                f"✅ {pair} BAŞARILI"
            )

            print(
                json.dumps(
                    params,
                    indent=2,
                    ensure_ascii=False
                )
            )

            # Her başarılı coin sonrasında kaydet.
            save_json(
                PARAM_FILE,
                pair_params
            )

            save_json(
                HISTORY_FILE,
                history
            )

        except Exception as e:

            failed += 1

            error = {
                "pair": pair,
                "error": str(e)
            }

            errors.append(error)

            print("")
            print(
                f"❌ {pair} BAŞARISIZ"
            )

            print(
                str(e)
            )

    # Hataları kaydet

    if errors:

        save_json(
            ERROR_FILE,
            errors
        )

    # Özet

    print("")
    print("=" * 70)
    print("HYPEROPT ÖZET")
    print("=" * 70)

    print(
        f"Toplam    : {len(pairs)}"
    )

    print(
        f"Başarılı  : {successful}"
    )

    print(
        f"Başarısız : {failed}"
    )

    # ---------------------------------------------------------
    # Güvenlik kontrolü:
    # Bütün coinler aynı DEFAULT_PARAMS ise
    # sistemi başarılı kabul etme.
    # ---------------------------------------------------------

    if successful == 0:

        raise RuntimeError(
            "HİÇBİR COIN İÇİN HYPEROPT BAŞARILI OLMADI!"
        )

    unique_params = {
        json.dumps(
            value,
            sort_keys=True
        )
        for value in pair_params.values()
    }

    print(
        f"Farklı parametre seti: "
        f"{len(unique_params)}"
    )

    if len(unique_params) == 1:

        only_params = next(
            iter(pair_params.values())
        )

        if only_params == DEFAULT_PARAMS:

            raise RuntimeError(
                "DİKKAT: Tüm coinler "
                "DEFAULT_PARAMS kullanıyor. "
                "Hyperopt sonucu alınamadı."
            )

    print("")
    print(
        "✅ HYPEROPT TAMAMLANDI"
    )

    print("")
    print(
        "Coin bazlı parametreler:"
    )

    for pair, params in pair_params.items():

        print(
            f"{pair}: "
            f"RSI={params['buy_rsi']}/"
            f"{params['short_rsi']} | "
            f"ADX={params['trend_adx']} | "
            f"SL={params['sl_multiplier']} | "
            f"TP={params['tp_multiplier']}"
        )


if __name__ == "__main__":
    main()
