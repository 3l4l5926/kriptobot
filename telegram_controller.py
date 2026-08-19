import asyncio
import json
import os
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


TOKEN = os.environ.get(
    "TELEGRAM_TOKEN"
)

CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID"
)


def authorized(update):

    if not CHAT_ID:
        return True

    return str(
        update.effective_chat.id
    ) == str(CHAT_ID)


async def send(
    update,
    text
):

    await update.message.reply_text(
        text
    )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    text = """
🤖 Quantum Momentum Bot

Komutlar:

/tara
Gate Futures coinlerini tara.

/egit
Coin başına Hyperopt başlat.

/test
Walk-forward OOS testi yap.

/sonuclar
Son test sonuçlarını göster.

/aktif
Aktif coinleri göster.

/parametre BTC/USDT:USDT
Coin parametrelerini göster.

/durum
Sistem durumunu göster.
"""

    await send(
        update,
        text
    )


async def run_command(
    update,
    command,
    success_message
):

    try:

        await send(
            update,
            f"⏳ {success_message}"
        )

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        output, _ = await process.communicate()

        if process.returncode != 0:

            text = (
                "❌ İşlem başarısız.\n\n"
                +
                output.decode(
                    errors="ignore"
                )[-3000:]
            )

            await send(
                update,
                text
            )

            return

        text = (
            "✅ Tamamlandı.\n\n"
            +
            output.decode(
                errors="ignore"
            )[-3000:]
        )

        await send(
            update,
            text
        )

    except Exception as e:

        await send(
            update,
            f"❌ Hata: {e}"
        )


async def scan(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    await run_command(
        update,
        [
            "python",
            "scanner.py"
        ],
        "Gate Futures taranıyor..."
    )


async def train(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    await run_command(
        update,
        [
            "python",
            "optimizer.py",
            "--timerange",
            get_training_range()
        ],
        "Coinler eğitiliyor..."
    )


async def test(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    await run_command(
        update,
        [
            "python",
            "walk_forward.py"
        ],
        "OOS testi başlatılıyor..."
    )


async def results(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    from result_manager import summary

    text = summary()

    await send(
        update,
        text[:4000]
    )


async def active(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    path = Path(
        "data/active_pairs.json"
    )

    if not path.exists():

        await send(
            update,
            "❌ Henüz sonuç yok."
        )

        return

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    pairs = data.get(
        "pairs",
        []
    )

    text = (
        "🟢 AKTİF COINLER\n\n"
        +
        "\n".join(pairs)
    )

    await send(
        update,
        text[:4000]
    )


async def parameter(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    if not context.args:

        await send(
            update,
            "Örnek:\n"
            "/parametre BTC/USDT:USDT"
        )

        return

    pair = " ".join(
        context.args
    )

    from result_manager import parameters

    text = parameters(
        pair
    )

    await send(
        update,
        text[:4000]
    )


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not authorized(update):
        return

    active_path = Path(
        "data/active_pairs.json"
    )

    params_path = Path(
        "data/pair_params.json"
    )

    active_count = 0

    param_count = 0

    if active_path.exists():

        with open(
            active_path,
            "r",
            encoding="utf-8"
        ) as f:

            active_count = len(
                json.load(f).get(
                    "pairs",
                    []
                )
            )

    if params_path.exists():

        with open(
            params_path,
            "r",
            encoding="utf-8"
        ) as f:

            param_count = len(
                json.load(f)
            )

    await send(
        update,
        (
            "🤖 SYSTEM STATUS\n\n"
            f"Parametreli coin: {param_count}\n"
            f"Aktif coin: {active_count}\n"
            "Timeframe: 15m\n"
            "Train: 90 gün\n"
            "OOS test: 30 gün"
        )
    )


def get_training_range():

    from datetime import (
        datetime,
        timedelta,
        timezone
    )

    end = datetime.now(
        timezone.utc
    ).date()

    start = (
        end
        -
        timedelta(
            days=90
        )
    )

    return (
        start.strftime("%Y%m%d")
        +
        "-"
        +
        end.strftime("%Y%m%d")
    )


def main():

    if not TOKEN:

        raise RuntimeError(
            "TELEGRAM_TOKEN bulunamadı."
        )

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "tara",
            scan
        )
    )

    application.add_handler(
        CommandHandler(
            "egit",
            train
        )
    )

    application.add_handler(
        CommandHandler(
            "test",
            test
        )
    )

    application.add_handler(
        CommandHandler(
            "sonuclar",
            results
        )
    )

    application.add_handler(
        CommandHandler(
            "aktif",
            active
        )
    )

    application.add_handler(
        CommandHandler(
            "parametre",
            parameter
        )
    )

    application.add_handler(
        CommandHandler(
            "durum",
            status
        )
    )

    print(
        "Telegram controller çalışıyor..."
    )

    application.run_polling()


if __name__ == "__main__":
    main()
