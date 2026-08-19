
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

COMMAND = os.environ.get("BOT_COMMAND", "").strip().lower()
ARGS = os.environ.get("BOT_ARGS", "").strip()

OUTPUT_FILE = Path("dispatch_output.txt")

CANDIDATE_FILE = Path("data/candidate_pairs.json")
ACTIVE_FILE = Path("data/active_pairs.json")
PARAM_FILE = Path("data/pair_params.json")


def write_output(text):
    # Telegram mesaj limiti 4096 karakter; güvenli pay bırakıyoruz.
    OUTPUT_FILE.write_text(text[:3800], encoding="utf-8")


def run(cmd, timeout=None):
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout + "\n" + result.stderr
    return result.returncode, output


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def get_training_range():
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=90)
    return f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"


def get_test_range():
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=30)
    return f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"


def download_data(pairs, timerange):
    command = [
        "freqtrade",
        "download-data",
        "--config",
        "config.json",
        "--trading-mode",
        "futures",
        "--timeframes",
        "15m",
        "--timerange",
        timerange,
        "--pairs",
        *pairs,
    ]
    return run(command, timeout=3600)


def cmd_tara():
    code, output = run(["python", "scanner.py"], timeout=600)
    prefix = "✅ Tarama tamamlandı.\n\n" if code == 0 else "❌ Tarama başarısız.\n\n"
    write_output(prefix + output[-3500:])


def cmd_egit():
    candidate = load_json(CANDIDATE_FILE, {})
    pairs = candidate.get("pairs", [])

    if not pairs:
        write_output("❌ candidate_pairs.json boş. Önce /tara çalıştır.")
        return

    train_range = get_training_range()
    test_range = get_test_range()
    full_range = f"{train_range.split('-')[0]}-{test_range.split('-')[1]}"

    code, dl_output = download_data(pairs, full_range)
    if code != 0:
        write_output("❌ Veri indirme başarısız.\n\n" + dl_output[-3500:])
        return

    code, output = run(
        ["python", "optimizer.py", "--timerange", train_range],
        timeout=5400,
    )
    prefix = "✅ Eğitim tamamlandı.\n\n" if code == 0 else "❌ Eğitim başarısız.\n\n"
    write_output(prefix + output[-3500:])


def cmd_test():
    candidate = load_json(CANDIDATE_FILE, {})
    pairs = candidate.get("pairs", [])

    if not pairs:
        write_output("❌ candidate_pairs.json boş. Önce /tara ve /egit çalıştır.")
        return

    test_range = get_test_range()

    code, dl_output = download_data(pairs, test_range)
    if code != 0:
        write_output("❌ Veri indirme başarısız.\n\n" + dl_output[-3500:])
        return

    code, output = run(["python", "walk_forward.py"], timeout=5400)
    prefix = "✅ Test tamamlandı.\n\n" if code == 0 else "❌ Test başarısız.\n\n"
    write_output(prefix + output[-3500:])


def cmd_sonuclar():
    from result_manager import summary

    write_output(summary())


def cmd_aktif():
    if not ACTIVE_FILE.exists():
        write_output("❌ Henüz sonuç yok.")
        return

    data = load_json(ACTIVE_FILE, {})
    pairs = data.get("pairs", [])

    if not pairs:
        write_output("🟢 Aktif coin yok.")
        return

    write_output("🟢 AKTİF COINLER\n\n" + "\n".join(pairs))


def cmd_parametre():
    from result_manager import parameters

    write_output(parameters(ARGS if ARGS else None))


def cmd_durum():
    active_count = len(load_json(ACTIVE_FILE, {}).get("pairs", []))
    param_count = len(load_json(PARAM_FILE, {}))

    write_output(
        "🤖 SYSTEM STATUS\n\n"
        f"Parametreli coin: {param_count}\n"
        f"Aktif coin: {active_count}\n"
        "Timeframe: 15m\n"
        "Train: 90 gün\n"
        "OOS test: 30 gün"
    )


COMMANDS = {
    "tara": cmd_tara,
    "egit": cmd_egit,
    "test": cmd_test,
    "sonuclar": cmd_sonuclar,
    "aktif": cmd_aktif,
    "parametre": cmd_parametre,
    "durum": cmd_durum,
}


def main():
    handler = COMMANDS.get(COMMAND)

    if not handler:
        write_output(f"❌ Bilinmeyen komut: {COMMAND}")
        return

    try:
        handler()
    except Exception as e:
        write_output(f"❌ Hata: {e}")


if __name__ == "__main__":
    main()
