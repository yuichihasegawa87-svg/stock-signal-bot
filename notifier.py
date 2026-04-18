"""
notifier.py
LINE Notify を使ってiPhoneに通知を送る

LINE Notifyの仕様:
- 1メッセージの上限: 1000文字
- 1時間あたりの送信上限: 1000回（個人利用では問題なし）
- 画像添付も可能（今回はテキストのみ）
- 認証: トークン1つだけ。SMTPもパスワード設定も不要。
"""

import requests
import os
from datetime import datetime


LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"
# LINEの1メッセージ上限は1000文字。超える場合は分割して送信する。
MAX_CHARS = 1000


def _send_line(message: str) -> bool:
    """
    LINE Notifyに1件のメッセージを送信する内部関数
    """
    token = os.environ.get("LINE_NOTIFY_TOKEN", "")
    if not token:
        print("LINE_NOTIFY_TOKEN が設定されていません")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    data    = {"message": message}

    try:
        res = requests.post(LINE_NOTIFY_URL, headers=headers, data=data, timeout=10)
        if res.status_code == 200:
            return True
        else:
            print(f"LINE送信エラー: {res.status_code} {res.text}")
            return False
    except Exception as e:
        print(f"LINE送信例外: {e}")
        return False


def send_line_messages(messages: list[str]) -> bool:
    """
    複数メッセージをまとめてLINEに送信する
    1000文字を超える場合は自動で分割する
    """
    success = True
    for msg in messages:
        # 1000文字を超える場合は分割
        if len(msg) > MAX_CHARS:
            chunks = [msg[i:i+MAX_CHARS] for i in range(0, len(msg), MAX_CHARS)]
            for chunk in chunks:
                if not _send_line(chunk):
                    success = False
        else:
            if not _send_line(msg):
                success = False
    return success


# ============================================================
# 朝のシグナル通知
# ============================================================

def build_morning_messages(candidates: list, market_ctx: dict) -> list[str]:
    """
    朝のシグナルをLINEメッセージのリストに変換する
    銘柄1つにつき1メッセージ（見やすくするため）
    """
    today = datetime.now().strftime("%m/%d")
    bias  = market_ctx.get("market_bias", "中立")
    bias_emoji = {"強気": "🟢", "中立": "🟡", "弱気": "🔴"}.get(bias, "🟡")
    ms    = market_ctx.get("market_score", 0)
    nk    = market_ctx.get("nikkei", {})
    fx    = market_ctx.get("usdjpy", {})
    sp    = market_ctx.get("sp500", {})

    def fmt(v):
        return f"{'+'if v>=0 else ''}{v:.2f}%"

    messages = []

    # ── メッセージ①：市場環境サマリー ──
    header = (
        f"\n【株シグナル {today} 朝8:00】\n"
        f"━━━━━━━━━━━━\n"
        f"市場: {bias_emoji}{bias}（{ms}/40点）\n"
        f"日経: {nk.get('price',0):,.0f}円 {fmt(nk.get('change_pct',0))}\n"
        f"ドル円: {fx.get('price',0):.1f}円 {fmt(fx.get('change_pct',0))}\n"
        f"SP500: {sp.get('price',0):,.0f} {fmt(sp.get('change_pct',0))}\n"
    )
    if market_ctx.get("has_major_event"):
        header += "⚠️ 本日重要指標あり\n"

    if not candidates:
        header += "\n本日の推奨銘柄なし\n→ 様子見を推奨します"
        messages.append(header)
        return messages

    header += f"\n注目銘柄: {len(candidates)}件 ↓"
    messages.append(header)

    # ── メッセージ②以降：銘柄1件ずつ ──
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, c in enumerate(candidates):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        ind   = c.get("indicators", {})
        tgt   = c.get("targets", {})
        score = c.get("score", 0)
        bar   = "█" * int(score / 10) + "░" * (10 - int(score / 10))

        reasons = []
        if c.get("volume_ratio", 0) >= 2.0:
            reasons.append(f"出来高{c['volume_ratio']:.1f}倍")
        if c.get("price_change_pct", 0) >= 1.0:
            reasons.append(f"+{c['price_change_pct']:.1f}%上昇")
        if ind.get("macd_golden_cross"):
            reasons.append("MACD GC")
        if 50 <= ind.get("rsi", 0) <= 70:
            reasons.append(f"RSI{ind['rsi']:.0f}")
        if ind.get("perfect_order"):
            reasons.append("完全順列")

        msg = (
            f"\n{medal} {c['name']}（{c['code']}）\n"
            f"信頼度: {score:.0f}% [{bar}]\n"
            f"前日終値: {c['close']:,.0f}円\n"
            f"前日比: +{c['price_change_pct']:.1f}%\n"
            f"根拠: {' / '.join(reasons)}\n"
            f"━━━━━━━━━━━━\n"
            f"▶ 参考エントリー\n"
            f"  {tgt.get('entry',0):,.0f}円\n"
            f"✅ 利確目標 (+1.5%)\n"
            f"  {tgt.get('target',0):,.0f}円\n"
            f"🛑 損切ライン (-0.7%)\n"
            f"  {tgt.get('stop',0):,.0f}円\n"
            f"RR比: {tgt.get('rr_ratio','-')}\n"
        )
        messages.append(msg)

    # ── 最後にフッター ──
    messages.append(
        "\n⚠️ 最終判断はご自身で\n"
        "📊 10:30前場・13:30後場\n"
        "　に状況変化を再通知します"
    )
    return messages


# ============================================================
# 前場・後場の監視通知
# ============================================================

def build_monitor_messages(
    mode: str,
    changed_candidates: list,
    new_candidates: list,
    market_ctx: dict
) -> tuple[list[str], bool]:
    """
    前場・後場の監視結果をLINEメッセージに変換する

    Returns:
        (メッセージリスト, 送信すべきかどうか)
    """
    from monitor import SIGNAL_STRENGTHEN, SIGNAL_WEAKEN, SIGNAL_EXIT

    now   = datetime.now().strftime("%H:%M")
    label = "前場レビュー" if mode == "midmorning" else "後場シグナル"
    bias  = market_ctx.get("market_bias", "中立")
    bias_emoji = {"強気": "🟢", "中立": "🟡", "弱気": "🔴"}.get(bias, "🟡")

    # 後場は常に送信、前場は変化があった場合のみ
    should_send = (mode == "afternoon") or bool(changed_candidates or new_candidates)
    if not should_send:
        print("前場：変化なし → LINE通知スキップ")
        return [], False

    messages = []

    # ── ヘッダー ──
    header = (
        f"\n【{label} {now}】\n"
        f"市場: {bias_emoji}{bias}\n"
        f"━━━━━━━━━━━━"
    )
    messages.append(header)

    # ── 朝の銘柄の状況変化 ──
    if changed_candidates:
        for c in changed_candidates:
            ct = c["change_type"]
            if ct == SIGNAL_STRENGTHEN:
                icon = "📈 強化シグナル\n→ 継続/追加エントリー推奨"
            elif ct == SIGNAL_WEAKEN:
                icon = "⚠️ 弱体化シグナル\n→ 利確を検討"
            else:
                icon = "🚨 撤退シグナル\n→ 損切り/見送り推奨"

            diff     = c["current_close"] - c["entry_price"]
            diff_pct = diff / c["entry_price"] * 100

            msg = (
                f"\n{icon}\n"
                f"{c['name']}（{c['code']}）\n"
                f"現在値: {c['current_close']:,.0f}円\n"
                f"朝比: {'+'if diff>=0 else ''}{diff_pct:.1f}%\n"
            )
            for reason in c["change_reasons"]:
                msg += f"→ {reason}\n"
            msg += (
                f"利確: {c['target_price']:,.0f}円\n"
                f"損切: {c['stop_price']:,.0f}円"
            )
            messages.append(msg)
    else:
        if mode == "midmorning":
            messages.append("\n朝の銘柄：変化なし\nホールド継続")

    # ── 後場の新規銘柄 ──
    if new_candidates:
        messages.append("\n🆕 後場の新規候補銘柄")
        medals = ["🥇", "🥈", "🥉"]
        for i, c in enumerate(new_candidates[:3]):
            medal = medals[i] if i < len(medals) else "▶"
            tgt   = c.get("targets", {})
            msg = (
                f"\n{medal} {c['name']}（{c['code']}）\n"
                f"信頼度: {c['score']:.0f}%\n"
                f"前日比: +{c['price_change_pct']:.1f}%\n"
                f"出来高: {c['volume_ratio']:.1f}倍\n"
                f"エントリー: {tgt.get('entry',0):,.0f}円\n"
                f"利確: {tgt.get('target',0):,.0f}円\n"
                f"損切: {tgt.get('stop',0):,.0f}円"
            )
            messages.append(msg)
    elif mode == "afternoon":
        messages.append("\n後場の新規候補：なし")

    messages.append("\n⚠️ 最終判断はご自身で")
    return messages, True
