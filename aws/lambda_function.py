"""AWS Lambda から scripts/gomi.py を動かすための入口 (ハンドラ)。

GitHub Actions 版は環境変数とローカルの public/ を使うが、Lambda 版は
  - 設定と秘密 → Parameter Store (/aizu-gomi/...) から読む
  - schedule.json → /tmp に書いてから S3 にアップロードする
という違いだけをここで吸収し、gomi.py 本体はそのまま使う。

テストイベントの例:
  {"command": "fetch"}                      予定を取得して S3 に保存するだけ
  {"command": "notify", "dry_run": true}    通知文を表示するだけで送らない
  {"command": "notify", "test": true}       内容に関係なくテスト通知を送る
  {"command": "notify"}                     本番 (EventBridge から呼ぶ形)

環境変数 (Lambda の「設定」→「環境変数」で登録):
  BUCKET      schedule.json を置く S3 バケット名
  SSM_PREFIX  Parameter Store の階層 (既定 /aizu-gomi)
"""
import os
from pathlib import Path

# boto3 は AWS を操作するためのライブラリ。Lambda の Python ランタイムに最初から入っている
import boto3

import gomi

# Lambda で書き込めるのは /tmp だけ (コードが置かれる場所は読み取り専用)
gomi.PUBLIC = Path("/tmp")

# Parameter Store の名前 → gomi.py が読む環境変数名
PARAMS = {
    "district-code": "DISTRICT_CODE",
    "vapid-private-key": "VAPID_PRIVATE_KEY",
    "vapid-subject": "VAPID_SUBJECT",
    "push-subscriptions": "PUSH_SUBSCRIPTIONS",
}

# クライアントはハンドラの外で作る。ウォームスタートのときに使い回されて速くなる
ssm = boto3.client("ssm")
s3 = boto3.client("s3")


def load_params():
    """/aizu-gomi/ の下のパラメータをまとめて読み、環境変数に入れる。"""
    prefix = os.environ.get("SSM_PREFIX", "/aizu-gomi")
    # WithDecryption=True: SecureString を復号して受け取る
    res = ssm.get_parameters_by_path(Path=prefix, WithDecryption=True)
    for p in res["Parameters"]:
        key = p["Name"].rsplit("/", 1)[-1]  # "/aizu-gomi/district-code" → "district-code"
        if key in PARAMS:
            os.environ[PARAMS[key]] = p["Value"]


def lambda_handler(event, context):
    command = event.get("command", "notify")
    if command not in ("fetch", "notify"):
        raise ValueError(f"unknown command: {command}")
    load_params()

    schedule = gomi.fetch_schedule(os.environ["DISTRICT_CODE"])
    path = gomi.PUBLIC / "schedule.json"
    gomi.write_json(path, schedule)
    # CacheControl: CloudFront やブラウザに「5 分だけ使い回してよい」と伝える (毎日更新されるファイルなので)
    s3.upload_file(str(path), os.environ["BUCKET"], "schedule.json",
                   ExtraArgs={"ContentType": "application/json", "CacheControl": "max-age=300"})
    print("uploaded schedule.json")

    if command == "notify":
        gomi.notify(schedule, test=event.get("test", False), dry_run=event.get("dry_run", False))
    return {"command": command, "days": len(schedule["days"])}
