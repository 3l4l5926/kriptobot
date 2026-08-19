import json
from pathlib import Path

import ccxt


OUTPUT_FILE = Path("data/candidate_pairs.json")

# İlk testte 20 coin ile başlayalım.
# Sistem sorunsuz çalışınca 80'e çıkarırız.
MAX_PAIRS = 20

# Minimum 24 saatlik USDT hacmi
MIN_QUOTE_VOLUME = 5_000_000


def main():

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Gate Futures taranıyor...")

    # Güncel CCXT'de Gate sınıfı:
    # ccxt.gate()
    exchange = ccxt.gate({
        "enableRateLimit": True,
        "options": {
            "defaultType": "swap"
        }
    })

    print("Gate piyasaları yükleniyor...")

    markets = exchange.load_markets()

    print(
        f"{len(markets)} piyasa bulundu."
    )

    print("Ticker verileri alınıyor...")

    tickers = exchange.fetch_tickers()

    candidates = []

    for symbol, market in markets.items():

        try:

            # Sadece aktif piyasalar
            if not market.get("active", True):
                continue

            # Sadece swap / perpetual
            if market.get("type") != "swap":
                continue

            # Sadece USDT
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

            quote_volume = float(
                quote_volume
            )

            # Likidite filtresi
            if quote_volume < MIN_QUOTE_VOLUME:
                continue

            last_price = ticker.get("last")

            if not last_price:
                continue

            candidates.append({
                "pair": symbol,
                "quote_volume": quote_volume,
                "last": float(last_price)
            })

        except Exception as e:

            print(
                f"Pair atlandı: {symbol} -> {e}"
            )

    # Hacme göre sırala
    candidates.sort(
        key=lambda x: x["quote_volume"],
        reverse=True
    )

    # En likit ilk coinler
    candidates = candidates[
        :MAX_PAIRS
    ]

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
        f"TARAMA TAMAMLANDI: {len(pairs)} COIN"
    )
    print("=" * 60)

    for index, item in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{item['pair']} | "
            f"Hacim: "
            f"{item['quote_volume']:,.0f} USDT"
        )

    print("")
    print(
        f"Sonuç kaydedildi: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
