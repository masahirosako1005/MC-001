/*
 * みっけ: 近くのシンボルさがし
 * ①現在地を取得 → ②その周囲にシンボルがあるかサーバーに問い合わせる、を必ずこの順番で行う。
 * 地図 (spotmap.js) とカメラ (camera.js) は、ここが出すイベントを受け取って表示・ボタンを切り替える。
 *   mikke:nearby-start  検索を始めた
 *   mikke:nearby        結果 { ok, data, me, error }
 * 位置情報は URL に載せず (POST 本文)、端末にも保存しない。
 */
(() => {
  "use strict";
  const root = document.getElementById("mikke-find");
  if (!root) return;

  const statusEl = document.getElementById("nearby-status");
  const btnNearby = document.getElementById("btn-nearby");
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const radius = Number(root.dataset.radius) || 100;
  const fmtDist = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`);

  let last = null; // { ok, data, me, at }
  let inflight = null;

  function setStatus(msg, state) {
    statusEl.textContent = msg;
    statusEl.className = `gps-gate${state ? ` is-${state}` : ""}`;
  }

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function getPosition() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("unsupported"));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve([pos.coords.latitude, pos.coords.longitude]),
        (err) => reject(err),
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 10000 },
      );
    });
  }

  function finish(result) {
    last = { ...result, at: Date.now() };
    emit("mikke:nearby", last);
    return last;
  }

  async function run() {
    emit("mikke:nearby-start", {});
    if (btnNearby) btnNearby.disabled = true;
    try {
      // ① 現在地の取得
      setStatus("① 現在地を取得しています…", "busy");
      let me;
      try {
        me = await getPosition();
      } catch (e) {
        const denied = e && e.code === 1;
        setStatus(denied
          ? "位置情報の利用が許可されていません。ブラウザの設定で許可してから「近くのシンボルを探す」を押してください。"
          : "現在地を取得できませんでした。電波や GPS の届く場所で「近くのシンボルを探す」を押してください。", "none");
        return finish({ ok: false, error: "location" });
      }
      // ② 周囲のシンボルを検索
      setStatus(`② 周囲 ${radius}m のシンボルを探しています…`, "busy");
      let res;
      let data = {};
      try {
        res = await fetch(root.dataset.nearbyUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({ lat: me[0], lng: me[1] }),
        });
        data = await res.json();
      } catch (_) {
        setStatus("通信できませんでした。電波のよい場所でもう一度お試しください。", "none");
        return finish({ ok: false, error: "network", me });
      }
      if (!res.ok) {
        if (res.status === 401) window.location.reload();
        setStatus(data.message || "近くのシンボルを調べられませんでした。", "none");
        return finish({ ok: false, error: "server", me });
      }
      if (data.has_nearby) {
        const s = data.nearby[0];
        const more = data.nearby.length > 1 ? ` ほか ${data.nearby.length - 1} 件` : "";
        setStatus(`近くにシンボルがあるよ!「${s.name}」まで約 ${fmtDist(s.distance_m)}${more}。カメラでみっけしよう!`, "ok");
      } else {
        const hint = data.nearest ? ` いちばん近いのは「${data.nearest.spot}」(約 ${fmtDist(data.nearest.distance_m)})です。` : "";
        setStatus(`ここにはなさそう・・・ (周囲 ${data.radius_m}m にシンボルが見つかりません)${hint}`, "none");
      }
      return finish({ ok: true, data, me });
    } finally {
      if (btnNearby) btnNearby.disabled = false;
    }
  }

  /** 現在地の取得 → シンボル検索 を順番に行う。実行中に呼ばれたら同じ結果を待つ。 */
  function search() {
    if (!inflight) inflight = run().finally(() => { inflight = null; });
    return inflight;
  }

  window.MikkeNearby = {
    search,
    /** 直近 maxAgeMs 以内の結果 (なければ null) */
    recent(maxAgeMs) {
      return last && Date.now() - last.at < maxAgeMs ? last : null;
    },
  };

  if (btnNearby) btnNearby.addEventListener("click", search);
  // 画面を開いたら、まず近くにシンボルがあるかを調べる (地図・カメラの準備ができてから)
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", search, { once: true });
  else search();
})();
