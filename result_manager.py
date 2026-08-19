import json
from pathlib import Path


RESULT_FILE = Path(
    "data/walk_forward_results.json"
)

PARAM_FILE = Path(
    "data/pair_params.json"
)

ACTIVE_FILE = Path(
    "data/active_pairs.json"
)


def load(path):

    if not path.exists():
        return {}

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return {}


def summary():

    results = load(
        RESULT_FILE
    )

    active = load(
        ACTIVE_FILE
    )

    pairs = active.get(
        "pairs",
        []
    )

    lines = []

    lines.append(
        "📊 WALK-FORWARD SONUÇLARI"
    )

    lines.append("")

    for pair, result in results.items():

        metrics = result.get(
            "metrics",
            {}
        )

        pf = metrics.get(
            "profit_factor",
            0
        )

        trades = metrics.get(
            "trades",
            0
        )

        dd = metrics.get(
            "drawdown",
            0
        )

        profit = metrics.get(
            "profit_percent",
            0
        )

        status = (
            "✅"
            if result.get("active")
            else "❌"
        )

        lines.append(
            f"{status} {pair}"
        )

        lines.append(
            f"PF: {pf:.2f} | "
            f"Trades: {trades}"
        )

        lines.append(
            f"Profit: {profit:.2f}% | "
            f"DD: {dd:.2%}"
        )

        lines.append("")

    lines.append(
        f"Aktif coin: {len(pairs)}"
    )

    return "\n".join(
        lines
    )


def parameters(pair=None):

    params = load(
        PARAM_FILE
    )

    if pair:

        if pair not in params:

            return (
                f"❌ {pair} için "
                f"parametre bulunamadı."
            )

        return json.dumps(
            params[pair],
            indent=2
        )

    return json.dumps(
        params,
        indent=2
    )


if __name__ == "__main__":

    print(summary())
