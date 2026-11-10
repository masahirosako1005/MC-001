/* みっけの地図: Protomaps (PMTiles) をローカル配信し、Leaflet + protomaps-leaflet で描画する。印はシンボルだけ (スポットは出さない) */
(() => {
  "use strict";
  const el = document.getElementById("spot-map");
  if (!el || !window.L || !window.protomapsL) return;

  const cfg = JSON.parse(document.getElementById("map-config").textContent);
  // 地図に出すシンボル (公開中のスポットの、公開中のシンボル。シークレットは見つけるまで名前を伏せる)
  const spots = JSON.parse(document.getElementById("symbol-data").textContent);
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
  // ポップアップが左上のボタン (拡大・縮小・現在地) に隠れないよう、自動で地図を動かすときの余白を広げる
  L.Popup.mergeOptions({ autoPanPaddingTopLeft: L.point(96, 12), autoPanPaddingBottomRight: L.point(12, 12) });

  protomapsL.leafletLayer({
    url: el.dataset.tiles,
    flavor: dark ? "dark" : "light",
    lang: "ja",
    maxDataZoom: cfg.max_data_zoom,
    attribution: '© <a href="https://openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors / Protomaps',
  }).addTo(map);

  // 地図にはスポットではなくシンボルを出す。ポップアップは DOM で組み立てる (innerHTML を使わない = XSS 対策)
  function basePopup(s) {
    const box = mk("div", "coord-popup");
    box.appendChild(mk("h3", null, s.masked ? "？？？(シークレット)" : s.name));
    box.appendChild(mk("p", "muted", s.spot));
    if (s.masked) {
      const img = mk("img", "secret-img");
      img.src = el.dataset.secretImg;
      img.alt = "シークレット: 何が手に入るかは見つけてからのお楽しみ";
      box.appendChild(img);
    } else if (s.hint) {
      box.appendChild(mk("p", null, `ヒント: ${s.hint}`));
    }
    if (s.found) box.appendChild(mk("p", "symbol-found", s.next_at ? `みっけ済み ・ 次は ${s.next_at} から` : "みっけ済み"));
    box.appendChild(mk("p", "muted", "近くで「近くのシンボルを探す」を押すと、ここで手に入るコーデが見られます。"));
    return box;
  }

  function symbolIcon(s) {
    const cls = s.masked ? "symbol-marker is-secret" : s.found ? "symbol-marker is-found" : "symbol-marker";
    const mark = s.masked ? "?" : s.found ? "✓" : "★";
    return L.divIcon({ className: "", iconSize: [28, 28], html: `<div class="${cls}" aria-hidden="true">${mark}</div>` });
  }

  const markers = new Map(spots.map((s) => [s.id, L.marker([s.lat, s.lng], {
    icon: symbolIcon(s), keyboard: true,
    title: s.masked ? "シークレットシンボル" : `${s.name}(${s.spot})`,
    alt: s.masked ? "シークレットシンボル" : s.name,
  }).bindPopup(basePopup(s), { maxWidth: 260 })]));
  // 「近くのシンボルを探す」で詳しい印 (手に入るコーデ付き) を出したシンボルは、ふだんの印を隠して重ならないようにする
  const hiddenIds = new Set();

  // 印が密集しても読めるよう、引いた表示 (ズーム 15 以下) では近い印を数字付きの丸にまとめる (簡易クラスタリング)
  const CLUSTER_MAX_ZOOM = 15;
  const CLUSTER_PX = 40;
  const symbolLayer = L.layerGroup().addTo(map);
  function renderSymbols() {
    symbolLayer.clearLayers();
    const visible = [...markers].filter(([id]) => !hiddenIds.has(id)).map(([, m]) => m);
    if (map.getZoom() > CLUSTER_MAX_ZOOM) {
      visible.forEach((m) => symbolLayer.addLayer(m));
      return;
    }
    const groups = [];
    for (const m of visible) {
      const p = map.latLngToLayerPoint(m.getLatLng());
      const g = groups.find((x) => x.p.distanceTo(p) < CLUSTER_PX);
      if (g) g.items.push(m);
      else groups.push({ p, items: [m] });
    }
    for (const g of groups) {
      if (g.items.length === 1) {
        symbolLayer.addLayer(g.items[0]);
        continue;
      }
      const area = L.latLngBounds(g.items.map((m) => m.getLatLng()));
      const n = g.items.length;
      const icon = L.divIcon({ className: "", iconSize: [40, 40], html: `<div class="spot-cluster">${n}</div>` });
      L.marker(area.getCenter(), { icon, title: `シンボル ${n} 個(押すと拡大)`, alt: `シンボル ${n} 個`, keyboard: true })
        .on("click", () => map.fitBounds(area.pad(0.4), { maxZoom: CLUSTER_MAX_ZOOM + 2 }))
        .addTo(symbolLayer);
    }
  }
  map.on("zoomend", renderSymbols);

  const inArea = spots.filter((s) => bounds.contains([s.lat, s.lng]));
  if (inArea.length > 1) map.fitBounds(L.latLngBounds(inArea.map((s) => [s.lat, s.lng])).pad(0.3), { maxZoom: 16 });
  renderSymbols();

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
      const name = mk("span", null, `${it.name} `);
      const stars = mk("span", null, "★".repeat(it.rarity));
      stars.setAttribute("aria-hidden", "true");
      name.append(stars, mk("span", "visually-hidden", `(レア度 ${it.rarity}/5)`));
      li.appendChild(name);
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
    hiddenIds.clear();
    for (const s of data.nearby) hiddenIds.add(s.id);
    renderSymbols();
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
      hiddenIds.clear();
      renderSymbols();
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
    // 何を探せばいいか分かるよう、目印のシンボル (名前・ヒント) と、このコーデが出る条件も出す
    const sym = s.symbol && typeof s.symbol.lat === "number" ? s.symbol : null;
    const box = mk("div", "coord-popup focus-popup");
    box.appendChild(mk("p", "focus-popup-lead", "これをみっけに行く"));
    box.appendChild(mk("h3", null, s.name));
    box.appendChild(mk("p", null, `ここで「${s.item}」をみっけしよう!`));
    if (sym) {
      const dl = mk("dl", "focus-hints");
      dl.append(mk("dt", null, "目印"), mk("dd", null, `「${sym.name}」`));
      if (sym.hint) dl.append(mk("dt", null, "ヒント"), mk("dd", null, sym.hint));
      if (sym.drops_here) {
        const cond = sym.conditions.length ? sym.conditions.join("・") : "いつでも";
        dl.append(mk("dt", null, "出る条件"), mk("dd", sym.now ? null : "focus-not-now", sym.now ? cond : `${cond}(いまは出ません)`));
      }
      box.appendChild(dl);
    }
    box.appendChild(mk("p", "muted", bounds.contains([s.lat, s.lng])
      ? "近くまで行ったら「近くのシンボルを探す」を押してね。"
      : "このスポットは地図データの範囲外です(京橋付近のみ収録)。"));
    // スポットの印は出さないので、目印のシンボルの位置 (分からなければスポットのシンボル → スポット) に目立つ印を出す
    const own = spots.filter((x) => x.spot_id === s.id);
    const target = sym ? [sym.lat, sym.lng] : own.length ? [own[0].lat, own[0].lng] : [s.lat, s.lng];
    // アニメーションなしで動かす (動いている最中に開くと、ポップアップが地図からはみ出す位置のままになるため)
    if (!sym && own.length > 1) {
      map.fitBounds(L.latLngBounds(own.map((x) => [x.lat, x.lng])).pad(0.6), { maxZoom: 18, animate: false });
    } else {
      map.setView(target, Math.max(map.getZoom(), 17), { animate: false });
    }
    const icon = L.divIcon({ className: "", iconSize: [44, 44], html: '<div class="focus-marker" aria-hidden="true">★</div>' });
    L.marker(target, { icon, title: `${s.name}(みっけに行く)`, alt: s.name, keyboard: true, zIndexOffset: 1000 })
      // 狭い画面でも、左のボタンの分をあけて地図の中に収まる幅にする
      .bindPopup(box, { maxWidth: Math.max(180, Math.min(260, map.getSize().x - 96 - 12 - 40)) })
      .addTo(focusLayer).openPopup();
    // 地図が動いている途中・ページのスクロール中に開くと、Leaflet の自動調整では地図からはみ出したままになることがある。
    // 実際の表示位置を測って、はみ出した分だけ地図を動かす (開いた直後と、スクロールが落ち着いたあと)
    const keepInside = () => {
      const pop = focusLayer.getLayers()[0]?.getPopup()?.getElement();
      if (!pop || !pop.isConnected) return;
      const pr = pop.getBoundingClientRect();
      const mr = el.getBoundingClientRect();
      const pad = { top: 12, left: 96, right: 12, bottom: 12 }; // 左は拡大・縮小・現在地のボタンの分
      let dx = 0;
      let dy = 0;
      if (pr.top < mr.top + pad.top) dy = pr.top - (mr.top + pad.top);
      else if (pr.bottom > mr.bottom - pad.bottom) dy = pr.bottom - (mr.bottom - pad.bottom);
      if (pr.left < mr.left + pad.left) dx = pr.left - (mr.left + pad.left);
      else if (pr.right > mr.right - pad.right) dx = pr.right - (mr.right - pad.right);
      if (dx || dy) map.panBy([dx, dy], { animate: false });
    };
    requestAnimationFrame(keepInside);
    setTimeout(keepInside, 600);
  });

  window.__mikkeMap = { map, markers, symbolLayer };
})();
