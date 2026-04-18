"""
monitor.py
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
        token: J-Quantsアクセストークン

    Returns:
        変化があった銘柄のリスト（変化なしは含まない）
    """
    results = []

    for candidate in morning_candidates:
        code       = candidate["code"]
        name       = candidate["name"]
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
                "code":          code,
                "name":          name,
                "change_type":   change_type,
                "change_reasons": change_reasons,
                "morning_score": morning_score,
                "current_close": latest_close,
                "entry_price":   entry_price,
                "target_price":  target_price,
                "stop_price":    stop_price,
                "current_rsi":   current_rsi,
                "vol_ratio":     round(vol_ratio, 2),
                "bb_position":   round(bb_pos, 1)
            })

        except Exception as e:
            print(f"  {code} モニタリングエラー: {e}")
            continue

    return results


# ============================================================
# メール本文生成（前場/後場共通）
# ============================================================

def build_monitor_email(
    mode: str,
    changed_candidates: list,
    new_candidates: list,
    market_ctx: dict
) -> tuple[str, bool]:
    """
    監視結果のメール本文を生成する

    Args:
        mode: "midmorning"(前場) or "afternoon"(後場)
        changed_candidates: 状況が変化した朝の銘柄
        new_candidates: 新たに浮上した銘柄
        market_ctx: 市場環境

    Returns:
        (メール本文, 送信すべきかどうか)
    """
    mode_label = "前場レビュー（10:30）" if mode == "midmorning" else "後場シグナル（13:30）"
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    bias = market_ctx.get("market_bias", "中立")
    bias_emoji = {"強気": "🟢", "中立": "🟡", "弱気": "🔴"}.get(bias, "🟡")

    # 後場は常に送信、前場は変化があった場合のみ
    should_send = (mode == "afternoon") or bool(changed_candidates or new_candidates)

    if not should_send:
        return "変化なし", False

    body = f"【{mode_label} {now}】\n"
    body += f"市場環境: {bias_emoji} {bias}\n"
    body += "━" * 40 + "\n\n"

    # ── 朝の銘柄の状況変化 ──
    if changed_candidates:
        body += "■ 朝の銘柄：状況変化アリ\n\n"

        for c in changed_candidates:
            change_type = c["change_type"]

            if change_type == SIGNAL_STRENGTHEN:
                icon = "📈 【強化】継続/追加エントリー推奨"
            elif change_type == SIGNAL_WEAKEN:
                icon = "⚠️  【弱体化】利確を検討"
            else:
                icon = "🚨 【撤退】損切り/見送りを推奨"

            price_diff = c["current_close"] - c["entry_price"]
            price_diff_pct = price_diff / c["entry_price"] * 100

            body += f"{icon}\n"
            body += f"  {c['name']}（{c['code']}）\n"
            body += f"  現在値: {c['current_close']:,.0f}円"
            body += f"  (朝比 {'+' if price_diff >= 0 else ''}{price_diff_pct:.1f}%)\n"
            for reason in c["change_reasons"]:
                body += f"  → {reason}\n"
            body += f"  利確: {c['target_price']:,.0f}円 / 損切: {c['stop_price']:,.0f}円\n\n"

    else:
        body += "■ 朝の銘柄：変化なし（ホールド継続）\n\n"

    # ── 新規浮上銘柄 ──
    if new_candidates:
        body += "■ 新たに浮上した有力銘柄\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, c in enumerate(new_candidates[:3]):
            medal = medals[i] if i < len(medals) else "▶"
            body += f"{medal} {c['name']}（{c['code']}）  信頼度: {c['score']:.0f}%\n"
            body += f"   前日比: +{c['price_change_pct']:.1f}%  出来高: {c['volume_ratio']:.1f}倍\n"
            tgt = c.get("targets", {})
            body += f"   参考エントリー: {tgt.get('entry', '-'):,.0f}円\n"
            body += f"   利確: {tgt.get('target', '-'):,.0f}円 / 損切: {tgt.get('stop', '-'):,.0f}円\n\n"
    else:
        if mode == "afternoon":
            body += "■ 新規銘柄：後場で新たな候補は見つかりませんでした\n\n"

    body += "━" * 40 + "\n"
    body += "⚠️ 最終判断はご自身でお願いします\n"

    return body, True
