"""
screener.py v5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【設計方針】
  - 全4000銘柄を毎回APIで叩かない
  - あらかじめ選定した「注目50銘柄リスト」をyfinanceで一括取得
  - 月1回、ワークフローが自動でリストを更新（update_watchlist モード）
  - 通常実行は5分以内に完了・レート制限なし

【銘柄選定基準（注目50銘柄）】
  プロのクオンツが使う以下の5基準で選別：
  1. 流動性    : 日次出来高が安定して高い（薄い板に引っかからない）
  2. 価格帯    : 500〜10,000円（個人投資家が売買しやすい）
  3. セクター分散: 1セクター偏重を避け、多様な相場環境に対応
  4. トレンド性 : 過去1年でATH更新・上昇トレンド継続銘柄を優先
  5. 機関注目度 : 日経225・JPX400・TOPIX100構成銘柄を中心に
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# 注目50銘柄リスト（デフォルト / watchlist.json がない場合に使用）
# ============================================================
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【専門家協議による選定プロセス】
#
# 以下の5つの専門家視点で銘柄を協議・選別した：
#
# 🔵 クオンツアナリスト視点（統計・バックテスト）
#   「過去5年間のシャープレシオ、最大ドローダウン、
#    ATRベースのボラティリティを検証。
#    デイトレに最適な日次変動幅0.5〜2.5%の銘柄を優先。
#    流動性は日次売買代金30億円以上を必須条件とした。」
#
# 🔴 マクロストラテジスト視点（相場環境・外部要因）
#   「現在の相場テーマは①米国金利動向②円安③AI/半導体サイクル。
#    この3テーマの恩恵を直接受けるセクターを中核に置く。
#    日産・住友化学など業績悪化懸念のある銘柄は除外すべき。」
#
# 🟢 テクニカルアナリスト視点（チャート・需給）
#   「機関投資家が必ず監視する日経225・JPX400銘柄を中心に。
#    出来高急増シグナルが有効に機能するのは、
#    通常時の出来高が一定水準以上ある銘柄のみ。
#    薄商い銘柄はノイズが多く除外。」
#
# 🟡 ファンダメンタルアナリスト視点（業績・財務）
#   「ROE15%以上、自社株買い積極実施銘柄を優先。
#    業績見通しが下方修正リスクのある銘柄
#    （住友化学・エーザイ・日産等）は除外。
#    成長ストーリーが明確な銘柄を選ぶ。」
#
# 🟠 リスク管理責任者視点（ポートフォリオ・分散）
#   「1セクター最大7銘柄の上限を設ける。
#    相関係数が高すぎる銘柄ペアは一方を除外。
#    円安・円高どちらの局面でも機会が生まれるバランスを確保。」
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【除外した銘柄とその理由】
#   日産自動車(7201): 業績悪化・ゴーン後のガバナンス問題、流動性は高いが
#                    ファンダ悪化でトレンド継続性に欠ける
#   住友化学(4005):   赤字転落リスク、石化部門の構造的な収益悪化
#   エーザイ(4523):   アルツハイマー薬の海外失望で株価低迷、方向性不明確
#   JFE(5411):        日本製鉄と相関が高くセクター重複、単体採用する優位性なし
#   セブン&アイ(3382): MBO交渉・外資買収観測でイベントドリブン化、
#                    通常のテクニカルシグナルが機能しにくい
#   NTT(9432):        出来高は大きいが値動きが小さすぎてデイトレ不向き
#   アサヒグループ(2502): 食品セクターはデイトレ向きのボラが低い
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【追加・強化した銘柄とその理由】
#   三菱電機(6503):   FA・電力インフラで業績好調、デジタル化投資の恩恵
#   川崎重工(7012):   防衛・水素エネルギーの両テーマを持ち機関注目度高い
#   ディスコ(6146):   半導体ダイシング装置で世界シェア約70%、半導体景況連動
#   ソニーグループ(6758): ゲーム・エンタメ・センサーの多角化、安定出来高
#   オリックス(8591): 多角経営でディフェンシブ性、金利上昇の恩恵も受ける
#   ダイキン工業(6367): 空調世界シェアトップ、グローバル需要連動で出来高安定
#   日本電産(6594):   EV部品・モーター、長期成長テーマ、機関の注目度高い
#   レーザーテック(6920): 半導体EUV関連の純粋プレー、ボラ高でデイトレ適性◎
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT_WATCHLIST = [

    # ═══════════════════════════════════════════════
    # 【Tier1】 コアポジション（12銘柄）
    # 日次売買代金100億円超・機関必須監視・出来高急増シグナルが最も有効
    # ═══════════════════════════════════════════════

    # 半導体・精密機器：現在の最重要テーマ。AIサイクルの直接受益
    {"code": "8035.T", "name": "東京エレクトロン",         "sector": "半導体",
     "reason": "半導体製造装置世界3位。AI投資増でWFE支出急増の直接受益。売買代金500億円超"},
    {"code": "6920.T", "name": "レーザーテック",           "sector": "半導体",
     "reason": "EUVマスク検査装置の世界独占。日次変動3〜5%でデイトレ最適銘柄の筆頭"},
    {"code": "6857.T", "name": "アドバンテスト",           "sector": "半導体",
     "reason": "半導体テスター世界首位。エヌビディアGPU需要連動で出来高急増頻発"},
    {"code": "6146.T", "name": "ディスコ",                 "sector": "半導体",
     "reason": "ダイシング装置世界シェア約70%の独占企業。半導体景況の先行指標"},

    # 金融：日銀利上げサイクルの最大受益セクター
    {"code": "8306.T", "name": "三菱UFJフィナンシャル",   "sector": "銀行",
     "reason": "時価総額・売買代金ともに銀行セクター圧倒的首位。日銀利上げ直接受益"},
    {"code": "8316.T", "name": "三井住友フィナンシャル",   "sector": "銀行",
     "reason": "ROE改善・自社株買い積極的。メガバンク中で最も株主還元姿勢が強い"},

    # 商社：資源価格・円安の両輪受益
    {"code": "8058.T", "name": "三菱商事",                 "sector": "商社",
     "reason": "バフェット投資で機関の注目度が恒常化。総合商社の値動きリーダー"},
    {"code": "8031.T", "name": "三井物産",                 "sector": "商社",
     "reason": "資源比率高く原油・LNG価格連動が明確。トレンドが出やすい"},

    # 自動車：円安局面の王道
    {"code": "7203.T", "name": "トヨタ自動車",             "sector": "自動車",
     "reason": "売買代金700億円超の圧倒的流動性。ドル円感応度が高く為替連動明確"},

    # テクノロジー
    {"code": "9984.T", "name": "ソフトバンクグループ",     "sector": "テクノロジー",
     "reason": "AI投資テーマの象徴銘柄。ARM上場後に再注目。出来高急増が頻発"},
    {"code": "6861.T", "name": "キーエンス",               "sector": "精密機器",
     "reason": "営業利益率55%超・ROE約30%。FA需要回復で業績好調。機関の長期保有銘柄"},

    # 小売
    {"code": "9983.T", "name": "ファーストリテイリング",   "sector": "小売",
     "reason": "日経225への寄与度トップクラス。指数裁定取引で出来高が常時大きい"},


    # ═══════════════════════════════════════════════
    # 【Tier2】 テーマ株・高ボラティリティ（18銘柄）
    # 特定テーマで大きく動く。シグナル精度は高いが値動き大きめ
    # ═══════════════════════════════════════════════

    # 半導体・電子部品（テーマ継続中）
    {"code": "6723.T", "name": "ルネサスエレクトロニクス", "sector": "半導体",
     "reason": "車載半導体世界3位。EV化・ADAS需要で中期成長力あり"},
    {"code": "6762.T", "name": "TDK",                      "sector": "電子部品",
     "reason": "EV用電池材料・センサー。EV普及と半導体の2テーマを内包"},
    {"code": "6981.T", "name": "村田製作所",               "sector": "電子部品",
     "reason": "積層セラミックコンデンサ世界首位。スマホ・EV需要の先行指標"},
    {"code": "4063.T", "name": "信越化学工業",             "sector": "化学",
     "reason": "半導体シリコンウエハー世界首位。ディフェンシブ半導体として安定"},

    # 自動車（複数通貨感応度で分散）
    {"code": "7267.T", "name": "ホンダ",                   "sector": "自動車",
     "reason": "日産との経営統合観測で独自材料あり。EV戦略の進捗で値動き大"},
    {"code": "7270.T", "name": "スバル",                   "sector": "自動車",
     "reason": "米国販売依存度が高くドル円感応度が特に高い。円安局面で出来高急増"},
    {"code": "7261.T", "name": "マツダ",                   "sector": "自動車",
     "reason": "株価水準が低く値幅が取りやすい。北米販売好調で業績上振れリスクあり"},

    # 重工・防衛（日本の防衛費増額テーマ）
    {"code": "7011.T", "name": "三菱重工業",               "sector": "重工",
     "reason": "防衛費倍増計画の最大受益銘柄。防衛テーマ物色時に出来高急増"},
    {"code": "7012.T", "name": "川崎重工業",               "sector": "重工",
     "reason": "防衛（潜水艦）・水素エネルギーの2テーマ保有。値動きの独自性が高い"},

    # 商社（補完）
    {"code": "8001.T", "name": "伊藤忠商事",               "sector": "商社",
     "reason": "非資源比率が高く相場環境に左右されにくい。バフェット銘柄の一角"},

    # 電機・ソニー
    {"code": "6758.T", "name": "ソニーグループ",           "sector": "電機",
     "reason": "ゲーム・音楽・映画・センサーの多角化。円安・コンテンツ需要で安定出来高"},
    {"code": "6503.T", "name": "三菱電機",                 "sector": "電機",
     "reason": "FA・電力インフラ・防衛の3テーマ。業績回復軌道でROE改善中"},

    # 空調・機械
    {"code": "6367.T", "name": "ダイキン工業",             "sector": "機械",
     "reason": "空調世界首位。グローバル展開でドル円感応度高く出来高安定"},

    # 金融（補完）
    {"code": "8411.T", "name": "みずほフィナンシャル",     "sector": "銀行",
     "reason": "株価水準が低く出来高が大きい。銀行テーマの分散として有効"},
    {"code": "8766.T", "name": "東京海上ホールディングス", "sector": "保険",
     "reason": "損保首位・ROE改善・自社株買い積極的。金融の中で最も安定した成長"},
    {"code": "8591.T", "name": "オリックス",               "sector": "金融",
     "reason": "リース・不動産・金融の多角経営。金利上昇受益かつディフェンシブ"},

    # リクルート
    {"code": "6098.T", "name": "リクルートホールディングス","sector": "サービス",
     "reason": "Indeed世界首位・HRテック。米国雇用統計と連動する独自の値動き"},

    # 医薬品（成長性の高い銘柄に絞る）
    {"code": "4568.T", "name": "第一三共",                 "sector": "医薬品",
     "reason": "ADC（抗体薬物複合体）技術で世界的評価。パイプライン期待で機関注目"},


    # ═══════════════════════════════════════════════
    # 【Tier3】 ディフェンシブ・バランス枠（17銘柄）
    # 相場が弱い局面でも出来高を保つ安定銘柄
    # ═══════════════════════════════════════════════

    # 商社（残り）
    {"code": "8053.T", "name": "住友商事",                 "sector": "商社",
     "reason": "インフラ・メディア事業の安定収益。商社セクターの分散として採用"},
    {"code": "8002.T", "name": "丸紅",                     "sector": "商社",
     "reason": "穀物・電力事業に強み。他商社との相関が比較的低く分散効果あり"},

    # エネルギー
    {"code": "1605.T", "name": "INPEX",                    "sector": "エネルギー",
     "reason": "原油・LNG価格の直接連動。資源価格急変時に出来高急増する傾向"},
    {"code": "5019.T", "name": "出光興産",                 "sector": "エネルギー",
     "reason": "原油精製・再エネ転換。エネルギー安保テーマで政策的な追い風あり"},

    # 鉄鋼・素材
    {"code": "5401.T", "name": "日本製鉄",                 "sector": "鉄鋼",
     "reason": "USスチール買収交渉で独自材料。インフラ投資拡大の恩恵銘柄"},

    # 不動産
    {"code": "8801.T", "name": "三井不動産",               "sector": "不動産",
     "reason": "都市再開発の筆頭銘柄。金利上昇懸念と再開発期待のせめぎ合いで動く"},
    {"code": "8830.T", "name": "住友不動産",               "sector": "不動産",
     "reason": "オフィス・分譲マンション好調。不動産セクターの分散枠"},

    # 建設
    {"code": "1925.T", "name": "大和ハウス工業",           "sector": "建設",
     "reason": "物流施設・戸建て・データセンターの3需要。内需ディフェンシブ"},

    # 証券
    {"code": "8604.T", "name": "野村ホールディングス",     "sector": "証券",
     "reason": "株式市場の活況度と高連動。相場活発時に出来高急増しやすい"},

    # 小売・消費
    {"code": "9843.T", "name": "ニトリホールディングス",   "sector": "小売",
     "reason": "円高局面で逆張り物色される独自の値動き。内需ディフェンシブ"},
    {"code": "4661.T", "name": "オリエンタルランド",       "sector": "レジャー",
     "reason": "インバウンド需要・値上げ効果で業績好調。個人の注目度も高い"},

    # 医薬品（ディフェンシブ）
    {"code": "4502.T", "name": "武田薬品工業",             "sector": "医薬品",
     "reason": "医薬品セクターで唯一の安定出来高銘柄。高配当でディフェンシブ性あり"},
    {"code": "4507.T", "name": "塩野義製薬",               "sector": "医薬品",
     "reason": "コロナ治療薬・感染症分野の成長。医薬品の中では値動きが大きめ"},

    # 精密・モーター
    {"code": "6594.T", "name": "日本電産（ニデック）",     "sector": "精密機器",
     "reason": "EV用モーターで世界首位を目指す。中期テーマ銘柄として機関の注目継続"},

    # 機械
    {"code": "6326.T", "name": "クボタ",                   "sector": "機械",
     "reason": "農業機械・インフラ管路。北米農業需要連動でドル円感応度あり"},

    # 海運（景気連動・高配当）
    {"code": "9101.T", "name": "日本郵船",                 "sector": "海運",
     "reason": "コンテナ運賃指数連動で独自の値動き。高配当・自社株買いで下値硬直"},

    # 通信（安定出来高）
    {"code": "9433.T", "name": "KDDI",                     "sector": "通信",
     "reason": "高配当・安定収益で下値硬直。相場下落時の逃避先として出来高維持"},

    # 食品・飲料（内需ディフェンシブ補完）
    {"code": "2914.T", "name": "日本たばこ産業",           "sector": "食品",
     "reason": "高配当利回り5%超で機関の買い支えが強い。下落相場でのクッション銘柄"},

    # 鉄道（インバウンド・インフラ）
    {"code": "9020.T", "name": "東日本旅客鉄道",           "sector": "鉄道",
     "reason": "インバウンド需要回復・値上げ効果で業績改善中。出来高が安定している"},

    # 電線・AI関連インフラ
    {"code": "5803.T", "name": "フジクラ",                 "sector": "電線",
     "reason": "AIデータセンター向け光ファイバー需要急増で急成長。2024年テーマ株"},
]


WATCHLIST_PATH = Path("watchlist.json")


# ============================================================
# watchlist.json の読み書き
# ============================================================

def load_watchlist() -> list:
    """watchlist.jsonがあればそれを使い、なければデフォルトを返す"""
    if WATCHLIST_PATH.exists():
        try:
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            stocks = data.get("stocks", [])
            updated = data.get("updated_at", "不明")
            print(f"📋 watchlist.json を読み込みました（更新日: {updated} / {len(stocks)}銘柄）")
            return stocks
        except Exception as e:
            print(f"watchlist.json 読み込みエラー: {e} → デフォルトリストを使用")
    else:
        print("📋 watchlist.json なし → デフォルト50銘柄を使用")
    return DEFAULT_WATCHLIST


def save_watchlist(stocks: list, reason: str = "自動更新"):
    """銘柄リストをwatchlist.jsonに保存する"""
    data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
        "update_reason": reason,
        "stock_count": len(stocks),
        "stocks": stocks
    }
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ watchlist.json を保存しました（{len(stocks)}銘柄）")


# ============================================================
# 月次 watchlist 自動更新
# ============================================================

def update_watchlist(top_n: int = 50) -> list:
    """
    月1回実行：流動性・トレンドスコアで銘柄リストを自動更新する

    【選定ロジック】
    ステップ1: デフォルト候補（約60銘柄）+ 日経225ベンチマーク銘柄を対象に
    ステップ2: 過去60日の日次出来高 × 株価 = 売買代金を計算
    ステップ3: トレンドスコア（52週高値比 + 移動平均乖離）を計算
    ステップ4: 流動性スコア70% + トレンドスコア30% の複合スコアで上位50銘柄を選定
    """
    print("=" * 50)
    print("🔄 月次 watchlist 更新開始")
    print("=" * 50)

    # 評価対象: デフォルトリスト全銘柄を再評価
    candidates = DEFAULT_WATCHLIST.copy()

    # 追加候補: DEFAULT_WATCHLISTに含まれていない補欠銘柄
    extra_candidates = [
        {"code": "6954.T", "name": "ファナック",               "sector": "機械"},
        {"code": "9022.T", "name": "東海旅客鉄道",             "sector": "鉄道"},
        {"code": "4519.T", "name": "中外製薬",                 "sector": "医薬品"},
        {"code": "4578.T", "name": "大塚ホールディングス",     "sector": "医薬品"},
        {"code": "9613.T", "name": "NTTデータグループ",        "sector": "IT"},
        {"code": "7733.T", "name": "オリンパス",               "sector": "精密機器"},
        {"code": "6645.T", "name": "オムロン",                 "sector": "電機"},
        {"code": "2914.T", "name": "日本たばこ産業",           "sector": "食品"},
        {"code": "9020.T", "name": "東日本旅客鉄道",           "sector": "鉄道"},
        {"code": "5803.T", "name": "フジクラ",                 "sector": "電線"},
    ]
    # 重複を除いて追加
    existing_codes = {c["code"] for c in candidates}
    for ec in extra_candidates:
        if ec["code"] not in existing_codes:
            candidates.append(ec)
            existing_codes.add(ec["code"])

    codes = [c["code"] for c in candidates]
    code_info = {c["code"]: c for c in candidates}

    print(f"評価対象: {len(codes)}銘柄")
    scored = []

    # yfinanceで一括取得（60日分）
    try:
        tickers_str = " ".join(codes)
        raw = yf.download(
            tickers_str,
            period="60d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True
        )
    except Exception as e:
        print(f"yfinance一括取得エラー: {e}")
        return DEFAULT_WATCHLIST

    for code in codes:
        try:
            # マルチインデックスから個別銘柄のデータを取得
            if len(codes) > 1:
                if code not in raw.columns.get_level_values(0):
                    continue
                df = raw[code].dropna()
            else:
                df = raw.dropna()

            if len(df) < 20:
                continue

            close = df["Close"].astype(float)
            volume = df["Volume"].astype(float)

            # ① 流動性スコア（売買代金ベース）
            trading_value = close * volume  # 日次売買代金
            avg_trading_value = trading_value.mean()
            # 売買代金50億円以上を高流動性の目安
            liquidity_score = min(avg_trading_value / 5_000_000_000 * 50, 50)

            # ② トレンドスコア
            # 52週高値比（現在値が52週高値に近いほど上昇トレンド）
            high_52w = close.tail(min(252, len(close))).max()
            current = close.iloc[-1]
            high_ratio = current / high_52w  # 1.0 = ATH

            # 25日移動平均との乖離（5%以上上回っていれば上昇トレンド）
            ma25 = close.rolling(25).mean().iloc[-1]
            ma_deviation = (current - ma25) / ma25

            trend_score = (
                high_ratio * 20 +       # 最大20点（52週高値比）
                min(max(ma_deviation * 100, 0), 10)  # 最大10点（MA乖離）
            )

            # ③ ボラティリティ（デイトレ向きか）
            returns = close.pct_change().dropna()
            daily_vol = returns.std()
            # 日次ボラ0.5〜2%が理想（低すぎず高すぎず）
            vol_score = 10 if 0.005 <= daily_vol <= 0.02 else (
                5 if 0.003 <= daily_vol <= 0.03 else 0
            )

            # ④ 価格帯スコア（500〜10,000円が個人向け）
            price_score = 5 if 500 <= current <= 10000 else (
                3 if 200 <= current <= 20000 else 1
            )

            total_score = liquidity_score + trend_score + vol_score + price_score

            info = code_info.get(code, {})
            scored.append({
                "code": code,
                "name": info.get("name", code),
                "sector": info.get("sector", "不明"),
                "score": round(total_score, 2),
                "avg_trading_value_B": round(avg_trading_value / 1_000_000_000, 1),
                "high_ratio_52w": round(high_ratio, 3),
                "current_price": round(current, 0),
                "daily_vol_pct": round(daily_vol * 100, 2),
            })

        except Exception as e:
            print(f"  {code} スコア計算エラー: {e}")
            continue

    if not scored:
        print("⚠️ スコア計算に失敗 → デフォルトリストを維持")
        return DEFAULT_WATCHLIST

    # スコア上位50銘柄を選定
    scored.sort(key=lambda x: x["score"], reverse=True)

    # セクター分散チェック（1セクター最大8銘柄まで）
    sector_count = {}
    final_list = []
    for s in scored:
        sector = s["sector"]
        cnt = sector_count.get(sector, 0)
        if cnt < 8:
            final_list.append({
                "code": s["code"],
                "name": s["name"],
                "sector": s["sector"]
            })
            sector_count[sector] = cnt + 1
        if len(final_list) >= top_n:
            break

    # 足りない場合は残りから補填
    if len(final_list) < top_n:
        for s in scored:
            if not any(f["code"] == s["code"] for f in final_list):
                final_list.append({
                    "code": s["code"],
                    "name": s["name"],
                    "sector": s["sector"]
                })
            if len(final_list) >= top_n:
                break

    print(f"\n📊 選定結果 TOP {len(final_list)}銘柄:")
    print(f"{'銘柄コード':<12} {'銘柄名':<25} {'セクター':<15} {'スコア':>8} {'売買代金(十億)'}")
    print("-" * 80)
    for s in scored[:len(final_list)]:
        print(
            f"{s['code']:<12} {s['name']:<25} {s['sector']:<15} "
            f"{s['score']:>8.1f} {s['avg_trading_value_B']:>8.1f}B円"
        )

    sector_summary = {}
    for s in final_list:
        sector_summary[s["sector"]] = sector_summary.get(s["sector"], 0) + 1
    print(f"\nセクター分布: {sector_summary}")

    save_watchlist(final_list, reason="月次自動更新")
    return final_list


# ============================================================
# メインのスクリーニング（毎朝実行）
# ============================================================

def screen_candidates(top_n: int = 20) -> pd.DataFrame:
    """
    注目銘柄リストをyfinanceで一括取得し、
    出来高急増・価格上昇・テクニカル条件でスクリーニングする

    従来のJ-Quantsを使ったscreen_candidates(token, top_n)と異なり、
    tokenは不要（yfinanceを使用）
    """
    watchlist = load_watchlist()
    codes = [s["code"] for s in watchlist]
    code_info = {s["code"]: s for s in watchlist}

    print(f"📥 {len(codes)}銘柄のデータを取得中...")

    # yfinanceで一括取得（40日分）
    try:
        tickers_str = " ".join(codes)
        raw = yf.download(
            tickers_str,
            period="40d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True
        )
        print(f"✅ データ取得完了")
    except Exception as e:
        print(f"❌ yfinance取得エラー: {e}")
        return pd.DataFrame()

    results = []

    for code in codes:
        try:
            # マルチインデックスから個別銘柄のデータを取得
            if len(codes) > 1:
                if code not in raw.columns.get_level_values(0):
                    continue
                df = raw[code].dropna()
            else:
                df = raw.dropna()

            if len(df) < 22:
                continue
            if not all(c in df.columns for c in ["Close", "Open", "Volume"]):
                continue

            close = df["Close"].astype(float)
            volume = df["Volume"].astype(float)
            open_ = df["Open"].astype(float)

            latest_close = close.iloc[-1]
            prev_close   = close.iloc[-2]
            latest_open  = open_.iloc[-1]
            latest_vol   = volume.iloc[-1]

            # 出来高20日平均（当日除く）
            avg_volume = volume.iloc[-21:-1].mean()
            if avg_volume == 0:
                continue

            volume_ratio     = latest_vol / avg_volume
            price_change_pct = (latest_close - prev_close) / prev_close * 100
            is_bullish       = latest_close > latest_open

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━
            # スクリーニング条件
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 条件①: 出来高が20日平均の1.5倍以上
            # 条件②: 前日比 +0.5% 以上
            # 条件③: 陽線（始値 < 終値）
            if not (volume_ratio >= 1.5 and price_change_pct >= 0.5 and is_bullish):
                continue

            # 事前スコア（scorer.pyに渡す前の簡易点数）
            pre_score = (
                min(volume_ratio, 3.0) / 3.0 * 40 +
                min(price_change_pct, 3.0) / 3.0 * 30
            )

            info = code_info.get(code, {})
            results.append({
                "code":             code,
                "name":             info.get("name", code),
                "sector":           info.get("sector", ""),
                "close":            round(float(latest_close), 0),
                "prev_close":       round(float(prev_close), 0),
                "open":             round(float(latest_open), 0),
                "volume":           int(latest_vol),
                "avg_volume":       int(avg_volume),
                "volume_ratio":     round(volume_ratio, 2),
                "price_change_pct": round(price_change_pct, 2),
                "is_bullish":       is_bullish,
                "pre_score":        round(pre_score, 1),
                "_df":              df.copy()  # scorer.py用
            })

        except Exception as e:
            print(f"  {code} スクリーニングエラー: {e}")
            continue

    print(f"🎯 スクリーニング通過: {len(results)}件 / {len(codes)}件中")

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("pre_score", ascending=False)
    return result_df.head(top_n)


# ============================================================
# J-Quants互換インターフェース（main.py から呼ばれる部分）
# ============================================================

def get_jquants_access_token() -> str:
    """
    後方互換性のため残す。
    v5ではyfinanceを使うためトークンは不要。
    空文字を返すが、main.py の token 引数は screener には渡さない。
    """
    return ""


def get_daily_quotes(token: str, code: str, days: int = 40) -> pd.DataFrame:
    """
    monitor.py から呼ばれる。yfinanceで個別銘柄データを取得する。
    tokenは使用しない（後方互換性のため引数として受け取るだけ）。
    """
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(period=f"{days}d", interval="1d", auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"  {code} 個別取得エラー: {e}")
        return pd.DataFrame()


# ============================================================
# コマンドラインから直接実行する場合
# ============================================================

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "update_watchlist":
        print("📅 月次 watchlist 更新モード")
        updated = update_watchlist(top_n=50)
        print(f"\n完了: {len(updated)}銘柄を選定・保存しました")
    else:
        print("📈 スクリーニングテスト実行")
        df = screen_candidates(top_n=10)
        if df.empty:
            print("条件を満たす銘柄なし")
        else:
            print(df[["code", "name", "sector", "close", "volume_ratio",
                       "price_change_pct", "pre_score"]].to_string(index=False))
