"""
main.py v3
LINE Notify版

--mode morning    : 朝8時のシグナル生成＆LINE通知
--mode midmorning : 前場10:30の監視＆LINE通知（変化ありのみ）
--mode afternoon  : 後場13:30のシグナル更新＆LINE通知
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
    send_line_messages,
    build_morning_messages,
    build_monitor_messages
)


TOP_CANDIDATES = 5
MIN_SCORE      = 50
SCREEN_TOP_N   = 30


# ============================================================
# 共通：スクリーニング + スコアリング
# ============================================================

def run_screening(token: str, market_ctx: dict) -> list:
    """スクリーニングからスコアリングまでを実行してリストを返す"""
    candidates_df = screen_candidates(token, top_n=SCREEN_TOP_N)
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


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",  default="morning",
                        choices=["morning", "midmorning", "afternoon"])
    parser.add_argument("--input", default=None, help="朝の結果JSONファイルパス")
    args = parser.parse_args()

    print(f"{'='*40}")
    print(f"実行モード: {args.mode}  {datetime.now().strftime('%H:%M')}")
    print(f"{'='*40}")

    # 市場環境は全モードで取得
    market_ctx = get_market_context()
    print(f"市場バイアス: {market_ctx['market_bias']} ({market_ctx['market_score']}/40)")

    # J-Quantsトークン取得
    token = get_jquants_access_token()

    # ──────────────────────────────────────
    # 朝モード
    # ──────────────────────────────────────
    if args.mode == "morning":

        # 弱気 + 重要イベントの場合は見送り通知
        if market_ctx["market_bias"] == "弱気" and market_ctx.get("has_major_event"):
            print("弱気相場 + 重要イベント → 見送り通知")
            send_line_messages([
                "\n【株シグナル 朝8:00】\n"
                "⚠️ 本日は見送りを推奨\n"
                "弱気相場 + 重要経済指標あり\n"
                "リスクが高いため様子見を"
            ])
            # 空の朝データを保存
            with open("morning_result.json", "w", encoding="utf-8") as f:
                json.dump({"timestamp": datetime.now().isoformat(),
                           "market_ctx": market_ctx, "candidates": []}, f,
                          ensure_ascii=False, indent=2)
            return

        # スクリーニング実行
        candidates = run_screening(token, market_ctx)
        print(f"候補銘柄: {len(candidates)}件")

        # LINEに通知
        messages = build_morning_messages(candidates, market_ctx)
        success  = send_line_messages(messages)

        if success:
            print(f"✅ LINE通知完了（{len(messages)}件送信）")
        else:
            print("❌ LINE通知失敗")
            sys.exit(1)

        # 朝の結果をJSONに保存（前場・後場が参照する）
        morning_data = {
            "timestamp":  datetime.now().isoformat(),
            "market_ctx": market_ctx,
            "candidates": candidates
        }
        with open("morning_result.json", "w", encoding="utf-8") as f:
            json.dump(morning_data, f, ensure_ascii=False, indent=2)
        print("morning_result.json を保存しました")

    # ──────────────────────────────────────
    # 前場・後場モード
    # ──────────────────────────────────────
    else:
        # 朝のデータを読み込む
        morning_candidates = []
        if args.input and os.path.exists(args.input):
            with open(args.input, "r", encoding="utf-8") as f:
                morning_data       = json.load(f)
                morning_candidates = morning_data.get("candidates", [])
            print(f"朝の候補銘柄: {len(morning_candidates)}件を読み込み")
        else:
            print("⚠️ 朝のデータが見つかりません。新規スクリーニングのみ実行します。")

        # 朝の銘柄の状況変化を検知
        changed = check_signal_status(morning_candidates, token)
        print(f"状況変化: {len(changed)}件")

        # 後場のみ新規スクリーニングも実施
        new_candidates = []
        if args.mode == "afternoon":
            print("後場の新規スクリーニング中...")
            all_new       = run_screening(token, market_ctx)
            morning_codes = {c["code"] for c in morning_candidates}
            new_candidates = [c for c in all_new if c["code"] not in morning_codes]
            print(f"新規候補: {len(new_candidates)}件")

        # LINEメッセージを生成
        messages, should_send = build_monitor_messages(
            args.mode, changed, new_candidates, market_ctx
        )

        if should_send:
            success = send_line_messages(messages)
            if success:
                print(f"✅ LINE通知完了（{len(messages)}件送信）")
            else:
                print("❌ LINE通知失敗")
                sys.exit(1)
        else:
            print("変化なし → LINE通知スキップ（前場のみ）")


if __name__ == "__main__":
    main()
