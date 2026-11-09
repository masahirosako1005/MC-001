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
    return box;
  }

  const markers = spots.map((s) =>
    L.marker([s.lat, s.lng], { title: s.name, alt: s.name, keyboard: true }).bindPopup(popup(s)).addTo(map));
  const inArea = spots.filter((s) => bounds.contains([s.lat, s.lng]));
  if (inArea.length > 1) map.fitBounds(L.latLngBounds(inArea.map((s) => [s.lat, s.lng])).pad(0.3), { maxZoom: 16 });

  // 「現在地」: ①現在地の取得 → ②近くのシンボル検索 を順番に行う (nearby.js)。
  // 「近くのシンボルを探す」ボタンと同じ動作で、結果は下の mikke:nearby で地図に描く。
  let locateBtn = null;
  const LocateControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd() {
      const btn = L.DomUtil.create("button", "map-locate");
      btn.type = "button";
      btn.textContent = "現在地";
      btn.setAttribute("aria-label", "現在地を取得して、近くのシンボルを探す");
      L.DomEvent.disableClickPropagation(btn);
      btn.addEventListener("click", () => { if (window.MikkeNearby) window.MikkeNearby.search(); });
      locateBtn = btn;
      return btn;
    },
  });
  map.addControl(new LocateControl());

  // ---------------------------------------------------------------- 近くのシンボル
  // 現在地の周囲 (サイト設定の距離) にあるシンボルを地図に出し、タップでここで手に入るコーデを見せる。
  // シークレットシンボルは、あえて「？」の画像だけを出す。
  const listEl = document.getElementById("nearby-list");
  const nearbyLayer = L.layerGroup().addTo(map);
  const fmtDist = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`);

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

  function drawMe(me, radiusM) {
    L.circle(me, { radius: radiusM, color: "#1A5FD0", weight: 2, fillOpacity: 0.06 }).addTo(nearbyLayer);
    const meMarker = L.marker(me, { icon: L.divIcon({ className: "", html: '<div class="me-marker"></div>', iconSize: [18, 18] }),
      title: "現在地", alt: "現在地", keyboard: false }).addTo(nearbyLayer);
    if (!bounds.contains(me)) meMarker.bindPopup("現在地は地図データの範囲外です(京橋付近のみ収録)").openPopup();
  }

  function render(data, me) {
    nearbyLayer.clearLayers();
    listEl.replaceChildren();
    drawMe(me, data.radius_m);
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
    if (!bounds.contains(me)) return;
    if (data.nearby.length) {
      map.fitBounds(L.latLngBounds([me, ...data.nearby.map((s) => [s.lat, s.lng])]).pad(0.4), { maxZoom: 18 });
    } else {
      map.setView(me, Math.max(map.getZoom(), 16));
    }
  }

  document.addEventListener("mikke:nearby-start", () => { if (locateBtn) locateBtn.disabled = true; });
  document.addEventListener("mikke:nearby", (ev) => {
    if (locateBtn) locateBtn.disabled = false;
    const r = ev.detail;
    if (r.ok) {
      render(r.data, r.me);
    } else if (r.me) {
      nearbyLayer.clearLayers();
      listEl.hidden = true;
      drawMe(r.me, Number(document.getElementById("mikke-find").dataset.radius) || 100);
    }
  });
  // カメラから地図にもどったとき、隠れていた間の大きさの変化を反映する
  document.addEventListener("mikke:find-shown", () => map.invalidateSize());

  // 「これをみっけに行く」: ほかの人のコーデを手に入れたスポットを、目立つ印で地図に出す
  const focusLayer = L.layerGroup().addTo(map);
  document.addEventListener("mikke:focus-spot", (ev) => {
    const s = ev.detail;
    if (typeof s.lat !== "number" || typeof s.lng !== "number") return;
    focusLayer.clearLayers();
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    map.invalidateSize();
    map.setView([s.lat, s.lng], Math.max(map.getZoom(), 17));
    const box = mk("div", "coord-popup focus-popup");
    box.appendChild(mk("p", "focus-popup-lead", "これをみっけに行く"));
    box.appendChild(mk("h3", null, s.name));
    box.appendChild(mk("p", null, `ここで「${s.item}」をみっけしよう!`));
    box.appendChild(mk("p", "muted", bounds.contains([s.lat, s.lng])
      ? "近くまで行ったら「近くのシンボルを探す」を押してね。季節や時間帯によっては出ないこともあります。"
      : "このスポットは地図データの範囲外です(京橋付近のみ収録)。"));
    const icon = L.divIcon({ className: "", iconSize: [44, 44], html: '<div class="focus-marker" aria-hidden="true">★</div>' });
    L.marker([s.lat, s.lng], { icon, title: `${s.name}(みっけに行く)`, alt: s.name, keyboard: true, zIndexOffset: 1000 })
      .bindPopup(box, { maxWidth: 260, autoPanPaddingTopLeft: [12, 56], autoPanPaddingBottomRight: [12, 12] })
      .addTo(focusLayer).openPopup();
  });

  window.__mikkeMap = { map, markers };
})();
