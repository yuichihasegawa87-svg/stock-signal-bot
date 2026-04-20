"""
monitor.py v5
朝に通知した銘柄の「状況変化」を検知する

世界のクオンツが使う原則：
「シグナルの強さが変わったときだけ通知する」
常時通知は情報過多になるため、変化検知型にする
"""

import json
import os
import pandas as pd
from datetime import datetime
from screener import get_jquants_access_token, get_daily_quotes
from scorer import calc_rsi, calc_macd, calc_bollinger


# ============================================================
# 状況変化の種類
# ============================================================

SIGNAL_STRENGTHEN = "strengthen"  # シグナル強化（継続/追加推奨）
SIGNAL_WEAKEN     = "weaken"      # シグナル弱体化（利確検討）
SIGNAL_EXIT       = "exit"        # 撤退シグナル（損切り/見送り）
SIGNAL_UNCHANGED  = "unchanged"   # 変化なし（通知しない）


# ============================================================
# 朝の銘柄の現在状況をチェック
# ============================================================

def check_signal_status(morning_candidates: list, token: str) -> list:
    """
    朝に通知した銘柄の現在の状況を確認し、変化があった銘柄を返す

    Args:
        morning_candidates: 朝のシグナルで通知した銘柄リスト
        token: J-Quantsアクセストークン（v5では未使用・後方互換のため残存）

    Returns:
        変化があった銘柄のリスト（変化なしは含まない）
    """
    results = []

    for candidate in morning_candidates:
        code          = candidate["code"]
        name          = candidate["name"]
        morning_score = candidate["score"]
        morning_rsi   = candidate["indicators"].get("rsi", 50)
        entry_price   = candidate["targets"].get("entry", 0)
        target_price  = candidate["targets"].get("target", 0)
        stop_price    = candidate["targets"].get("stop", 0)

        try:
            # 最新データを取得
            df = get_daily_quotes(token, code, days=5)
            if df.empty or len(df) < 3:
                continue

            close_series = df["Close"].astype(float)
            latest_close = close_series.iloc[-1]

            # 現在のテクニカル指標
            current_rsi  = calc_rsi(close_series)
            _, _, hist, golden_cross = calc_macd(close_series)
            _, _, _, bb_pos = calc_bollinger(close_series)

            # 出来高変化
            latest_vol = df["Volume"].iloc[-1]
            avg_vol    = df["Volume"].iloc[:-1].mean()
            vol_ratio  = latest_vol / avg_vol if avg_vol > 0 else 1.0

            # ============================================================
            # 状況変化の判定ロジック
            # ============================================================
            change_type = SIGNAL_UNCHANGED
            change_reasons = []

            # ① 撤退シグナル（最優先）
            if latest_close <= stop_price:
                change_type = SIGNAL_EXIT
                change_reasons.append(f"価格が損切りライン({stop_price:,.0f}円)に到達")
            elif current_rsi > 75:
                change_type = SIGNAL_EXIT
                change_reasons.append(f"RSI過熱({current_rsi:.0f}) → 買われすぎ")
            elif vol_ratio < 0.5 and latest_close < entry_price:
                change_type = SIGNAL_EXIT
                change_reasons.append(f"出来高急減({vol_ratio:.1f}倍) + 価格下落")

            # ② シグナル強化
            elif (
                golden_cross and
                current_rsi > morning_rsi and
                vol_ratio >= 1.5 and
                latest_close > entry_price
            ):
                change_type = SIGNAL_STRENGTHEN
                change_reasons.append("MACDゴールデンクロス発生")
                change_reasons.append(f"RSI上昇({morning_rsi:.0f}→{current_rsi:.0f})")
                change_reasons.append(f"出来高継続増加({vol_ratio:.1f}倍)")

            elif vol_ratio >= 2.0 and latest_close > entry_price * 1.005:
                change_type = SIGNAL_STRENGTHEN
                change_reasons.append(f"出来高さらに急増({vol_ratio:.1f}倍)")
                change_reasons.append(f"価格上昇継続")

            # ③ シグナル弱体化
            elif latest_close >= target_price * 0.99:
                change_type = SIGNAL_WEAKEN
                change_reasons.append(f"目標価格({target_price:,.0f}円)に接近 → 利確検討")
            elif current_rsi > 70 and current_rsi > morning_rsi + 10:
                change_type = SIGNAL_WEAKEN
                change_reasons.append(f"RSI上昇しすぎ({current_rsi:.0f}) → 過熱感")

            # 変化なしはスキップ
            if change_type == SIGNAL_UNCHANGED:
                continue

            results.append({
                "code":           code,
                "name":           name,
                "change_type":    change_type,
                "change_reasons": change_reasons,
                "morning_score":  morning_score,
                "current_close":  latest_close,
                "entry_price":    entry_price,
                "target_price":   target_price,
                "stop_price":     stop_price,
                "current_rsi":    current_rsi,
                "vol_ratio":      round(vol_ratio, 2),
                "bb_position":    round(bb_pos, 1)
            })

        except Exception as e:
            print(f"  {code} モニタリングエラー: {e}")
            continue

    return results
