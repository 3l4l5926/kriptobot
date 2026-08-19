import json
from pathlib import Path

import ccxt


OUTPUT_FILE = Path("data/candidate_pairs.json")

# İlk doğrulamada 5 coin.
# Sistem çalışınca 20 -> 50 -> 80 yapacağız.
MAX_PAIRS = 5

# Minimum 24 saatlik hacim
MIN_QUOTE_VOLUME = 10_000_000


def is_crypto_symbol(market):
    """
    Gate üzerindeki swap piyasalarından
    klasik kripto/USDT perpetual olanları seç.
    """

    if market.get("type") != "swap":
        return False

    if market.get("quote") != "USDT":
        return False

    if market.get("settle") != "USDT":
        return False

    # Gate'in bazı tokenized / stock / commodity
    # sözleşmelerini filtrele.
    symbol = market.get("symbol", "")

    base = market.get("base", "")

    # Kripto olmayan bilinen varlıkları dışla.
    excluded = {
        "XAU",
        "XAG",
        "MU",
        "SOXL",
        "QQQX",
        "SPCX",
        "SKHYNIX",
        "SKHY",
        "SNDK",
        "UNITREE",
        "DRAM",
    }

    if base.upper() in excluded:
        return False

    # Unified market bilgisi kripto değilse çıkar.
    if market.get("spot") is False and market.get("swap") is not True:
        return False

    return True


def main():

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Gate Futures taranıyor...")

    exchange = ccxt.gate({
        "enableRateLimit": True,
        "options": {
            "defaultType": "swap"
        }
    })

    markets = exchange.load_markets()

    print(
        f"Toplam piyasa: {len(markets)}"
    )

    tickers = exchange.fetch_tickers()

    candidates = []

    for symbol, market in markets.items():

        try:

            if not market.get("active", True):
                continue

            if not is_crypto_symbol(market):
                continue

            ticker = tickers.get(symbol)

            if not ticker:
                continue

            volume = ticker.get("quoteVolume")

            if volume is None:
                continue

            volume = float(volume)

            if volume < MIN_QUOTE_VOLUME:
                continue

            last = ticker.get("last")

            if not last:
                continue

            candidates.append({
                "pair": symbol,
                "quote_volume": volume,
                "last": float(last)
            })

        except Exception as e:

            print(
                f"Atlandı: {symbol} -> {e}"
            )

    # Hacme göre sırala
    candidates.sort(
        key=lambda x: x["quote_volume"],
        reverse=True
    )

    candidates = candidates[:MAX_PAIRS]

    pairs = [
        item["pair"]
        for item in candidates
    ]

    result = {
        "pairs": pairs,
        "count": len(pairs),
        "pairs_detail": candidates
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=2
        )

    print("")
    print("=" * 60)
    print(
        f"SEÇİLEN COIN SAYISI: {len(pairs)}"
    )
    print("=" * 60)

    for i, item in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{i}. {item['pair']} | "
            f"Hacim: "
            f"{item['quote_volume']:,.0f} USDT"
        )

    if not pairs:

        raise RuntimeError(
            "Hiç uygun kripto futures bulunamadı!"
        )

    print("")
    print(
        f"Kaydedildi: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
