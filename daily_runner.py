"""
daily_runner.py v2
cron-job.org から workflow_dispatch でトリガーされる前提。
起動時刻を見て対応モードを即時実行する。sleepなし。
"""

import subprocess
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

SCHEDULE = [
    (8,  0,  "morning",    None),
    (10, 30, "midmorning", "morning_result.json"),
    (13, 30, "afternoon",  "morning_result.json"),
]

TOLERANCE_MINUTES = 30


def now_jst() -> datetime:
    return datetime.now(JST)


def run_mode(mode: str, input_file: str = None):
    cmd = ["python", "main.py", "--mode", mode]
    if input_file and os.path.exists(input_file):
        cmd += ["--input", input_file]

    print(f"\n{'='*40}")
    print(f"[{now_jst().strftime('%H:%M:%S')} JST] {mode} モード開始")
    print(f"{'='*40}")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"❌ {mode} 失敗（終了コード {result.returncode}）")
    else:
        print(f"✅ {mode} 完了")


def main():
    now = now_jst()
    print(f"daily_runner v2 起動: {now.strftime('%Y-%m-%d %H:%M:%S')} JST")

    for hour, minute, mode, input_file in SCHEDULE:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        diff_minutes = (now - target).total_seconds() / 60

        if abs(diff_minutes) <= TOLERANCE_MINUTES:
            print(f"→ {hour:02d}:{minute:02d} の {mode} モードと判定（差 {diff_minutes:.1f}分）")
            run_mode(mode, input_file)
            return

    print(f"⚠️ 対応するモードなし（起動時刻: {now.strftime('%H:%M')} JST）")


if __name__ == "__main__":
    main()
