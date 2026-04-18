# 📈 株シグナル通知ボット v4（Discord通知版）

毎朝8時・前場10:30・後場13:30に、日本株のシグナルを **Discordに直接通知** するボットです。

- GitHub Actions上で動作 → **サーバー・VPS不要**
- Discord Webhookを使用 → **パスワード設定不要、URLを1つ登録するだけ**
- 必要なSecrets（秘密情報）は **2つだけ**（J-Quants + Discord）

> ⚠️ LINE Notifyは2025年3月31日にサービス終了しています。本ボットはDiscord Webhookを使用しています。

---

## 通知のイメージ（iPhoneのDiscordに届く）

朝8時に届く市場サマリー：
```
📈 株シグナル 2025/04/17 朝8:00
━━━━━━━━━━━━━━
市場環境 🟢 強気
スコア: 35/40点
日経225:  38,250円  +0.80%
ドル円:   153.1円   +0.30%
S&P500:   5,200     +0.50%
Nasdaq:   18,000    +0.70%

本日の注目銘柄 → 3件が条件を満たしました
```

続いて銘柄カード（見やすいカード形式）：
```
🥇 トヨタ自動車（7203）
信頼度: 82%  ████████░░

基本情報                参考価格
セクター: 輸送用機器    ▶ エントリー: 3,450円
前日終値: 3,450円       ✅ 利確目標: 3,502円 (+1.5%)
前日比: +1.2%           🛑 損切ライン: 3,426円 (-0.7%)
出来高比: 3.1倍         RR比: 2.14

判断根拠: 出来高3.1倍急増 / MACD GC / RSI58
```

---

## セットアップ手順

### ステップ1：Discordの準備をする

#### 1-1. Discordアカウントを作る（まだの場合）

```
https://discord.com
```

「登録」からメールアドレスで無料登録。

#### 1-2. iPhoneにDiscordアプリを入れる

App StoreでDiscordと検索してインストール。同じアカウントでログイン。

#### 1-3. 自分専用のサーバーを作る

Discordアプリを開く → 左端の「＋」ボタン →「自分用に作成」→「ゲームをするための個人サーバー」→ サーバー名を「株シグナル」などにする →「作成」

#### 1-4. 通知用チャンネルにWebhookを作成する

1. 作成したサーバーの「# general」チャンネルを**長押し（または右クリック）**
2. 「チャンネルの編集」をタップ
3. 「連携サービス」→「ウェブフック」→「新しいウェブフック」
4. 名前を「株ボット」などに変更（任意）
5. **「ウェブフックURLをコピー」をタップ**

> ⚠️ **このURLをメモ帳に保存してください。** 後でGitHub Secretsに登録します。

URLの形式はこのようになっています：
```
https://discord.com/api/webhooks/1234567890/AbCdEfGhIjKlMnOpQrStUv
```

---

### ステップ2：J-Quantsに登録してトークンを取得する

J-Quantsは日本取引所グループが提供する**無料の株価データAPI**です。

#### 2-1. サイトにアクセスして登録

```
https://jpx-jquants.com
```

「新規登録」→ メールアドレスとパスワードを入力 → 届いた確認メールのリンクをクリック

#### 2-2. リフレッシュトークンを取得

ログイン後、右上のアカウントアイコン →「APIトークン発行」

「リフレッシュトークン」という英数字の文字列が表示されます。**メモ帳にコピーして保存。**

---

### ステップ3：GitHubにリポジトリを作ってファイルをアップロードする

#### 3-1. GitHubアカウントを作る（まだの場合）

```
https://github.com
```

「Sign up」から無料登録。

#### 3-2. 新しいリポジトリを作る

ログイン後、右上の「＋」→「New repository」

| 項目 | 入力内容 |
|------|---------|
| Repository name | `stock-signal-bot` |
| Public / Private | Privateを推奨 |

「Create repository」をクリック。

#### 3-3. ファイルをアップロードする

ダウンロードしたZIPを解凍します。

リポジトリページに表示される「uploading an existing file」をクリック。

解凍したフォルダの**中身を全て選択してドラッグ＆ドロップ**。

> ⚠️ **`.github`フォルダも必ず含めてください。** Macでは隠しフォルダのため`Cmd+Shift+.`で表示できます。

「Commit changes」をクリック。

---

### ステップ4：GitHub Secretsに2つ登録する

SecretはGitHubの「金庫」です。パスワードなどの秘密情報をここに保管します。

**Secretsのページを開く手順：**

リポジトリページ →「Settings」タブ → 左メニュー「Secrets and variables」→「Actions」

#### 1つ目

「New repository secret」をクリック

```
Name  : JQUANTS_REFRESH_TOKEN
Secret: ステップ2でコピーしたJ-Quantsのトークン
```

「Add secret」をクリック。

#### 2つ目

再度「New repository secret」をクリック

```
Name  : DISCORD_WEBHOOK_URL
Secret: ステップ1-4でコピーしたDiscord WebhookのURL
```

「Add secret」をクリック。

登録完了後はこのように表示されます：

```
DISCORD_WEBHOOK_URL       Updated just now
JQUANTS_REFRESH_TOKEN     Updated just now
```

> ℹ️ FinnhubのAPIキーをお持ちの場合は `FINNHUB_API_KEY` も登録すると重要経済指標の警告が届きます。なくても動きます。

---

### ステップ5：動作テストをする

1. リポジトリページ上部の「**Actions**」タブをクリック
2. 左のリストから「📈 朝のシグナル通知（8:00）」をクリック
3. 右側の「**Run workflow**」ボタン →「Run workflow」をクリック
4. 1〜3分後、緑の✅が表示されれば成功
5. iPhoneのDiscordアプリを開いて通知が届いていれば完璧です

❌が表示された場合はジョブをクリックするとエラーの詳細が確認できます。

---

## 通知スケジュール

| 時刻 | 内容 | 送信条件 |
|------|------|---------|
| 毎朝 8:00 | 本日の注目銘柄（最大5件） | 毎日送信 |
| 前場 10:30 | 朝の銘柄の状況変化 | 変化があった場合のみ |
| 後場 13:30 | 変化の確認＋新規候補銘柄 | 毎日送信 |

---

## 状況変化の通知パターン

| 通知 | 条件 | 意味 |
|------|------|------|
| 📈 強化シグナル | MACD GC + RSI上昇 + 出来高増加 | 継続/追加エントリー推奨 |
| ⚠️ 弱体化シグナル | 目標価格接近 or RSI過熱 | 利確を検討 |
| 🚨 撤退シグナル | 損切りライン到達 or RSI75超 | 損切り/見送りを推奨 |
| （通知なし） | 変化なし | 前場はスキップ |

---

## 必要なSecrets一覧

| Secret名 | 必須 | 取得元 |
|----------|------|--------|
| `JQUANTS_REFRESH_TOKEN` | ✅ 必須 | jpx-jquants.com |
| `DISCORD_WEBHOOK_URL` | ✅ 必須 | Discordサーバーの設定 |
| `FINNHUB_API_KEY` | ⚠️ 任意 | finnhub.io（重要指標警告に使用） |

---

## ファイル構成

```
stock-signal-bot/
├── .github/workflows/
│   ├── morning_signal.yml      # 8:00  朝のシグナル
│   ├── midmorning_monitor.yml  # 10:30 前場レビュー
│   └── afternoon_signal.yml    # 13:30 後場シグナル
├── main.py            # メイン処理
├── market_context.py  # 日経・ドル円・NY市場取得
├── screener.py        # J-Quantsで銘柄スクリーニング
├── scorer.py          # テクニカル指標・信頼度スコア計算
├── monitor.py         # 朝の銘柄の状況変化を検知
├── notifier.py        # Discord Webhook送信
└── requirements.txt   # 必要なPythonパッケージ
```

---

## 注意事項

- このシグナルは統計的な参考情報です
- 最終的な売買判断はご自身でお願いします
- 投資は自己責任でお願いします
