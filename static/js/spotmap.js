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
  window.__mikkeMap = { map, markers };
})();
