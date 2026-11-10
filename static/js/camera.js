/*
 * みっけ 疑似ARカメラ
 * - カメラ映像を canvas に描き、jsQR でみっけシンボルを検出
 * - 検出位置に光るマークを重ねて追従表示 (疑似AR)
 * - マーク(または代替ボタン)をタップすると、サーバーでごほうびを受け取る
 * 映像フレームはサーバーに送らない。送るのはシンボルの識別文字列だけ。
 */
(() => {
  "use strict";

  const root = document.getElementById("ar");
  if (!root) return;
  const $ = (id) => document.getElementById(id);

  const video = $("ar-video");
  const canvas = $("ar-canvas");
  const ctx = canvas.getContext("2d");
  const statusEl = $("ar-status");
  const btnStart = $("btn-start");
  const btnStop = $("btn-stop");
  const btnCollect = $("btn-collect");
  const collectLabel = $("btn-collect-label");

  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const scanCanvas = document.createElement("canvas");
  const scanCtx = scanCanvas.getContext("2d", { willReadFrequently: true });
  const PREFIX = "MIKKE1:";
  const LOST_FADE_MS = 1200;
  const LOST_CLEAR_MS = 2500;
  const SCAN_INTERVAL_MS = 150;
  const dateFmt = new Intl.DateTimeFormat("ja-JP", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });

  let stream = null;
  let rafId = 0;
  let lastScanAt = 0;
  let dpr = 1;
  let target = null;
  let markHit = null;
  let busy = false;
  const scanCache = new Map();
  // 画像シンボル (写真そのものがシンボル) の特徴量
  let imageRefs = [];
  let imageRefsPromise = null;
  let imageRR = 0;
  // 近距離用 640px と遠距離用 960px を交互に使う (遠くの小さなシンボルも見つけやすくする)
  const IMAGE_SCAN_EDGES = [640, 960];
  let imageTick = 0;
  const IMAGE_CANDIDATES_PER_TICK = 3;

  const setStatus = (msg) => { statusEl.textContent = msg; };

  const newKey = () => (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
        (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));

  async function post(url, body, headers = {}) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, ...headers },
      body: JSON.stringify(body),
    });
    let data = {};
    try { data = await res.json(); } catch (_) { /* 空レスポンス */ }
    return { ok: res.ok, status: res.status, data };
  }

  // ---------- 描画まわり ----------
  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(rect.width * dpr));
    const h = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  }

  function sourceSize(src) {
    if (src === video) return [video.videoWidth, video.videoHeight];
    return [src.naturalWidth || src.width, src.naturalHeight || src.height];
  }

  // カメラの映像は画面いっぱいに表示する (cover)
  function fitRect(sw, sh, cw, ch, cover) {
    const s = cover ? Math.max(cw / sw, ch / sh) : Math.min(cw / sw, ch / sh);
    return { s, dx: (cw - sw * s) / 2, dy: (ch - sh * s) / 2 };
  }

  function frame(ts) {
    rafId = requestAnimationFrame(frame);
    const src = video.readyState >= 2 ? video : null;
    if (!src) return;
    resizeCanvas();
    const [sw, sh] = sourceSize(src);
    if (!sw || !sh) return;
    const fit = fitRect(sw, sh, canvas.width, canvas.height, true);
    ctx.fillStyle = "#101820";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(src, fit.dx, fit.dy, sw * fit.s, sh * fit.s);
    if (ts - lastScanAt > (imageRefs.length ? SCAN_INTERVAL_MS + 60 : SCAN_INTERVAL_MS)) {
      lastScanAt = ts;
      if (!detect(src, sw, sh, fit, 640, "dontInvert")) {
        detectImage(src, sw, sh, fit, IMAGE_SCAN_EDGES[imageTick++ % IMAGE_SCAN_EDGES.length]);
      }
    }
    updateLost(ts);
    drawMark(ts);
  }

  function detect(src, sw, sh, fit, maxEdge, inversion) {
    if (typeof window.jsQR !== "function") return false;
    const k = Math.min(1, maxEdge / Math.max(sw, sh));
    const w = Math.round(sw * k);
    const h = Math.round(sh * k);
    scanCanvas.width = w;
    scanCanvas.height = h;
    scanCtx.drawImage(src, 0, 0, w, h);
    const img = scanCtx.getImageData(0, 0, w, h);
    const code = window.jsQR(img.data, w, h, { inversionAttempts: inversion });
    if (!code || typeof code.data !== "string" || !code.data.startsWith(PREFIX)) return false;
    const L = code.location;
    const raw = [L.topLeftCorner, L.topRightCorner, L.bottomRightCorner, L.bottomLeftCorner]
      .map((p) => ({ x: p.x / k, y: p.y / k }));
    onDetected(code.data, raw, fit);
    return true;
  }

  function ensureImageRefs() {
    if (imageRefsPromise) return imageRefsPromise;
    if (!window.MikkeImage || !root.dataset.imageSymbolsUrl) return Promise.resolve([]);
    imageRefsPromise = fetch(root.dataset.imageSymbolsUrl, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : { symbols: [] }))
      .then((d) => {
        imageRefs = (d.symbols || []).map((s) => window.MikkeImage.prepareReference(s));
        return imageRefs;
      })
      .catch(() => {
        imageRefsPromise = null; // 次の起動時に再取得
        return [];
      });
    return imageRefsPromise;
  }

  /** 画像シンボルを探す。負荷を抑えるため 1 回に数件ずつ順番に照合する */
  function detectImage(src, sw, sh, fit, maxEdge) {
    if (!imageRefs.length || !window.MikkeImage) return false;
    const k = Math.min(1, maxEdge / Math.max(sw, sh));
    const w = Math.round(sw * k);
    const h = Math.round(sh * k);
    const frameF = window.MikkeImage.frameFeatures(window.MikkeImage.rasterize(src, w, h), maxEdge > 700 ? 600 : 420);
    // 追跡中のシンボルは全角度を優先し、それ以外は数件ずつ順番に照合する
    const candidates = target && target.imageId ? imageRefs.filter((r) => r.id === target.imageId) : [];
    const n = Math.min(imageRefs.length, IMAGE_CANDIDATES_PER_TICK);
    for (let i = 0; i < n; i++) {
      const r = imageRefs[(imageRR + i) % imageRefs.length];
      if (!candidates.includes(r)) candidates.push(r);
    }
    imageRR = (imageRR + n) % imageRefs.length;
    for (const ref of candidates) {
      const m = window.MikkeImage.match(frameF, ref);
      if (!m) continue;
      const raw = m.corners.map((p) => ({ x: p.x / k, y: p.y / k }));
      onDetected(`img:${ref.id}`, raw, fit, {
        imageId: ref.id,
        patch: () => window.MikkeImage.toBase64(window.MikkeImage.patchFromGray(frameF.gray, m.H, ref.w, ref.h)),
      });
      return true;
    }
    return false;
  }

  const toDisplay = (raw, fit) => raw.map((p) => ({ x: p.x * fit.s + fit.dx, y: p.y * fit.s + fit.dy }));

  function onDetected(payload, raw, fit, extra = null) {
    const now = performance.now();
    const pts = toDisplay(raw, fit);
    if (!target || target.payload !== payload) {
      target = { payload, raw, pts, fit: fit.s, lastSeen: now, bornAt: now, state: "checking", info: null, idemKey: null,
        imageId: extra ? extra.imageId : null, patch: extra ? extra.patch() : null };
      requestScan(target);
    } else {
      // 手ぶれでマークが震えないように平滑化
      target.pts = target.pts.map((p, i) => ({ x: p.x * 0.6 + pts[i].x * 0.4, y: p.y * 0.6 + pts[i].y * 0.4 }));
      target.raw = raw;
      target.lastSeen = now;
    }
  }

  function updateLost(ts) {
    if (!target || busy) return;
    if (ts - target.lastSeen > LOST_CLEAR_MS) {
      clearTarget();
      setStatus("シンボルをさがしています…");
    }
  }

  function clearTarget() {
    target = null;
    markHit = null;
    btnCollect.hidden = true;
  }

  function drawStar(cx, cy, outer, inner, points, rot) {
    ctx.beginPath();
    for (let i = 0; i < points * 2; i++) {
      const r = i % 2 === 0 ? outer : inner;
      const a = rot + (Math.PI * i) / points - Math.PI / 2;
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    }
    ctx.closePath();
  }

  function drawMark(ts) {
    markHit = null;
    if (!target || target.state === "unknown") return;
    const p = target.pts;
    const cx = (p[0].x + p[1].x + p[2].x + p[3].x) / 4;
    const cy = (p[0].y + p[1].y + p[2].y + p[3].y) / 4;
    const edge = (Math.hypot(p[1].x - p[0].x, p[1].y - p[0].y) + Math.hypot(p[3].x - p[0].x, p[3].y - p[0].y)) / 2;
    const r = Math.max(34 * dpr, Math.min(edge * 0.42, 130 * dpr));
    const t = reduceMotion ? 0 : ts / 1000;
    const age = ts - target.lastSeen;
    const alpha = Math.max(0.25, 1 - Math.max(0, age - LOST_FADE_MS / 2) / LOST_FADE_MS);
    const y = cy - r * 0.15 + Math.sin(t * 2.4) * 6 * dpr;

    ctx.save();
    ctx.globalAlpha = alpha;
    // 検出枠
    ctx.setLineDash([10 * dpr, 8 * dpr]);
    ctx.lineDashOffset = -t * 30;
    ctx.lineWidth = 3 * dpr;
    ctx.strokeStyle = target.state === "ready" ? "rgba(255,190,60,0.9)" : "rgba(255,255,255,0.6)";
    ctx.beginPath();
    p.forEach((q, i) => (i ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y)));
    ctx.closePath();
    ctx.stroke();
    ctx.setLineDash([]);

    if (target.state === "checking") {
      ctx.lineWidth = 6 * dpr;
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.beginPath();
      ctx.arc(cx, cy, r * 0.5, t * 4, t * 4 + Math.PI * 1.3);
      ctx.stroke();
    } else if (target.state === "ready") {
      const pulse = 1 + (reduceMotion ? 0 : Math.sin(t * 4) * 0.06);
      const glow = ctx.createRadialGradient(cx, y, r * 0.1, cx, y, r * 1.3);
      glow.addColorStop(0, "rgba(255,240,170,0.95)");
      glow.addColorStop(0.5, "rgba(255,180,40,0.45)");
      glow.addColorStop(1, "rgba(255,180,40,0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(cx, y, r * 1.3, 0, Math.PI * 2);
      ctx.fill();
      drawStar(cx, y, r * 0.75 * pulse, r * 0.34 * pulse, 5, reduceMotion ? 0 : Math.sin(t) * 0.15);
      ctx.fillStyle = "#FFD84D";
      ctx.fill();
      ctx.lineWidth = 4 * dpr;
      ctx.strokeStyle = "#FFFFFF";
      ctx.stroke();
      ctx.fillStyle = "#B4570A";
      ctx.font = `700 ${Math.round(r * 0.42)}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("!", cx, y + r * 0.04);
      for (let i = 0; i < 4; i++) {
        const a = t * 1.5 + (Math.PI / 2) * i;
        drawStar(cx + Math.cos(a) * r * 1.05, y + Math.sin(a) * r * 1.05, r * 0.14, r * 0.05, 4, a);
        ctx.fillStyle = "#FFFFFF";
        ctx.fill();
      }
      // 吹き出しラベル
      const label = "タップでみっけ!";
      ctx.font = `700 ${Math.round(15 * dpr)}px sans-serif`;
      const tw = ctx.measureText(label).width + 20 * dpr;
      const ly = y - r * 1.15;
      ctx.fillStyle = "rgba(31,42,68,0.9)";
      ctx.beginPath();
      ctx.roundRect(cx - tw / 2, ly - 16 * dpr, tw, 30 * dpr, 15 * dpr);
      ctx.fill();
      ctx.fillStyle = "#FFFFFF";
      ctx.fillText(label, cx, ly);
      markHit = { x: cx, y, r: r * 1.3 };
    } else if (target.state === "cooldown") {
      ctx.fillStyle = "rgba(90,99,117,0.85)";
      ctx.beginPath();
      ctx.arc(cx, y, r * 0.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 4 * dpr;
      ctx.beginPath();
      ctx.arc(cx, y, r * 0.42, 0, Math.PI * 2);
      ctx.moveTo(cx, y);
      ctx.lineTo(cx, y - r * 0.3);
      ctx.moveTo(cx, y);
      ctx.lineTo(cx + r * 0.22, y + r * 0.08);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ---------- サーバーとのやりとり ----------
  async function requestScan(t) {
    const cached = scanCache.get(t.payload);
    if (cached && performance.now() - cached.at < 20000) {
      applyScan(t, cached.res);
      return;
    }
    setStatus("シンボルを確認しています…");
    let res;
    const body = t.imageId ? { image_symbol: t.imageId, patch: t.patch } : { payload: t.payload };
    try {
      res = await post(root.dataset.scanUrl, body);
    } catch (_) {
      setStatus("通信できませんでした。電波のよい場所でもう一度うつしてください。");
      if (target === t) clearTarget();
      return;
    }
    if (res.status === 401) { window.location.reload(); return; }
    if (res.status === 429) {
      setStatus(res.data.message || "少し時間をおいてお試しください。");
      if (target === t) clearTarget();
      return;
    }
    // 画像シンボルの照合失敗は写り具合の問題なのでキャッシュせず、少し待って撮り直す
    if (res.ok || !t.imageId) scanCache.set(t.payload, { at: performance.now(), res });
    applyScan(t, res);
  }

  function applyScan(t, res) {
    if (target !== t) return;
    if (!res.ok) {
      t.state = "unknown";
      setStatus(res.data.message || "このコードはみっけシンボルではないようです。");
      if (t.imageId) setTimeout(() => { if (target === t) clearTarget(); }, 1500);
      return;
    }
    t.info = res.data;
    t.state = res.data.status;
    t.idemKey = newKey();
    updatePanel();
  }

  function updatePanel() {
    if (!target || !target.info) return;
    const sym = target.info.symbol;
    if (target.state === "ready") {
      collectLabel.textContent = `「${sym.spot}」の${sym.name}をみっけ!`;
      btnCollect.hidden = false;
      btnCollect.disabled = false;
      setStatus(`${sym.spot}「${sym.name}」を発見!光るマークか、下のボタンをタップしてね。`);
    } else if (target.state === "cooldown") {
      btnCollect.hidden = true;
      const at = target.info.next_available_at ? dateFmt.format(new Date(target.info.next_available_at)) : "";
      setStatus(`${sym.name}はみっけ済みです。${at ? at + "ごろ、" : ""}また来てね。`);
    }
  }

  function getLocation() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) { reject(new Error("unsupported")); return; }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        reject,
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
      );
    });
  }

  async function collect() {
    if (busy || !target || target.state !== "ready" || !target.info) return;
    const t = target;
    busy = true;
    btnCollect.disabled = true;
    try {
      let location = null;
      if (t.info.requires_location) {
        setStatus("現在地を確認しています…");
        try {
          location = await getLocation();
        } catch (_) {
          setStatus("位置情報を取得できませんでした。このスポットでは現地確認が必要です。設定で位置情報の利用を許可してください。");
          return;
        }
      }
      setStatus("受け取っています…");
      let res;
      try {
        res = await post(root.dataset.collectUrl, { ticket: t.info.ticket, location }, { "Idempotency-Key": t.idemKey });
      } catch (_) {
        // 同じ Idempotency-Key で再送できるので、二重に受け取ることはない
        setStatus("通信できませんでした。電波のよい場所で、もう一度タップしてください。");
        return;
      }
      scanCache.delete(t.payload);
      if (res.ok) {
        t.state = "cooldown";
        t.info.status = "cooldown";
        btnCollect.hidden = true;
        document.dispatchEvent(new CustomEvent("mikke:reward", { detail: res.data }));
        setStatus("受け取りました!ほかのシンボルもさがしてみよう。");
      } else if (res.status === 401) {
        window.location.reload();
      } else if (res.data.error === "cooldown") {
        t.state = "cooldown";
        t.info.next_available_at = res.data.next_available_at;
        updatePanel();
      } else if (res.data.error === "invalid_ticket") {
        clearTarget();
        setStatus(res.data.message);
      } else if (res.data.error === "not_nearby") {
        // 「近くのシンボルを探す」を通っていない (時間がたった・省略した)。地図に戻って探し直してもらう
        clearTarget();
        setStatus(res.data.message);
        showCameraView(false);
        if (window.MikkeNearby) window.MikkeNearby.search().catch(() => {});
      } else {
        setStatus(res.data.message || "受け取れませんでした。もう一度お試しください。");
      }
    } finally {
      busy = false;
      btnCollect.disabled = false;
    }
  }

  // ---------- 結果の表示は reward_dialog.js / finders.js ----------
  // 「これをみっけに行く」: カメラ中なら止めて地図 (①さがす) にもどる
  document.addEventListener("mikke:go-map", () => {
    if (stream) stopCamera(true);
    else showCameraView(false);
  });

  // ---------- 近くにシンボルがあるときだけカメラを使える ----------
  // ①現在地の取得 → ②シンボル検索 は nearby.js が行い、その結果でボタンを切り替える。
  const skipEl = $("gps-skip"); // 管理者のテスト用
  const findView = $("mikke-find");
  const cameraView = $("mikke-camera");
  const PASS_MS = 3 * 60 * 1000; // 確認から 3 分以内なら、もう一度は調べない
  let nearbyOk = false;
  let searching = false;
  let lastError = null; // "location" (位置情報が取れない) / "network" / "server"
  const reasonEl = $("btn-start-reason");

  // 押せないときの理由 (ボタンの中に表示する)
  function startReason() {
    if (searching) return "近くのシンボルを探しています…";
    if (lastError === "location") return "位置情報の利用を許可すると押せます";
    if (lastError) return "通信できませんでした。「近くのシンボルを探す」をもう一度";
    return "近くにシンボルが見つかると押せます";
  }

  function setReady() {
    const ok = (nearbyOk || (skipEl && skipEl.checked)) && !searching;
    btnStart.disabled = !ok;
    if (reasonEl) {
      reasonEl.textContent = ok ? "" : startReason();
      reasonEl.hidden = ok;
    }
    // 手順の表示: いまの手順を強調し、終わった手順には ✓ を付ける
    const s1 = $("step-search");
    const s2 = $("step-camera");
    s1.classList.toggle("is-done", nearbyOk);
    s1.classList.toggle("is-current", !nearbyOk);
    s2.classList.toggle("is-current", nearbyOk);
    if (nearbyOk) { s1.removeAttribute("aria-current"); s2.setAttribute("aria-current", "step"); }
    else { s2.removeAttribute("aria-current"); s1.setAttribute("aria-current", "step"); }
  }
  document.addEventListener("mikke:nearby-start", () => { searching = true; setReady(); });
  document.addEventListener("mikke:nearby", (ev) => {
    searching = false;
    nearbyOk = !!(ev.detail.ok && ev.detail.data.has_nearby);
    lastError = ev.detail.ok ? null : ev.detail.error;
    setReady();
  });
  if (skipEl) skipEl.addEventListener("change", setReady);

  async function gpsGate() {
    if (skipEl && skipEl.checked) return true;
    if (!window.MikkeNearby) return false;
    const r = window.MikkeNearby.recent(PASS_MS) || await window.MikkeNearby.search();
    return !!(r.ok && r.data.has_nearby);
  }

  // 地図 (①さがす) とカメラ (②みっけ) の表示を切り替える
  function showCameraView(on) {
    findView.hidden = on;
    cameraView.hidden = !on;
    if (on) {
      cameraView.scrollIntoView({ block: "start" });
    } else {
      document.dispatchEvent(new CustomEvent("mikke:find-shown"));
    }
  }

  // 分析用: カメラを起動したことだけを送る。失敗しても探索は続ける
  function notifyCameraStart() {
    if (!root.dataset.cameraStartUrl) return;
    post(root.dataset.cameraStartUrl, {}).catch(() => {});
  }

  // ---------- カメラ ----------
  async function startCamera() {
    if (typeof window.jsQR !== "function") {
      setStatus("読み取り機能を読み込めませんでした。ページを再読み込みしてください。");
      return;
    }
    btnStart.disabled = true;
    const ok = await gpsGate();
    setReady();
    if (!ok) return; // 理由 (「ここにはなさそう・・・」など) は地図の上に出ている
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      $("nearby-status").textContent = "このブラウザではカメラを使えません。カメラが使えるブラウザ(Chrome・Safari など)でお試しください。";
      return;
    }
    btnStart.disabled = true;
    showCameraView(true);
    setStatus("カメラを起動しています…");
    ensureImageRefs();
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
    } catch (e) {
      const messages = {
        NotAllowedError: "カメラの利用が許可されていません。ブラウザの設定でカメラを許可してから、もう一度お試しください。",
        NotFoundError: "カメラが見つかりません。カメラのある端末でお試しください。",
        NotReadableError: "ほかのアプリがカメラを使用中のようです。そのアプリを閉じてからお試しください。",
      };
      // 地図にもどして、理由を出す
      showCameraView(false);
      $("nearby-status").textContent = messages[e.name] || "カメラを起動できませんでした。ページを読み込み直して、もう一度お試しください。";
      setReady();
      return;
    }
    clearTarget();
    video.srcObject = stream;
    try { await video.play(); } catch (_) { /* 自動再生制限: ユーザー操作起点なので通常は成功 */ }
    notifyCameraStart();
    setReady();
    setStatus("シンボルをさがしています… 画面の中にシンボルをうつしてください。");
    if (!rafId) rafId = requestAnimationFrame(frame);
  }

  /** カメラを止める。backToMap なら地図 (①さがす) にもどる。 */
  function stopCamera(backToMap = true) {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    if (backToMap) {
      cancelAnimationFrame(rafId);
      rafId = 0;
      clearTarget();
      setStatus("カメラを止めました。");
      showCameraView(false);
    }
  }

  btnStart.addEventListener("click", startCamera);
  btnStop.addEventListener("click", () => stopCamera(true));
  btnCollect.addEventListener("click", collect);
  canvas.addEventListener("pointerdown", (ev) => {
    if (!markHit) return;
    const rect = canvas.getBoundingClientRect();
    const x = (ev.clientX - rect.left) * dpr;
    const y = (ev.clientY - rect.top) * dpr;
    if (Math.hypot(x - markHit.x, y - markHit.y) <= markHit.r) collect();
  });
  // 画面を離れたらカメラを止める (電池とプライバシーのため)
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && stream) stopCamera(true);
  });
})();
