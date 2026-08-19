import json
from pathlib import Path

import ccxt


OUTPUT_FILE = Path(
    "data/candidate_pairs.json"
)

MAX_PAIRS = 80

MIN_QUOTE_VOLUME = 5_000_000


def main():

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Gate Futures taranıyor...")

    exchange = ccxt.gateio({
        "enableRateLimit": True,
        "options": {
            "defaultType": "swap"
        }
    })

    markets = exchange.load_markets()

    tickers = exchange.fetch_tickers()

    candidates = []

    for symbol, market in markets.items():

        try:

            if not market.get("active", True):
                continue

            if market.get("type") != "swap":
                continue

            if market.get("quote") != "USDT":
                continue

            if market.get("settle") != "USDT":
                continue

            ticker = tickers.get(symbol)

            if not ticker:
                continue

            quote_volume = (
                ticker.get("quoteVolume")
                or 0
            )

            if quote_volume < MIN_QUOTE_VOLUME:
                continue

            candidates.append({
                "pair": symbol,
                "quote_volume": float(
                    quote_volume
                ),
                "last": ticker.get("last"),
            })

        except Exception as e:

            print(
                f"Pair atlandı {symbol}: {e}"
            )

    candidates.sort(
        key=lambda x: x["quote_volume"],
        reverse=True
    )

    candidates = candidates[
        :MAX_PAIRS
    ]

    pairs = [
        x["pair"]
        for x in candidates
    ]

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "pairs": pairs,
                "count": len(pairs),
                "pairs_detail": candidates
            },
            f,
            indent=2
        )

    print(
        f"{len(pairs)} coin seçildi."
    )

    for pair in pairs:

        print(pair)


if __name__ == "__main__":
    main()
