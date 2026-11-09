/* スポット地図: Protomaps (PMTiles) をローカル配信し、Leaflet + protomaps-leaflet で描画する */
(() => {
  "use strict";
  const el = document.getElementById("spot-map");
  if (!el || !window.L || !window.protomapsL) return;

  const cfg = JSON.parse(document.getElementById("map-config").textContent);
  const spots = JSON.parse(document.getElementById("spot-data").textContent);
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const bounds = L.latLngBounds(cfg.bounds);

  const map = L.map(el, {
    center: cfg.center,
    zoom: cfg.zoom,
    minZoom: 13,
    maxZoom: 18,
    maxBounds: bounds.pad(0.15),
    maxBoundsViscosity: 0.8,
  });
  map.attributionControl.setPrefix(false);

  protomapsL.leafletLayer({
    url: el.dataset.tiles,
    flavor: dark ? "dark" : "light",
    lang: "ja",
    maxDataZoom: cfg.max_data_zoom,
    attribution: '© <a href="https://openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors / Protomaps',
  }).addTo(map);

  // ポップアップは DOM で組み立てる (innerHTML を使わない = XSS 対策)
  function popup(s) {
    const box = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = s.name;
    box.appendChild(title);
    if (s.area) {
      const area = document.createElement("div");
      area.textContent = s.area;
      box.appendChild(area);
    }
    const stat = document.createElement("div");
    stat.textContent = `訪問 ${s.visit_days} 日 ・ シンボル ${s.found}/${s.symbols} みっけ済み`;
    box.appendChild(stat);
    const link = document.createElement("a");
    link.href = `#spot-${s.id}`;
    link.textContent = "ヒントを見る";
    link.addEventListener("click", () => {
      const card = document.getElementById(`spot-${s.id}`);
      if (card) setTimeout(() => card.focus(), 0);
    });
    box.appendChild(link);
    return box;
  }

  const markers = spots.map((s) =>
    L.marker([s.lat, s.lng], { title: s.name, alt: s.name, keyboard: true }).bindPopup(popup(s)).addTo(map));
  const inArea = spots.filter((s) => bounds.contains([s.lat, s.lng]));
  if (inArea.length > 1) map.fitBounds(L.latLngBounds(inArea.map((s) => [s.lat, s.lng])).pad(0.3), { maxZoom: 16 });

  // 現在地 (端末内で表示するだけでサーバーには送らない)
  const LocateControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd() {
      const btn = L.DomUtil.create("button", "map-locate");
      btn.type = "button";
      btn.textContent = "現在地";
      btn.setAttribute("aria-label", "現在地を表示");
      L.DomEvent.disableClickPropagation(btn);
      let me = null;
      btn.addEventListener("click", () => {
        if (!navigator.geolocation) return;
        navigator.geolocation.getCurrentPosition((pos) => {
          const ll = [pos.coords.latitude, pos.coords.longitude];
          if (me) me.remove();
          me = L.circleMarker(ll, { radius: 8, color: "#1a5fd0", fillColor: "#1a5fd0", fillOpacity: 0.6 }).addTo(map);
          if (bounds.contains(ll)) map.setView(ll, Math.max(map.getZoom(), 16));
          else me.bindPopup("現在地は地図データの範囲外です(京橋付近のみ収録)").openPopup();
        }, () => { /* 拒否時は何もしない */ }, { enableHighAccuracy: true, timeout: 10000 });
      });
      return btn;
    },
  });
  map.addControl(new LocateControl());

  // ---------------------------------------------------------------- 近くのシンボル
  // 現在地の周囲 (サイト設定の距離) にあるシンボルを地図に出し、タップでここで手に入るコーデを見せる。
  // シークレットシンボルは、あえて「？」の画像だけを出す。
  const btnNearby = document.getElementById("btn-nearby");
  const statusEl = document.getElementById("nearby-status");
  const listEl = document.getElementById("nearby-list");
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const nearbyLayer = L.layerGroup().addTo(map);
  const fmtDist = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`);

  function setStatus(msg, state) {
    statusEl.hidden = false;
    statusEl.textContent = msg;
    statusEl.className = `gps-gate${state ? ` is-${state}` : ""}`;
  }

  function mk(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function symbolPopup(s) {
    const box = mk("div", "coord-popup");
    box.appendChild(mk("h3", null, s.secret ? "？？？(シークレット)" : s.name));
    box.appendChild(mk("p", "muted", `${s.spot} ・ ここから約 ${fmtDist(s.distance_m)}`));
    if (s.secret) {
      const img = mk("img", "secret-img");
      img.src = el.dataset.secretImg;
      img.alt = "シークレット: 何が手に入るかは見つけてからのお楽しみ";
      box.appendChild(img);
      box.appendChild(mk("p", "muted", "何が手に入るかは、見つけてからのお楽しみ!"));
      return box;
    }
    box.appendChild(mk("p", null, "ここで獲得可能なコーデ"));
    if (!s.items.length) {
      box.appendChild(mk("p", "muted", "コーデはありません(クーポンなどが出ます)"));
      return box;
    }
    const ul = mk("ul", "coord-grid");
    for (const it of s.items) {
      const li = mk("li", it.now ? "" : "not-now");
      const img = mk("img");
      img.src = it.image;
      img.alt = it.name;
      img.loading = "lazy";
      li.appendChild(img);
      li.appendChild(mk("span", null, `${it.name} ${"★".repeat(it.rarity)}`));
      const cond = it.conditions.length ? it.conditions.join("・") : "いつでも";
      li.appendChild(mk("span", "coord-cond", it.now ? cond : `${cond}(今は出ない)`));
      ul.appendChild(li);
    }
    box.appendChild(ul);
    return box;
  }

  function render(data, me) {
    nearbyLayer.clearLayers();
    listEl.replaceChildren();
    L.circle(me, { radius: data.radius_m, color: "#1A5FD0", weight: 2, fillOpacity: 0.06 }).addTo(nearbyLayer);
    L.marker(me, { icon: L.divIcon({ className: "", html: '<div class="me-marker"></div>', iconSize: [18, 18] }),
      title: "現在地", alt: "現在地", keyboard: false }).addTo(nearbyLayer);
    for (const s of data.nearby) {
      const icon = L.divIcon({ className: "", iconSize: [34, 34],
        html: `<div class="nearby-marker${s.secret ? " is-secret" : ""}">${s.secret ? "?" : "★"}</div>` });
      const m = L.marker([s.lat, s.lng], { icon, title: s.secret ? "シークレットシンボル" : s.name, alt: s.name, keyboard: true })
        // コーデが多いときは地図からはみ出さないよう、ポップアップ内をスクロールさせる
        .bindPopup(symbolPopup(s), { maxWidth: 280, maxHeight: Math.max(200, el.clientHeight - 90), autoPanPadding: [12, 12] })
        .addTo(nearbyLayer);
      // 一覧からも開ける (地図を操作しにくい人向け)
      const li = mk("li");
      const b = mk("button", "btn btn-ghost btn-small", `${s.secret ? "？？？" : s.name}(${s.spot}・約 ${fmtDist(s.distance_m)})`);
      b.type = "button";
      b.addEventListener("click", () => { map.setView([s.lat, s.lng], Math.max(map.getZoom(), 17)); m.openPopup(); });
      li.appendChild(b);
      listEl.appendChild(li);
    }
    listEl.hidden = !data.nearby.length;
    const pts = [me, ...data.nearby.map((s) => [s.lat, s.lng])];
    if (bounds.contains(me)) map.fitBounds(L.latLngBounds(pts).pad(0.4), { maxZoom: 18 });
  }

  async function findNearby() {
    if (!navigator.geolocation) {
      setStatus("この端末では位置情報を使えません。", "none");
      return;
    }
    btnNearby.disabled = true;
    setStatus("現在地を確認しています…", "");
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const me = [pos.coords.latitude, pos.coords.longitude];
      try {
        const res = await fetch(el.dataset.nearbyUrl, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({ lat: me[0], lng: me[1] }),
        });
        const data = await res.json();
        if (!res.ok) {
          setStatus(data.message || "近くのシンボルを調べられませんでした。", "none");
          return;
        }
        render(data, me);
        if (data.has_nearby) {
          setStatus(`周囲 ${data.radius_m}m にシンボルが ${data.nearby.length} 件あります。★をタップすると、ここで手に入るコーデが見られます。`, "ok");
        } else {
          const hint = data.nearest ? ` いちばん近いのは「${data.nearest.spot}」(約 ${fmtDist(data.nearest.distance_m)})です。` : "";
          setStatus(`ここにはなさそう・・・ (周囲 ${data.radius_m}m にシンボルが見つかりません)${hint}`, "none");
        }
      } catch (_) {
        setStatus("通信できませんでした。もう一度お試しください。", "none");
      } finally {
        btnNearby.disabled = false;
      }
    }, () => {
      btnNearby.disabled = false;
      setStatus("位置情報を取得できませんでした。ブラウザの設定で位置情報の利用を許可してください。", "none");
    }, { enableHighAccuracy: true, timeout: 10000 });
  }
  if (btnNearby) btnNearby.addEventListener("click", findNearby);

  window.__mikkeMap = { map, markers };
})();
