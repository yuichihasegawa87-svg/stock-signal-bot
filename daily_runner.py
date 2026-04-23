"""
daily_runner.py
GitHub Actions上で朝・前場・後場を正確な時刻に実行するスケジューラ

GitHub Actionsのcronは数時間ズレることがあるため、
このスクリプトが07:50頃に起動し、
Python の time.sleep() で正確な時刻まで待機してから各モードを実行する。
"""

import subprocess
import time
import json
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

# 実行スケジュール（JST）
SCHEDULE = [
    (8,  0,  "morning",    None),
    (10, 30, "midmorning", "morning_result.json"),
    (13, 30, "afternoon",  "morning_result.json"),
]


def now_jst() -> datetime:
    return datetime.now(JST)


def wait_until(target_hour: int, target_minute: int):
    """指定時刻（JST）になるまでsleepする"""
    while True:
        now = now_jst()
        target = now.replace(hour=target_hour, minute=target_minute,
                             second=0, microsecond=0)
        diff = (target - now).total_seconds()
        if diff <= 0:
            return  # 既に過ぎていれば即実行
        if diff > 60:
            print(f"  [{now_jst().strftime('%H:%M:%S')} JST] "
                  f"{target_hour:02d}:{target_minute:02d} まで {diff/60:.1f}分待機中...")
            time.sleep(min(diff - 30, 60))  # 30秒前まで1分おきにチェック
        else:
            time.sleep(diff)
            return


def run_mode(mode: str, input_file: str = None):
    """main.py を指定モードで実行する"""
    cmd = ["python", "main.py", "--mode", mode]
    if input_file and os.path.exists(input_file):
        cmd += ["--input", input_file]

    print(f"\n{'='*40}")
    print(f"[{now_jst().strftime('%H:%M:%S')} JST] {mode} モード開始")
    print(f"{'='*40}")

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"❌ {mode} モード失敗（終了コード {result.returncode}）")
    else:
        print(f"✅ {mode} モード完了")


def main():
    print(f"デイリースケジューラ起動: {now_jst().strftime('%Y-%m-%d %H:%M:%S')} JST")
    print(f"実行予定: 08:00（朝）/ 10:30（前場）/ 13:30（後場）")

    for hour, minute, mode, input_file in SCHEDULE:
        now = now_jst()
        target_str = f"{hour:02d}:{minute:02d}"

        # 既に実行時刻を大幅に（30分以上）過ぎていればスキップ
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if (now - target).total_seconds() > 30 * 60:
            print(f"\n⏭️  {target_str} ({mode}) は既に30分以上経過 → スキップ")
            continue

        print(f"\n⏳ {target_str} ({mode}) まで待機...")
        wait_until(hour, minute)
        run_mode(mode, input_file)

    print(f"\n✅ 本日のスケジュール完了: {now_jst().strftime('%H:%M:%S')} JST")


if __name__ == "__main__":
    main()
