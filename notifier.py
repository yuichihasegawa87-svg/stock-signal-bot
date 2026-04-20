"""
notifier.py v4
Discord Webhook を使ってiPhoneに通知を送る

Discord Webhookの仕様:
- 1メッセージの上限: 2000文字
- 認証: WebhookのURLを1つ登録するだけ。トークンもパスワードも不要。
- Embedsという見やすいカード形式で表示できる
"""

import requests
import os
from datetime import datetime


DISCORD_MAX_CHARS = 2000


def _send_discord(content: str = None, embeds: list = None) -> bool:
    """
    Discord WebhookにメッセージまたはEmbedsを送信する内部関数
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL が設定されていません")
        return False

    payload = {}
    if content:
        payload["content"] = content[:DISCORD_MAX_CHARS]
    if embeds:
        payload["embeds"] = embeds

    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        if res.status_code in (200, 204):
            return True
        else:
            print(f"Discord送信エラー: {res.status_code} {res.text}")
            return False
    except Exception as e:
        print(f"Discord送信例外: {e}")
        return False


def send_discord_messages(payloads: list) -> bool:
    """
    複数のpayload（contentまたはembeds）をDiscordに順番に送信する
    payloads = [
        {"content": "テキスト"},
        {"embeds": [...]},
        ...
    ]
    """
    success = True
    for p in payloads:
        result = _send_discord(
            content=p.get("content"),
            embeds=p.get("embeds")
        )
        if not result:
            success = False
    return success


# ============================================================
# 色の定数（Discord Embedのサイドバー色）
# ============================================================
COLOR_GREEN  = 0x00C851  # 強気・強化
COLOR_YELLOW = 0xFFBB33  # 中立・弱体化
COLOR_RED    = 0xFF4444  # 弱気・撤退
COLOR_BLUE   = 0x33B5E5  # 情報


# ============================================================
# 朝のシグナル通知
# ============================================================

def build_morning_payloads(candidates: list, market_ctx: dict) -> list:
    """
    朝のシグナルをDiscord送信用payloadのリストに変換する
    """
    today = datetime.now().strftime("%Y/%m/%d")
    bias  = market_ctx.get("market_bias", "中立")
    ms    = market_ctx.get("market_score", 0)
    nk    = market_ctx.get("nikkei", {})
    fx    = market_ctx.get("usdjpy", {})
    sp    = market_ctx.get("sp500", {})
    nq    = market_ctx.get("nasdaq", {})

    bias_emoji = {"強気": "🟢", "中立": "🟡", "弱気": "🔴"}.get(bias, "🟡")
    color = {"強気": COLOR_GREEN, "中立": COLOR_YELLOW, "弱気": COLOR_RED}.get(bias, COLOR_YELLOW)

    def fmt(v):
        return f"{'+'if v>=0 else ''}{v:.2f}%"

    payloads = []

    # ── Embed①：市場環境サマリー ──
    market_embed = {
        "title": f"📈 株シグナル {today} 朝8:00",
        "color": color,
        "fields": [
            {
                "name": f"市場環境 {bias_emoji} {bias}",
                "value": (
                    f"スコア: {ms}/40点\n"
                    f"日経225:  `{nk.get('price',0):,.0f}円`  {fmt(nk.get('change_pct',0))}\n"
                    f"ドル円:   `{fx.get('price',0):.1f}円`  {fmt(fx.get('change_pct',0))}\n"
                    f"S&P500:   `{sp.get('price',0):,.0f}`  {fmt(sp.get('change_pct',0))}\n"
                    f"Nasdaq:   `{nq.get('price',0):,.0f}`  {fmt(nq.get('change_pct',0))}"
                ),
                "inline": False
            }
        ],
        "footer": {"text": "10:30前場・13:30後場に状況変化を再通知します"}
    }

    if market_ctx.get("has_major_event"):
        market_embed["fields"].append({
            "name": "⚠️ 注意",
            "value": "本日は重要経済指標の発表予定があります",
            "inline": False
        })

    if not candidates:
        market_embed["fields"].append({
            "name": "本日の推奨銘柄",
            "value": "条件を満たす銘柄なし\n**→ 本日は様子見を推奨します**",
            "inline": False
        })
        payloads.append({"embeds": [market_embed]})
        return payloads

    market_embed["fields"].append({
        "name": "本日の注目銘柄",
        "value": f"{len(candidates)}件が条件を満たしました ↓",
        "inline": False
    })
    payloads.append({"embeds": [market_embed]})

    # ── Embed②以降：銘柄1件ずつ ──
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, c in enumerate(candidates):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        ind   = c.get("indicators", {})
        tgt   = c.get("targets", {})
        score = c.get("score", 0)
        bar   = "█" * int(score / 10) + "░" * (10 - int(score / 10))

        reasons = []
        if c.get("volume_ratio", 0) >= 2.0:
            reasons.append(f"出来高{c['volume_ratio']:.1f}倍急増")
        if c.get("price_change_pct", 0) >= 1.0:
            reasons.append(f"前日比+{c['price_change_pct']:.1f}%")
        if ind.get("macd_golden_cross"):
            reasons.append("MACD GC")
        if 50 <= ind.get("rsi", 0) <= 70:
            reasons.append(f"RSI{ind['rsi']:.0f}")
        if ind.get("perfect_order"):
            reasons.append("移動平均完全順列")

        embed = {
            "title": f"{medal} {c['name']}（{c['code']}）",
            "description": f"**信頼度: {score:.0f}%**  `{bar}`",
            "color": COLOR_GREEN if score >= 70 else COLOR_YELLOW,
            "fields": [
                {
                    "name": "基本情報",
                    "value": (
                        f"セクター: {c.get('sector','')}\n"
                        f"前日終値: `{c['close']:,.0f}円`\n"
                        f"前日比: `+{c['price_change_pct']:.1f}%`\n"
                        f"出来高比: `{c['volume_ratio']:.1f}倍`"
                    ),
                    "inline": True
                },
                {
                    "name": "参考価格",
                    "value": (
                        f"▶ エントリー: `{tgt.get('entry',0):,.0f}円`\n"
                        f"✅ 利確目標: `{tgt.get('target',0):,.0f}円` (+1.5%)\n"
                        f"🛑 損切ライン: `{tgt.get('stop',0):,.0f}円` (-0.7%)\n"
                        f"RR比: `{tgt.get('rr_ratio','-')}`"
                    ),
                    "inline": True
                },
                {
                    "name": "判断根拠",
                    "value": " / ".join(reasons) if reasons else "複合条件通過",
                    "inline": False
                }
            ]
        }
        payloads.append({"embeds": [embed]})

    # フッター
    payloads.append({
        "content": "⚠️ 参考情報です。最終判断はご自身でお願いします。"
    })
    return payloads


# ============================================================
# 前場・後場の監視通知
# ============================================================

def build_monitor_payloads(
    mode: str,
    changed_candidates: list,
    new_candidates: list,
    market_ctx: dict
) -> tuple[list, bool]:
    """
    前場・後場の監視結果をDiscord送信用payloadに変換する

    Returns:
        (payloadリスト, 送信すべきかどうか)
    """
    from monitor import SIGNAL_STRENGTHEN, SIGNAL_WEAKEN, SIGNAL_EXIT

    now   = datetime.now().strftime("%H:%M")
    label = "前場レビュー" if mode == "midmorning" else "後場シグナル"
    bias  = market_ctx.get("market_bias", "中立")
    bias_emoji = {"強気": "🟢", "中立": "🟡", "弱気": "🔴"}.get(bias, "🟡")

    # 後場は常に送信、前場は変化があった場合のみ
    should_send = (mode == "afternoon") or bool(changed_candidates or new_candidates)
    if not should_send:
        print("前場：変化なし → Discord通知スキップ")
        return [], False

    payloads = []

    # ── ヘッダー ──
    header_embed = {
        "title": f"🔍 {label} {now}",
        "color": COLOR_BLUE,
        "description": f"市場: {bias_emoji} {bias}"
    }
    payloads.append({"embeds": [header_embed]})

    # ── 朝の銘柄の状況変化 ──
    if changed_candidates:
        for c in changed_candidates:
            ct = c["change_type"]
            if ct == SIGNAL_STRENGTHEN:
                icon  = "📈 強化シグナル"
                color = COLOR_GREEN
                msg   = "継続/追加エントリー推奨"
            elif ct == SIGNAL_WEAKEN:
                icon  = "⚠️ 弱体化シグナル"
                color = COLOR_YELLOW
                msg   = "利確を検討"
            else:
                icon  = "🚨 撤退シグナル"
                color = COLOR_RED
                msg   = "損切り/見送りを推奨"

            diff     = c["current_close"] - c["entry_price"]
            diff_pct = diff / c["entry_price"] * 100

            embed = {
                "title": f"{icon}：{c['name']}（{c['code']}）",
                "description": f"**→ {msg}**",
                "color": color,
                "fields": [
                    {
                        "name": "価格状況",
                        "value": (
                            f"現在値: `{c['current_close']:,.0f}円`\n"
                            f"朝比: `{'+'if diff>=0 else ''}{diff_pct:.1f}%`\n"
                            f"利確目標: `{c['target_price']:,.0f}円`\n"
                            f"損切ライン: `{c['stop_price']:,.0f}円`"
                        ),
                        "inline": True
                    },
                    {
                        "name": "変化の理由",
                        "value": "\n".join([f"→ {r}" for r in c["change_reasons"]]),
                        "inline": True
                    }
                ]
            }
            payloads.append({"embeds": [embed]})
    else:
        if mode == "midmorning":
            payloads.append({
                "content": "✅ 朝の銘柄：変化なし（ホールド継続）"
            })

    # ── 後場の新規銘柄 ──
    if new_candidates:
        payloads.append({"content": "🆕 **後場の新規候補銘柄**"})
        medals = ["🥇", "🥈", "🥉"]
        for i, c in enumerate(new_candidates[:3]):
            medal = medals[i] if i < len(medals) else "▶"
            tgt   = c.get("targets", {})
            embed = {
                "title": f"{medal} {c['name']}（{c['code']}）",
                "description": f"信頼度: **{c['score']:.0f}%**",
                "color": COLOR_GREEN,
                "fields": [
                    {
                        "name": "情報",
                        "value": (
                            f"前日比: `+{c['price_change_pct']:.1f}%`\n"
                            f"出来高: `{c['volume_ratio']:.1f}倍`"
                        ),
                        "inline": True
                    },
                    {
                        "name": "参考価格",
                        "value": (
                            f"エントリー: `{tgt.get('entry',0):,.0f}円`\n"
                            f"利確: `{tgt.get('target',0):,.0f}円`\n"
                            f"損切: `{tgt.get('stop',0):,.0f}円`"
                        ),
                        "inline": True
                    }
                ]
            }
            payloads.append({"embeds": [embed]})
    elif mode == "afternoon":
        payloads.append({"content": "後場の新規候補：条件を満たす銘柄なし"})

    payloads.append({"content": "⚠️ 参考情報です。最終判断はご自身でお願いします。"})
    return payloads, True


# ============================================================
# 見送り推奨通知（弱気相場 + 重要経済指標が重なった日）
# ============================================================

def build_skip_payloads(market_ctx: dict) -> list:
    """
    見送り推奨日の詳細通知を生成する。
    市場の数値・根拠・具体的な行動指針をEmbed形式で送信。
    """
    today = datetime.now().strftime("%Y/%m/%d")
    ms    = market_ctx.get("market_score", 0)
    nk    = market_ctx.get("nikkei", {})
    fx    = market_ctx.get("usdjpy", {})
    sp    = market_ctx.get("sp500", {})
    nq    = market_ctx.get("nasdaq", {})

    def fmt(v):
        return f"{'+'if v >= 0 else ''}{v:.2f}%"

    # ── 市場スコアから具体的な弱気根拠を生成 ──
    weak_reasons = []
    if nk.get("change_pct", 0) < 0:
        weak_reasons.append(f"日経225が前日比 {fmt(nk['change_pct'])} と下落")
    if fx.get("change_pct", 0) < 0:
        weak_reasons.append(f"ドル円が {fmt(fx['change_pct'])} と円高方向（輸出株に逆風）")
    if sp.get("change_pct", 0) < 0:
        weak_reasons.append(f"S&P500が {fmt(sp['change_pct'])} と下落（NY市場の地合い悪化）")
    if nq.get("change_pct", 0) < 0:
        weak_reasons.append(f"Nasdaqが {fmt(nq['change_pct'])} と下落（グロース株に売り圧力）")
    if not weak_reasons:
        weak_reasons.append("複数指標が弱気シグナルを点灯")

    weak_reasons_str = "\n".join([f"・{r}" for r in weak_reasons])

    payloads = []

    # ── Embed①：見送り宣言（目立つ赤） ──
    payloads.append({"embeds": [{
        "title": f"🚫 本日は見送りを推奨  {today}",
        "description": (
            "**弱気相場 × 重要経済指標の発表が重なっています。**\n"
            "この組み合わせは過去データ上、損切りが多発するパターンです。\n"
            "今日はポジションを持たず、相場を観察する日と割り切ってください。"
        ),
        "color": COLOR_RED,
        "fields": [
            {
                "name": "📊 本日の市場スコア",
                "value": (
                    f"`{ms}/40点`　← 30点以上で強気、20点未満で弱気\n"
                    f"日経225:  `{nk.get('price',0):,.0f}円`  {fmt(nk.get('change_pct',0))}\n"
                    f"ドル円:   `{fx.get('price',0):.1f}円`  {fmt(fx.get('change_pct',0))}\n"
                    f"S&P500:   `{sp.get('price',0):,.0f}`  {fmt(sp.get('change_pct',0))}\n"
                    f"Nasdaq:   `{nq.get('price',0):,.0f}`  {fmt(nq.get('change_pct',0))}"
                ),
                "inline": False
            },
            {
                "name": "🔴 弱気と判断した根拠",
                "value": weak_reasons_str,
                "inline": False
            },
            {
                "name": "⚠️ 重要経済指標の発表あり",
                "value": (
                    "本日はFOMC・日銀会合・米雇用統計（NFP）等の\n"
                    "重大イベントが予定されています。\n"
                    "発表前後は乱高下が起きやすく、損切りラインを簡単に割ります。"
                ),
                "inline": False
            }
        ]
    }]})

    # ── Embed②：見送る理由の解説 ──
    payloads.append({"embeds": [{
        "title": "📖 なぜ今日は見送るべきか",
        "color": COLOR_RED,
        "fields": [
            {
                "name": "① 重要指標発表日の統計的リスク",
                "value": (
                    "FOMC・NFP・日銀会合の発表前後30分は\n"
                    "通常の3〜5倍のボラティリティが発生します。\n"
                    "損切りラインを瞬時に突き破るケースが多く、\n"
                    "テクニカル分析が機能しにくい環境です。"
                ),
                "inline": False
            },
            {
                "name": "② 弱気相場でのエントリーは「落ちるナイフを掴む」行為",
                "value": (
                    "市場全体が下落トレンドのときに個別株を買っても、\n"
                    "指数の下げに引きずられて上昇シグナルが機能しません。\n"
                    "強気銘柄でさえ、地合いの悪さに負けて下落するのが現実です。"
                ),
                "inline": False
            },
            {
                "name": "③ 見送りもれっきとした「判断」",
                "value": (
                    "プロのトレーダーは「今日は動かない」という決断を\n"
                    "積極的に下します。損失ゼロも立派な成果です。\n"
                    "資金を守ることが、次のチャンスへの備えになります。"
                ),
                "inline": False
            }
        ]
    }]})

    # ── Embed③：今日やるべきこと ──
    payloads.append({"embeds": [{
        "title": "✅ 今日やるべきこと",
        "color": COLOR_BLUE,
        "fields": [
            {
                "name": "相場観察",
                "value": (
                    "・発表後の市場の反応を観察する\n"
                    "・「どの銘柄が下げ渋っているか」をメモしておく\n"
                    "・強い銘柄は明日以降のウォッチリスト候補になる"
                ),
                "inline": False
            },
            {
                "name": "明日への準備",
                "value": (
                    "・指標発表後に相場が落ち着けば、明朝のシグナルが有効になる\n"
                    "・発表内容がポジティブなら、明日の市場スコアが改善する可能性が高い\n"
                    "・Bot は明朝8時に改めて市場を評価して通知します"
                ),
                "inline": False
            }
        ],
        "footer": {"text": "明朝8:00に改めてシグナルを配信します"}
    }]})

    return payloads
