"""
scorer.py
スクリーニング通過銘柄にテクニカル指標を計算して
0〜100の信頼度スコアを付与する
"""

import pandas as pd
import numpy as np


# ============================================================
# テクニカル指標計算
# ============================================================

def calc_rsi(series: pd.Series, period: int = 14) -> float:
    """RSIを計算（最新値のみ返す）"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 1) if not rsi.empty else 50.0


def calc_macd(series: pd.Series):
    """
    MACDを計算
    戻り値: (macd値, シグナル値, ヒストグラム値, ゴールデンクロスかどうか)
    """
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal

    # ゴールデンクロス：前日はmacd<signal、当日はmacd>signal
    golden_cross = False
    if len(macd) >= 2:
        golden_cross = (macd.iloc[-2] < signal.iloc[-2]) and (macd.iloc[-1] >= signal.iloc[-1])

    return round(macd.iloc[-1], 4), round(signal.iloc[-1], 4), round(hist.iloc[-1], 4), golden_cross


def calc_bollinger(series: pd.Series, period: int = 20):
    """
    ボリンジャーバンドを計算
    戻り値: (上限, 中心, 下限, 現在値の位置%）
    """
    ma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    last = series.iloc[-1]
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
    perfect_order = ma5 > ma25 and (ma75 is None or ma25 > ma75)
    return round(ma5, 0), round(ma25, 0), perfect_order


# ============================================================
# 信頼度スコア計算
# ============================================================

def calculate_score(row: dict, market_score: int) -> dict:
    """
    1銘柄のスコアを計算して辞書で返す

    スコア配分:
    - 市場環境    : 最大20点（market_contextから）
    - 出来高比率  : 最大20点
    - 価格変化率  : 最大15点
    - RSI         : 最大15点
    - MACD        : 最大15点
    - ボリンジャー: 最大10点
    - 移動平均    :  最大5点
    合計100点
    """
    df = row.get("_df", pd.DataFrame())
    if df.empty or len(df) < 26:
        return {"score": 0, "indicators": {}}

    close_series = df["Close"].astype(float)
    score = 0
    indicators = {}

    # ① 市場環境スコア（最大20点）
    # market_scoreは0〜40点なので半分にして20点満点に
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
    indicators["volume_ratio"] = vr
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
        # 理想的な上昇途中
        score += 15
    elif 45 <= rsi < 50:
        score += 8
    elif rsi > 70:
        # 買われすぎ気味 → 減点
        score += 5
    else:
        score += 0

    # ⑤ MACD（最大15点）
    macd_val, signal_val, hist_val, golden_cross = calc_macd(close_series)
    indicators["macd"] = macd_val
    indicators["macd_signal"] = signal_val
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
        # 中心〜上限の間で上昇中が理想
        score += 10
    elif bb_pos > 80:
        # 上限突破は過熱感あり
        score += 5
    elif 30 <= bb_pos < 50:
        score += 3
    else:
        score += 0

    # ⑦ 移動平均パーフェクトオーダー（最大5点）
    ma5, ma25, perfect_order = calc_moving_averages(close_series)
    indicators["ma5"] = ma5
    indicators["ma25"] = ma25
    indicators["perfect_order"] = perfect_order
    if perfect_order:
        score += 5

    return {
        "score": round(score, 1),
        "indicators": indicators
    }


# ============================================================
# エントリー価格の参考値を計算
# ============================================================

def calc_entry_targets(row: dict) -> dict:
    """
    参考エントリー価格・利確・損切りの目安を返す
    """
    close = row.get("close", 0)
    if close == 0:
        return {}

    entry   = close                                  # 寄り付き付近
    target  = round(close * 1.015, 0)               # +1.5%で利確
    stop    = round(close * 0.993, 0)               # -0.7%で損切り
    rr_ratio = round((target - entry) / (entry - stop), 2)  # リスクリワード比

    return {
        "entry": entry,
        "target": target,
        "stop": stop,
        "rr_ratio": rr_ratio
    }
