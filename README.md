# ごみの日通知 (会津若松市)

会津若松市の[ごみカレンダー](https://www.city.aizuwakamatsu.fukushima.jp/index_php/gomical/index_i.php)から自分の地区の収集日を取得し、前日の夜にスマホへ Web Push で通知する PWA。

燃やせるごみ以外 (資源物・燃やせないごみ等) の日は、1週間前にも予告通知します。

サーバー不要で、GitHub Actions と GitHub Pages だけで動きます。

```
GitHub Actions (毎日 19:30 JST)
  ├─ 市のごみカレンダーに地区コードを POST → 直近の収集日6回分 (約2週間) を取得 (祝日や年末年始の変更も反映済み)
  ├─ 明日がごみの日、または7日後が資源物等の日なら pywebpush で Push 通知
  └─ public/ を GitHub Pages にデプロイ (schedule.json 付き)
スマホ (PWA)
  └─ 直近の予定を表示 / Push 購読
```

## セットアップ

1. **リポジトリを作って push**: GitHub Pages を無料で使うには public リポジトリにします。購読情報や秘密鍵は Secrets に入れるので公開されません。
2. **Pages を有効化**: Settings → Pages → Source を「GitHub Actions」にします。
3. **VAPID 鍵を生成**:
   ```
   pip install -r requirements.txt
   python scripts/gen_vapid.py
   ```
4. **Settings → Secrets and variables → Actions** に以下を登録します。

   | 種類 | 名前 | 値 |
   |---|---|---|
   | Variable | `DISTRICT_CODE` | 地区コード (アプリの「地区コードを調べる」か `public/districts.json` で確認) |
   | Variable | `VAPID_PUBLIC_KEY` | 3 で出力された公開鍵 |
   | Variable | `VAPID_SUBJECT` | `mailto:自分のメールアドレス` |
   | Variable (任意) | `NOTICE_DAYS_AHEAD` | 資源物等を何日前に予告するか (既定 7、最大 10 程度まで)  |
   | Secret | `VAPID_PRIVATE_KEY` | 3 で出力された秘密鍵 |

5. **Actions → ごみの日通知 → Run workflow** で一度デプロイします。
6. **スマホで Pages の URL を開き**、iPhone の場合は共有 → 「ホーム画面に追加」をして、追加したアイコンから開きます (iOS 16.4 以降)。
7. **「通知を有効にする」** を押し、表示された JSON を Secret `PUSH_SUBSCRIPTIONS` に登録します。家族の端末も通知したい場合は `[{...}, {...}]` の配列にします。
8. **Run workflow で「テスト通知を送る」にチェック**して実行し、通知が届けば完了です。

## メモ

- GitHub Actions の cron は混雑時に数分〜数十分遅れることがあるため、19:30 に設定しています。
- GitHub は 60 日間リポジトリに動きがないと定期実行を自動停止しますが、`keepalive` ジョブが毎回ワークフローを再有効化してこれを防ぎます (コミットは増えません)。万一停止した場合は GitHub から事前に警告メールが届くので、Actions 画面から有効化してください。
- 市のページ構成が変わって取得に失敗するとワークフローが失敗し、GitHub からメールが届きます。
- 通知内容を送らずに確認: `TODAY=2026-10-06 python scripts/gomi.py notify --dry-run` (TODAY で日付を仮定できます)
- ローカルで取得だけ試す場合は `DISTRICT_CODE=11300 python scripts/gomi.py fetch` を実行します。
