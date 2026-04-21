"""
scorer.py v5.3
スクリーニング通過銘柄にテクニカル指標を計算して
0〜100の信頼度スコアを付与する

v5.3変更点:
  - calc_macd の golden_cross を bool() でキャスト（JSON保存バグ修正）
  - calc_moving_averages の perfect_order を bool() でキャスト（同上）
  - calc_entry_targets をピボットポイント + ATRベースに全面改修
    - エントリー : ピボット付近（前日終値との中間値、最低+0.3%）
    - 利確①     : 第1抵抗線（R1）← 半分はここで利確
    - 利確②     : 第2抵抗線（R2）← 残りを引っ張る
    - 損切り     : ATR×0.5（ボラティリティ連動）
    - RR比1.5未満は空dictを返して候補から除外
"""

import pandas as pd
import numpy as np


# ============================================================
# テクニカル指標計算
# ============================================================

def calc_rsi(series: pd.Series, period: int = 14) -> float:
    """RSIを計算（最新値のみ返す）。NaNは中立値50.0を返す"""
    delta    = series.diff()
    gain     = delta.where(delta > 0, 0.0)
    loss     = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    rsi      = 100 - (100 / (1 + rs))
    val      = rsi.iloc[-1] if not rsi.empty else np.nan
    return round(float(val), 1) if not np.isnan(val) else 50.0


def calc_macd(series: pd.Series):
    """
    MACDを計算
    戻り値: (macd値, シグナル値, ヒストグラム値, ゴールデンクロスかどうか)
    """
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal

    # bool()でキャスト → numpy bool_ → Python bool（JSON保存バグ修正）
    golden_cross = False
    if len(macd) >= 2:
        golden_cross = bool(
            (macd.iloc[-2] < signal.iloc[-2]) and (macd.iloc[-1] >= signal.iloc[-1])
        )

    return round(macd.iloc[-1], 4), round(signal.iloc[-1], 4), round(hist.iloc[-1], 4), golden_cross


def calc_bollinger(series: pd.Series, period: int = 20):
    """
    ボリンジャーバンドを計算
    戻り値: (上限, 中心, 下限, 現在値の位置%）
    """
    ma         = series.rolling(period).mean()
    std        = series.rolling(period).std()
    upper      = ma + 2 * std
    lower      = ma - 2 * std
    last       = series.iloc[-1]
    band_range = upper.iloc[-1] - lower.iloc[-1]
    position_pct = (last - lower.iloc[-1]) / band_range * 100 if band_range > 0 else 50
    return round(upper.iloc[-1], 0), round(ma.iloc[-1], 0), round(lower.iloc[-1], 0), round(position_pct, 1)


def calc_moving_averages(series: pd.Series):
    """
    5日・25日・75日移動平均とパーフェクトオーダー判定
    """
    ma5  = series.rolling(5).mean().iloc[-1]
    ma25 = series.rolling(25).mean().iloc[-1]
    ma75 = series.rolling(75).mean().iloc[-1] if len(series) >= 75 else None

    # bool()でキャスト → numpy bool_ → Python bool（JSON保存バグ修正）
    perfect_order = bool(ma5 > ma25 and (ma75 is None or ma25 > ma75))

    return round(ma5, 0), round(ma25, 0), perfect_order


# ============================================================
# 信頼度スコア計算
# ============================================================

def calculate_score(row: dict, market_score: int) -> dict:
    """
    1銘柄のスコアを計算して辞書で返す

    スコア配分:
    - 市場環境    : 最大20点
    - 出来高比率  : 最大20点
    - 価格変化率  : 最大15点
    - RSI         : 最大15点
    - MACD        : 最大15点
    - ボリンジャー: 最大10点
    - 移動平均    : 最大5点
    合計100点
    """
    df = row.get("_df", pd.DataFrame())
    if df.empty or len(df) < 26:
        return {"score": 0, "indicators": {}}

    close_series = df["Close"].astype(float)
    score = 0
    indicators = {}

    # ① 市場環境スコア（最大20点）
    market_points = min(market_score / 2, 20)
    score += market_points

    # ② 出来高比率（最大20点）
    vr = row.get("volume_ratio", 1.0)
    if vr >= 3.0:
        vol_points = 20
    elif vr >= 2.0:
        vol_points = 15
    elif vr >= 1.5:
        vol_points = 10
    else:
        vol_points = 0
    score += vol_points
    indicators["volume_ratio"]  = vr
    indicators["volume_points"] = vol_points

    # ③ 価格変化率（最大15点）
    pcp = row.get("price_change_pct", 0)
    if pcp >= 3.0:
        price_points = 15
    elif pcp >= 2.0:
        price_points = 12
    elif pcp >= 1.0:
        price_points = 8
    elif pcp >= 0.5:
        price_points = 4
    else:
        price_points = 0
    score += price_points
    indicators["price_change_pct"] = pcp

    # ④ RSI（最大15点）
    rsi = calc_rsi(close_series)
    indicators["rsi"] = rsi
    if 50 <= rsi <= 70:
        score += 15
    elif 45 <= rsi < 50:
        score += 8
    elif rsi > 70:
        score += 5
    else:
        score += 0

    # ⑤ MACD（最大15点）
    macd_val, signal_val, hist_val, golden_cross = calc_macd(close_series)
    indicators["macd"]              = macd_val
    indicators["macd_signal"]       = signal_val
    indicators["macd_golden_cross"] = golden_cross
    if golden_cross:
        score += 15
    elif macd_val > signal_val and hist_val > 0:
        score += 10
    elif macd_val > 0:
        score += 5
    else:
        score += 0

    # ⑥ ボリンジャーバンド（最大10点）
    bb_upper, bb_mid, bb_lower, bb_pos = calc_bollinger(close_series)
    indicators["bb_position"] = bb_pos
    if 50 <= bb_pos <= 80:
        score += 10
    elif bb_pos > 80:
        score += 5
    elif 30 <= bb_pos < 50:
        score += 3
    else:
        score += 0

    # ⑦ 移動平均パーフェクトオーダー（最大5点）
    ma5, ma25, perfect_order = calc_moving_averages(close_series)
    indicators["ma5"]           = ma5
    indicators["ma25"]          = ma25
    indicators["perfect_order"] = perfect_order
    if perfect_order:
        score += 5

    return {
        "score":      round(score, 1),
        "indicators": indicators
    }


# ============================================================
# エントリー・利確・損切り価格の算出
# ============================================================

def calc_entry_targets(row: dict) -> dict:
    """
    ピボットポイント + ATRベースの現実的な価格を算出する

    【設計根拠】
    エントリー : ピボット付近（前日終値とピボットの中間値、最低前日終値+0.3%）
                 → 寄り付きのギャップアップを考慮しつつ現実的な約定価格
    利確①(R1) : 第1抵抗線 = 機関投資家の売り圧力が集中しやすい価格帯
                 → ここで半分利確してリスクをゼロに近づける
    利確②(R2) : 第2抵抗線 = 強いトレンドが続いた場合の上値目標
                 → 残りポジションをここまで引っ張る
    損切り     : エントリー − ATR×0.5（ボラティリティ連動）
                 → ボラが高い銘柄は広く、安定銘柄は狭くリスクを均一化
    RR比       : 1.5未満の場合は空dictを返して候補から除外
                 → リスクに見合わないトレードを事前に弾く
    """
    close = row.get("close", 0)
    if close == 0:
        return {}

    df = row.get("_df", None)

    if df is not None and len(df) >= 15 and \
       all(c in df.columns for c in ["High", "Low", "Close"]):
        try:
            high         = df["High"].astype(float)
            low          = df["Low"].astype(float)
            close_series = df["Close"].astype(float)

            # 前日の高値・安値・終値
            prev_high  = float(high.iloc[-2])
            prev_low   = float(low.iloc[-2])
            prev_close = float(close_series.iloc[-2])

            # ── ピボットポイント計算 ──
            pivot = (prev_high + prev_low + prev_close) / 3
            r1    = 2 * pivot - prev_low          # 第1抵抗線
            r2    = pivot + (prev_high - prev_low) # 第2抵抗線
            s1    = 2 * pivot - prev_high          # 第1支持線（損切り参考）

            # ── ATR計算（最大14日）──
            tr_list = []
            for i in range(1, min(15, len(df))):
                h  = float(high.iloc[-i])
                l  = float(low.iloc[-i])
                pc = float(close_series.iloc[-i - 1])
                tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
            atr = sum(tr_list) / len(tr_list) if tr_list else close * 0.01

            # ── エントリー価格 ──
            # 前日終値とピボットの中間値（最低でも前日終値+0.3%）
            entry = round(max(close * 1.003, (close + pivot) / 2), 0)

            # ── 損切り：ATR×0.5（ボラティリティ連動）──
            stop = round(entry - atr * 0.5, 0)
            if stop >= entry:
                return {}

            # ── 利確①：R1（R1がエントリーより十分上にない場合は+1%）──
            target1 = round(r1, 0) if r1 > entry * 1.005 else round(entry * 1.01, 0)

            # ── 利確②：R2（R2がR1より十分上にない場合はR1+2%）──
            target2 = round(r2, 0) if r2 > target1 * 1.005 else round(target1 * 1.02, 0)

            # ── RR比（利確①基準）──
            risk   = entry - stop
            reward = target1 - entry
            if risk <= 0:
                return {}
            rr_ratio = round(reward / risk, 2)

            # RR比1.5未満はリスクに見合わないため除外
            if rr_ratio < 1.5:
                return {}

            return {
                "entry":    int(entry),
                "target1":  int(target1),
                "target2":  int(target2),
                "stop":     int(stop),
                "rr_ratio": rr_ratio,
                "pivot":    int(round(pivot, 0)),
                "s1":       int(round(s1, 0)),
                "atr":      int(round(atr, 0)),
            }

        except Exception as e:
            print(f"  ピボット計算エラー: {e} → フォールバック使用")

    # ── フォールバック（DataFrame不足・計算失敗時）──
    entry    = int(round(close * 1.005, 0))
    target1  = int(round(entry * 1.015, 0))
    target2  = int(round(entry * 1.030, 0))
    stop     = int(round(entry * 0.993, 0))
    risk     = entry - stop
    reward   = target1 - entry
    if risk <= 0:
        return {}
    rr_ratio = round(reward / risk, 2)
    if rr_ratio < 1.5:
        return {}
    return {
        "entry":    entry,
        "target1":  target1,
        "target2":  target2,
        "stop":     stop,
        "rr_ratio": rr_ratio,
    }
