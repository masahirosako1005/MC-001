/* スポット編集: 地図をクリックして位置を選ぶ。判定半径を円で表示。「無期限」なら有効期限の入力を隠す */
(() => {
  "use strict";
  const noExpiry = document.getElementById("id_no_expiry");
  const expiresField = document.getElementById("expires-field");
  const syncExpiry = () => { if (noExpiry && expiresField) expiresField.hidden = noExpiry.checked; };
  if (noExpiry) noExpiry.addEventListener("change", syncExpiry);
  syncExpiry();

  const el = document.getElementById("picker-map");
  if (!el || !window.L || !window.protomapsL) return;
  const cfg = JSON.parse(document.getElementById("map-config").textContent);
  const lat = document.getElementById("id_latitude");
  const lng = document.getElementById("id_longitude");
  const radius = document.getElementById("id_radius_m");

  const map = L.map(el, { center: cfg.center, zoom: cfg.zoom, minZoom: 12, maxZoom: 18 });
  map.attributionControl.setPrefix(false);
  protomapsL.leafletLayer({
    url: el.dataset.tiles, flavor: "light", lang: "ja", maxDataZoom: cfg.max_data_zoom,
    attribution: '© <a href="https://openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors / Protomaps',
  }).addTo(map);

  let marker = null;
  let circle = null;
  function place(ll, pan) {
    if (!marker) {
      marker = L.marker(ll, { draggable: true, keyboard: true, title: "スポットの位置" }).addTo(map);
      marker.on("dragend", () => { const p = marker.getLatLng(); write(p); place(p, false); });
      circle = L.circle(ll, { radius: +radius.value || 300, color: "#D94F00", weight: 2, fillOpacity: 0.08 }).addTo(map);
    }
    marker.setLatLng(ll);
    circle.setLatLng(ll);
    circle.setRadius(+radius.value || 300);
    if (pan) map.panTo(ll);
  }
  function write(p) {
    lat.value = p.lat.toFixed(6);
    lng.value = p.lng.toFixed(6);
  }
  map.on("click", (e) => { write(e.latlng); place(e.latlng, false); });
  [lat, lng, radius].forEach((input) => input.addEventListener("change", () => {
    const a = parseFloat(lat.value);
    const b = parseFloat(lng.value);
    if (Number.isFinite(a) && Number.isFinite(b)) place([a, b], true);
  }));
  const a0 = parseFloat(lat.value);
  const b0 = parseFloat(lng.value);
  if (Number.isFinite(a0) && Number.isFinite(b0)) place([a0, b0], true);
})();
