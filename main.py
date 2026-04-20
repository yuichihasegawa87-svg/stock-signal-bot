"""
main.py v5
Discord Webhook通知版

--mode morning    : 朝8時のシグナル生成＆Discord通知
--mode midmorning : 前場10:30の監視＆Discord通知（変化ありのみ）
--mode afternoon  : 後場13:30のシグナル更新＆Discord通知

v5変更点:
  - screener.py が yfinance ベースになったため token を screen_candidates に渡さない
  - monitor.py の get_daily_quotes も yfinance 経由（token は形式的に渡すのみ）
"""

import argparse
import json
import os
import sys
from datetime import datetime

from market_context import get_market_context
from screener import get_jquants_access_token, screen_candidates
from scorer import calculate_score, calc_entry_targets
from monitor import check_signal_status
from notifier import (
    send_discord_messages,
    build_morning_payloads,
    build_monitor_payloads
)


TOP_CANDIDATES = 5
MIN_SCORE      = 50
SCREEN_TOP_N   = 30


def run_screening(market_ctx: dict) -> list:
    # v5: token不要。screen_candidates() はwatchlistからyfinanceで取得
    candidates_df = screen_candidates(top_n=SCREEN_TOP_N)
    if candidates_df.empty:
        return []

    scored = []
    for _, row in candidates_df.iterrows():
        row_dict = row.to_dict()
        result   = calculate_score(row_dict, market_ctx["market_score"])
        targets  = calc_entry_targets(row_dict)
        if result["score"] >= MIN_SCORE:
            scored.append({
                "code":             row_dict["code"],
                "name":             row_dict["name"],
                "sector":           row_dict["sector"],
                "close":            row_dict["close"],
                "price_change_pct": row_dict["price_change_pct"],
                "volume_ratio":     row_dict["volume_ratio"],
                "score":            result["score"],
                "indicators":       result["indicators"],
                "targets":          targets
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:TOP_CANDIDATES]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",  default="morning",
                        choices=["morning", "midmorning", "afternoon"])
    parser.add_argument("--input", default=None)
    args = parser.parse_args()

    print(f"{'='*40}")
    print(f"実行モード: {args.mode}  {datetime.now().strftime('%H:%M')}")
    print(f"{'='*40}")

    market_ctx = get_market_context()
    print(f"市場バイアス: {market_ctx['market_bias']} ({market_ctx['market_score']}/40)")

    # v5: token は monitor.py の後方互換用にのみ使う（実質不要）
    token = get_jquants_access_token()

    # ── 朝モード ──
    if args.mode == "morning":

        if market_ctx["market_bias"] == "弱気" and market_ctx.get("has_major_event"):
            from notifier import build_skip_payloads
            send_discord_messages(build_skip_payloads(market_ctx))
            with open("morning_result.json", "w", encoding="utf-8") as f:
                json.dump({"timestamp": datetime.now().isoformat(),
                           "market_ctx": market_ctx, "candidates": []}, f,
                          ensure_ascii=False, indent=2)
            return

        candidates = run_screening(market_ctx)
        print(f"候補銘柄: {len(candidates)}件")

        payloads = build_morning_payloads(candidates, market_ctx)
        success  = send_discord_messages(payloads)

        if success:
            print(f"✅ Discord通知完了（{len(payloads)}件送信）")
        else:
            print("❌ Discord通知失敗")
            sys.exit(1)

        morning_data = {
            "timestamp":  datetime.now().isoformat(),
            "market_ctx": market_ctx,
            "candidates": candidates
        }
        with open("morning_result.json", "w", encoding="utf-8") as f:
            json.dump(morning_data, f, ensure_ascii=False, indent=2)
        print("morning_result.json を保存しました")

    # ── 前場・後場モード ──
    else:
        morning_candidates = []
        if args.input and os.path.exists(args.input):
            with open(args.input, "r", encoding="utf-8") as f:
                morning_data       = json.load(f)
                morning_candidates = morning_data.get("candidates", [])
            print(f"朝の候補銘柄: {len(morning_candidates)}件を読み込み")
        else:
            print("⚠️ 朝のデータが見つかりません")

        changed = check_signal_status(morning_candidates, token)
        print(f"状況変化: {len(changed)}件")

        new_candidates = []
        if args.mode == "afternoon":
            print("後場の新規スクリーニング中...")
            all_new        = run_screening(market_ctx)
            morning_codes  = {c["code"] for c in morning_candidates}
            new_candidates = [c for c in all_new if c["code"] not in morning_codes]
            print(f"新規候補: {len(new_candidates)}件")

        payloads, should_send = build_monitor_payloads(
            args.mode, changed, new_candidates, market_ctx
        )

        if should_send:
            success = send_discord_messages(payloads)
            if success:
                print(f"✅ Discord通知完了（{len(payloads)}件送信）")
            else:
                print("❌ Discord通知失敗")
                sys.exit(1)
        else:
            print("変化なし → Discord通知スキップ")


if __name__ == "__main__":
    main()
