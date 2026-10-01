"""会津若松市ごみカレンダーの取得と Web Push 通知。

使い方:
  python scripts/gomi.py districts          # 地区一覧を public/districts.json に保存
  python scripts/gomi.py fetch              # 地区の直近6日分を public/schedule.json に保存
  python scripts/gomi.py notify             # 明日がごみの日なら Push 通知を送る
  python scripts/gomi.py notify --test      # 内容に関係なくテスト通知を送る
  python scripts/gomi.py notify --dry-run   # 送らずに通知内容だけ表示

  収集日のみ (d=0) で取得するので、約2週間先までの予定が取れる。
  燃やせるごみ以外 (資源物・燃やせないごみ等) は NOTICE_DAYS_AHEAD 日前にも予告する。

環境変数:
  DISTRICT_CODE      地区コード (districts.json の code)
  PUSH_SUBSCRIPTIONS 購読情報 JSON (1件のオブジェクト、または配列)
  VAPID_PRIVATE_KEY  VAPID 秘密鍵 (base64url)
  VAPID_SUBJECT      mailto:you@example.com など
  NOTICE_DAYS_AHEAD  特殊ごみを何日前に予告するか (既定 7)
  TODAY              今日の日付を上書き (テスト用, 例 2026-10-06)
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://www.city.aizuwakamatsu.fukushima.jp/index_php/gomical/index_i.php?typ=p"
PUBLIC = Path(__file__).resolve().parent.parent / "public"
JST = dt.timezone(dt.timedelta(hours=9))
REGULAR = "燃やせるごみ"  # 予告しない、いつものごみ
WEEK = "月火水木金土日"


def today_jst():
    if os.environ.get("TODAY"):
        return dt.date.fromisoformat(os.environ["TODAY"])
    return dt.datetime.now(JST).date()


def label(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.month}/{d.day}({WEEK[d.weekday()]})"


def http(data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(URL, data=body, headers={"User-Agent": "aizu-gomi-notifier"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def list_districts():
    page = http()
    i = page.index('name="m"')
    select = page[i:page.index("</select>", i)]
    return [{"code": c, "name": html.unescape(n).strip()}
            for c, n in re.findall(r'<option value="(\d+)"[^>]*>([^<\r\n]+)', select)]


def fetch_schedule(code):
    page = http({"m": code, "d": "0"})  # d=0: ごみの日のみ表示
    name = re.search(r'<h2 class="title3">([^<]+)</h2>\s*<ul>\s*<li class="tri', page)
    items = re.findall(r"<h3>(\d{2})/(\d{2})\([^)]*\)</h3>([^<]*)</li>", page)
    if not items:
        raise RuntimeError("収集日を取得できませんでした (ページ構成が変わった可能性があります)")
    today = today_jst()
    days = []
    for mm, dd, kind in items:
        d = dt.date(today.year, int(mm), int(dd))
        if d < today - dt.timedelta(days=180):  # 年をまたぐ場合 (12月→1月)
            d = d.replace(year=today.year + 1)
        kind = html.unescape(kind).strip()
        if kind in ("", "なし"):
            continue
        days.append({"date": d.isoformat(), "kinds": kind.split("・")})
    return {
        "district": {"code": code, "name": html.unescape(name.group(1)).strip() if name else code},
        "fetchedAt": dt.datetime.now(JST).isoformat(timespec="seconds"),
        "days": days,
    }


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path}")


def send_push(title, body):
    from pywebpush import webpush, WebPushException

    for name in ("PUSH_SUBSCRIPTIONS", "VAPID_PRIVATE_KEY"):
        if not os.environ.get(name, "").strip():
            sys.exit(f"Secret {name} が空です。Settings → Secrets and variables → Actions の"
                     " Repository secrets に登録されているか確認してください")
    subject = os.environ.get("VAPID_SUBJECT", "").strip()
    if not subject.startswith(("mailto:", "https:")):
        sys.exit(f"Variable VAPID_SUBJECT が不正です ({subject!r})。Settings → Secrets and variables"
                 " → Actions の Variables に mailto:自分のメールアドレス を登録してください")
    subs = json.loads(os.environ["PUSH_SUBSCRIPTIONS"])
    if isinstance(subs, dict):
        subs = [subs]
    payload = json.dumps({"title": title, "body": body}, ensure_ascii=False)
    failed = 0
    for sub in subs:
        try:
            webpush(sub, payload,
                    vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                    vapid_claims={"sub": subject},
                    ttl=6 * 3600)
            print("sent:", sub["endpoint"][:60], "...")
        except WebPushException as e:
            failed += 1
            print("push failed:", e, file=sys.stderr)
    if failed == len(subs):
        sys.exit(1)


def special(kinds):
    return [k for k in kinds if k != REGULAR]


def build_message(schedule, today):
    """(title, body) を返す。通知不要なら None。"""
    by_date = {d["date"]: d["kinds"] for d in schedule["days"]}
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    ahead_n = int(os.environ.get("NOTICE_DAYS_AHEAD", "7"))
    ahead = (today + dt.timedelta(days=ahead_n)).isoformat()

    if schedule["days"][-1]["date"] < ahead:
        print(f"警告: 取得範囲が {ahead} まで届いていません", file=sys.stderr)

    lines = []
    title = None
    if tomorrow in by_date:
        title = "🗑️ 明日はごみの日"
        lines.append(f"明日 {label(tomorrow)}: " + "・".join(by_date[tomorrow]))
    sp = special(by_date.get(ahead, []))
    if sp and ahead != tomorrow:
        title = title or f"📅 {label(ahead)} は資源物などの日"
        lines.append(f"{ahead_n}日後 {label(ahead)}: " + "・".join(sp))
    if not lines:
        return None
    return title, "\n".join(lines) + f"\n({schedule['district']['name']})"


def notify(schedule, test=False, dry_run=False):
    msg = build_message(schedule, today_jst())
    if msg is None:
        if not test:
            print("明日の収集も予告もなし。通知しません")
            return
        msg = ("🔔 テスト通知", f"明日の収集はありません\n({schedule['district']['name']})")
    elif test:
        msg = ("🔔 テスト通知", msg[1])
    print(f"{msg[0]}\n{msg[1]}")
    if not dry_run:
        send_push(*msg)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "districts":
        write_json(PUBLIC / "districts.json", list_districts())
        return
    schedule = fetch_schedule(os.environ.get("DISTRICT_CODE", "11300"))
    if cmd == "fetch":
        write_json(PUBLIC / "schedule.json", schedule)
    elif cmd == "notify":
        write_json(PUBLIC / "schedule.json", schedule)
        notify(schedule, test="--test" in sys.argv, dry_run="--dry-run" in sys.argv)
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
