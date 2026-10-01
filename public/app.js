const $ = (id) => document.getElementById(id);
const WEEK = ["日", "月", "火", "水", "木", "金", "土"];

function todayJst() {
  return new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
}

function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function label(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}(${WEEK[d.getUTCDay()]})`;
}

function tagClass(kind) {
  if (kind.includes("燃やせる")) return "burn";
  if (/びん|かん|缶|ペット|プラ|古紙|古着|古布/.test(kind)) return "res";
  return "";
}

const special = (kinds) => kinds.filter((k) => k !== "燃やせるごみ");

function daysBetween(a, b) {
  return Math.round((new Date(b + "T00:00:00Z") - new Date(a + "T00:00:00Z")) / 86400e3);
}

function tags(kinds) {
  const wrap = document.createElement("span");
  wrap.className = "tags";
  for (const k of kinds) {
    const span = document.createElement("span");
    span.className = `tag ${tagClass(k)}`;
    span.textContent = k;
    wrap.append(span);
  }
  return wrap;
}

async function loadSchedule() {
  const res = await fetch("schedule.json", { cache: "no-cache" });
  const s = await res.json();
  $("district").textContent = s.district.name;
  $("fetched").textContent = `市のごみカレンダーより取得: ${s.fetchedAt.replace("T", " ").slice(0, 16)}`;

  const today = todayJst();
  const tomorrow = addDays(today, 1);
  const days = s.days.filter((d) => d.date >= today);

  const t = days.find((d) => d.date === tomorrow);
  $("hero").hidden = false;
  $("heroLabel").textContent = `明日 ${label(tomorrow)}`;
  $("heroKinds").textContent = t ? t.kinds.join("・") : "収集なし";
  $("hero").classList.toggle("off", !t);

  // 燃やせるごみ以外の次の収集日
  const next = days.find((d) => d.date > today && special(d.kinds).length);
  $("next").hidden = !next;
  if (next) {
    const n = daysBetween(today, next.date);
    $("nextWhen").textContent = `${n === 1 ? "明日" : `あと${n}日`}・${label(next.date)}`;
    $("nextKinds").replaceChildren(tags(special(next.kinds)));
  }

  $("days").replaceChildren(...days.map((d) => {
    const li = document.createElement("li");
    if (special(d.kinds).length) li.className = "special";
    const prefix = d.date === today ? "今日 " : d.date === tomorrow ? "明日 " : "";
    const date = document.createElement("span");
    date.className = "date";
    date.textContent = prefix + label(d.date);
    li.append(date, tags(d.kinds));
    return li;
  }));
}

async function loadDistricts() {
  const list = await (await fetch("districts.json")).json();
  for (const d of list) $("districtSelect").append(new Option(d.name, d.code));
  $("districtSelect").onchange = (e) => {
    $("codeOut").textContent = e.target.value
      ? `地区コード: ${e.target.value}`
      : "";
  };
}

function urlBase64ToUint8Array(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function subscribe() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    $("subStatus").textContent = "このブラウザは Web Push に対応していません。iPhone はホーム画面に追加してから開いてください。";
    return;
  }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") {
    $("subStatus").textContent = "通知が許可されませんでした。";
    return;
  }
  const { vapidPublicKey } = await (await fetch("config.json")).json();
  const reg = await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
    }));
  $("subJson").value = JSON.stringify(sub);
  $("subBox").hidden = false;
  $("subStatus").textContent = "この端末の購読情報を作成しました。";
}

$("subscribe").onclick = () => subscribe().catch((e) => ($("subStatus").textContent = `エラー: ${e.message}`));
$("copy").onclick = async () => {
  await navigator.clipboard.writeText($("subJson").value);
  $("copy").textContent = "コピーしました";
};

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
loadSchedule().catch(() => ($("district").textContent = "スケジュールを読み込めませんでした"));
loadDistricts();
