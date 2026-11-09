/*
 * スタッフ用: 画像シンボルの登録 / 撮影角度の管理
 *   角度 (最大 9) ごとに: 撮影 → 四角形で切り抜き (正面補正) → 判定しない部分を塗りつぶし → 決定
 *   まとめて送信すると、サーバーが各角度を検証して保存する。
 */
(() => {
  "use strict";
  const form = document.getElementById("reg-form");
  if (!form) return;
  const $ = (id) => document.getElementById(id);
  const MI = () => window.MikkeImage;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const mode = form.dataset.mode;

  const editor = $("editor");
  const video = $("reg-video");
  const stage = $("stage-canvas");
  const sctx = stage.getContext("2d");
  const handlesBox = $("quad-handles");
  const handles = [...handlesBox.querySelectorAll(".quad-handle")];
  const empty = $("reg-empty");
  const quality = $("reg-quality");
  const errorsEl = $("reg-errors");
  const btnSubmit = $("btn-submit");
  const cells = [...document.querySelectorAll(".angle-cell")];

  const MAX_SOURCE_EDGE = 1600;
  const MIN_KP = 30;

  // 角度ごとの状態: { status: "existing" | "new" | "deleted", thumb, kp, ref, crop, mask }
  const views = {};
  cells.forEach((c) => {
    if (c.dataset.existing) views[c.dataset.angle] = { status: "existing", thumb: c.dataset.thumb, kp: +c.dataset.kp };
  });

  let current = null; // 編集中の角度
  let stream = null;
  let step = "capture";
  let source = null; // 撮影した元画像 (canvas)
  let quad = null; // 元画像座標の四隅 [{x,y}*4]
  let crop = null; // 切り抜き後の canvas
  let mask = null; // 除外マスク canvas (crop と同サイズ)
  let ref = null; // 解析結果
  let analyzeTimer = 0;

  const setQuality = (msg, level = "info") => {
    quality.textContent = msg;
    quality.className = `quality quality-${level}`;
  };

  // ---------- 角度グリッド ----------
  function renderCells() {
    cells.forEach((c) => {
      const v = views[c.dataset.angle];
      const img = c.querySelector(".angle-thumb");
      const state = c.querySelector(".angle-state");
      c.classList.toggle("is-set", !!v && v.status !== "deleted");
      c.classList.toggle("is-deleted", !!v && v.status === "deleted");
      c.classList.toggle("is-current", c.dataset.angle === current);
      c.setAttribute("aria-pressed", c.dataset.angle === current ? "true" : "false");
      if (v && v.status !== "deleted") {
        img.src = v.thumb;
        img.hidden = false;
        state.textContent = `${v.status === "new" ? "新規" : "登録済み"}・${v.kp} 点`;
      } else {
        img.hidden = true;
        state.textContent = v && v.status === "deleted" ? "削除予定" : "未登録";
      }
    });
    const changes = Object.values(views).filter((v) => v.status === "new" || v.status === "deleted").length;
    const active = Object.values(views).filter((v) => v.status !== "deleted").length;
    btnSubmit.disabled = mode === "new" ? active === 0 : changes === 0 || active === 0;
  }

  function openEditor(angle) {
    current = angle;
    const label = cells.find((c) => c.dataset.angle === angle).dataset.label;
    $("editor-angle").textContent = label;
    editor.hidden = false;
    $("btn-angle-delete").hidden = !(views[angle] && views[angle].status !== "deleted");
    resetEditor();
    renderCells();
    $("editor-h").focus();
    editor.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function closeEditor() {
    stopCamera();
    editor.hidden = true;
    current = null;
    renderCells();
  }

  function resetEditor() {
    stopCamera();
    source = quad = crop = mask = ref = null;
    stage.hidden = true;
    empty.hidden = false;
    handlesBox.hidden = true;
    setStep("capture");
    setQuality("「カメラを起動」で撮影するか、「写真を選ぶ」から選んでください。");
  }

  function setStep(s) {
    step = s;
    $("tools-capture").hidden = s !== "capture";
    $("tools-crop").hidden = s !== "crop";
    $("tools-mask").hidden = s !== "mask";
    handlesBox.hidden = s !== "crop";
    stage.classList.toggle("is-painting", s === "mask");
    editor.querySelectorAll(".steps li").forEach((li) => li.classList.toggle("is-active", li.dataset.step === s));
  }

  // ---------- 1. 撮影 ----------
  function stopCamera() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    video.hidden = true;
    $("btn-shutter").hidden = true;
  }

  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setQuality("このブラウザではカメラを使えません。「写真を選ぶ」をお使いください。", "bad");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false,
      });
    } catch (e) {
      setQuality(e.name === "NotAllowedError"
        ? "カメラの利用が許可されていません。ブラウザの設定で許可してください。"
        : "カメラを起動できませんでした。「写真を選ぶ」をお使いください。", "bad");
      return;
    }
    video.srcObject = stream;
    video.hidden = false;
    stage.hidden = true;
    empty.hidden = true;
    $("btn-shutter").hidden = false;
    try { await video.play(); } catch (_) { /* ユーザー操作起点なので通常は成功 */ }
    setQuality("シンボルにしたいものを画面に入れて「撮影する」を押してください。");
  }

  function toSourceCanvas(img, sw, sh) {
    const s = Math.min(1, MAX_SOURCE_EDGE / Math.max(sw, sh));
    const c = document.createElement("canvas");
    c.width = Math.round(sw * s);
    c.height = Math.round(sh * s);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  function useSource(c) {
    source = c;
    const iw = c.width;
    const ih = c.height;
    quad = [
      { x: iw * 0.12, y: ih * 0.12 }, { x: iw * 0.88, y: ih * 0.12 },
      { x: iw * 0.88, y: ih * 0.88 }, { x: iw * 0.12, y: ih * 0.88 },
    ];
    stage.width = iw;
    stage.height = ih;
    stage.hidden = false;
    empty.hidden = true;
    setStep("crop");
    drawCrop();
    setQuality("四隅の ● を動かして、シンボルにする部分を囲んでください。");
  }

  // ---------- 2. 四角形で切り抜き ----------
  function drawCrop() {
    sctx.drawImage(source, 0, 0);
    // 囲みの外側を暗くする
    sctx.save();
    sctx.fillStyle = "rgba(16, 24, 32, 0.55)";
    sctx.beginPath();
    sctx.rect(0, 0, stage.width, stage.height);
    sctx.moveTo(quad[0].x, quad[0].y);
    for (let i = 3; i >= 0; i--) sctx.lineTo(quad[i].x, quad[i].y);
    sctx.closePath();
    sctx.fill("evenodd");
    sctx.strokeStyle = "#FFD84D";
    sctx.lineWidth = Math.max(2, stage.width / 300);
    sctx.beginPath();
    quad.forEach((p, i) => (i ? sctx.lineTo(p.x, p.y) : sctx.moveTo(p.x, p.y)));
    sctx.closePath();
    sctx.stroke();
    sctx.restore();
    placeHandles();
  }

  function stageScale() {
    const r = stage.getBoundingClientRect();
    return { r, k: stage.width / r.width };
  }

  function placeHandles() {
    const { r, k } = stageScale();
    const base = handlesBox.getBoundingClientRect();
    handles.forEach((h, i) => {
      h.style.left = `${r.left - base.left + quad[i].x / k}px`;
      h.style.top = `${r.top - base.top + quad[i].y / k}px`;
    });
  }

  function clampPoint(p) {
    return { x: Math.min(Math.max(p.x, 0), stage.width), y: Math.min(Math.max(p.y, 0), stage.height) };
  }

  handles.forEach((h) => {
    const i = +h.dataset.i;
    h.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      h.setPointerCapture(ev.pointerId);
      const move = (e) => {
        const { r, k } = stageScale();
        quad[i] = clampPoint({ x: (e.clientX - r.left) * k, y: (e.clientY - r.top) * k });
        drawCrop();
      };
      const up = () => {
        h.removeEventListener("pointermove", move);
        h.removeEventListener("pointerup", up);
        h.removeEventListener("pointercancel", up);
      };
      h.addEventListener("pointermove", move);
      h.addEventListener("pointerup", up);
      h.addEventListener("pointercancel", up);
    });
    h.addEventListener("keydown", (ev) => {
      const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[ev.key];
      if (!d) return;
      ev.preventDefault();
      const { k } = stageScale();
      const stepPx = (ev.shiftKey ? 20 : 4) * k;
      quad[i] = clampPoint({ x: quad[i].x + d[0] * stepPx, y: quad[i].y + d[1] * stepPx });
      drawCrop();
    });
  });
  window.addEventListener("resize", () => { if (step === "crop" && source) placeHandles(); });

  function quadIsValid() {
    let sign = 0;
    for (let i = 0; i < 4; i++) {
      const a = quad[i];
      const b = quad[(i + 1) % 4];
      const c = quad[(i + 2) % 4];
      const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
      const s = Math.sign(cross);
      if (s === 0 || (sign && s !== sign)) return false;
      sign = s;
      if (Math.hypot(b.x - a.x, b.y - a.y) < 40) return false;
    }
    return true;
  }

  function doCrop() {
    if (!quadIsValid()) {
      setQuality("四角形がねじれているか、小さすぎます。四隅を「左上・右上・右下・左下」の順に合わせてください。", "bad");
      return;
    }
    setQuality("切り抜いています…");
    setTimeout(() => {
      crop = MI().cropQuad(source, quad, 800);
      mask = document.createElement("canvas");
      mask.width = crop.width;
      mask.height = crop.height;
      stage.width = crop.width;
      stage.height = crop.height;
      setStep("mask");
      analyze();
    }, 0);
  }

  // ---------- 3. 塗りつぶし (判定しない部分) ----------
  function drawMaskStage() {
    sctx.clearRect(0, 0, stage.width, stage.height);
    sctx.drawImage(crop, 0, 0);
    sctx.save();
    sctx.globalAlpha = 0.5;
    sctx.drawImage(tintedMask(), 0, 0);
    sctx.restore();
    if (ref) {
      const k = crop.width / ref.width;
      sctx.fillStyle = "rgba(255, 216, 77, 0.95)";
      sctx.strokeStyle = "rgba(31, 42, 68, 0.9)";
      sctx.lineWidth = 1;
      const r = Math.max(2, crop.width / 220);
      for (const [x, y] of ref.features.kp) {
        sctx.beginPath();
        sctx.arc(x * k, y * k, r, 0, Math.PI * 2);
        sctx.fill();
        sctx.stroke();
      }
    }
  }

  let tintCanvas = null;
  function tintedMask() {
    if (!tintCanvas) tintCanvas = document.createElement("canvas");
    tintCanvas.width = mask.width;
    tintCanvas.height = mask.height;
    const t = tintCanvas.getContext("2d");
    t.drawImage(mask, 0, 0);
    t.globalCompositeOperation = "source-in";
    t.fillStyle = "#E5484D";
    t.fillRect(0, 0, mask.width, mask.height);
    t.globalCompositeOperation = "source-over";
    return tintCanvas;
  }

  function analyze() {
    ref = MI().extractReference(crop, mask);
    drawMaskStage();
    const n = ref.features.kp.length;
    const masked = countMasked(ref.mask);
    if (masked > 0.75) {
      setQuality("塗りつぶした部分が多すぎます。判定に使う部分を全体の 1/4 以上残してください。", "bad");
    } else if (n < MIN_KP) {
      setQuality(`特徴点 ${n} 個: 少なすぎて認識できません。模様や文字がはっきり写った部分を囲み直してください。`, "bad");
    } else if (n < 120) {
      setQuality(`特徴点 ${n} 個: やや少なめです。登録はできますが、近くで撮り直すと見つけやすくなります。`, "warn");
    } else {
      setQuality(`特徴点 ${n} 個: 良好です。`, "good");
    }
    $("btn-angle-done").disabled = masked > 0.75 || n < MIN_KP;
  }

  function countMasked(bits) {
    let n = 0;
    for (const b of bits) for (let i = 0; i < 8; i++) n += (b >> i) & 1;
    return n / (bits.length * 8);
  }

  let painting = false;
  function paintAt(ev) {
    const { r, k } = stageScale();
    const x = (ev.clientX - r.left) * k;
    const y = (ev.clientY - r.top) * k;
    const radius = (+$("brush-size").value / 2) * k;
    const m = mask.getContext("2d");
    const erase = form.querySelector('input[name="brush-mode"]:checked').value === "erase";
    m.globalCompositeOperation = erase ? "destination-out" : "source-over";
    m.fillStyle = "#000";
    m.beginPath();
    m.arc(x, y, radius, 0, Math.PI * 2);
    m.fill();
    m.globalCompositeOperation = "source-over";
    drawMaskStage();
  }
  stage.addEventListener("pointerdown", (ev) => {
    if (step !== "mask") return;
    ev.preventDefault();
    painting = true;
    stage.setPointerCapture(ev.pointerId);
    clearTimeout(analyzeTimer);
    paintAt(ev);
  });
  stage.addEventListener("pointermove", (ev) => { if (painting) paintAt(ev); });
  const endPaint = () => {
    if (!painting) return;
    painting = false;
    clearTimeout(analyzeTimer);
    analyzeTimer = setTimeout(analyze, 250);
  };
  stage.addEventListener("pointerup", endPaint);
  stage.addEventListener("pointercancel", endPaint);

  // ---------- 決定・送信 ----------
  function finishAngle() {
    if (!ref || ref.features.kp.length < MIN_KP) return;
    const prev = views[current];
    if (prev && prev.thumb && prev.status === "new") URL.revokeObjectURL(prev.thumb);
    const thumb = document.createElement("canvas");
    const s = 160 / Math.max(crop.width, crop.height);
    thumb.width = Math.round(crop.width * s);
    thumb.height = Math.round(crop.height * s);
    const t = thumb.getContext("2d");
    t.drawImage(crop, 0, 0, thumb.width, thumb.height);
    t.globalAlpha = 0.5;
    t.drawImage(tintedMask(), 0, 0, thumb.width, thumb.height);
    views[current] = { status: "new", thumb: thumb.toDataURL("image/jpeg", 0.8), kp: ref.features.kp.length, ref, crop };
    const label = $("editor-angle").textContent;
    closeEditor();
    setQualityOutside(`「${label}」を設定しました。ほかの角度も追加できます。`);
  }

  function setQualityOutside(msg) {
    errorsEl.textContent = "";
    const live = document.querySelector(".messages") || errorsEl;
    if (live === errorsEl) {
      errorsEl.className = "help";
      errorsEl.textContent = msg;
    }
  }

  async function submit(ev) {
    ev.preventDefault();
    errorsEl.className = "errors";
    errorsEl.textContent = "";
    const changed = Object.entries(views).filter(([, v]) => v.status === "new");
    const deleted = Object.entries(views).filter(([, v]) => v.status === "deleted").map(([a]) => a);
    if (!changed.length && !deleted.length) return;
    btnSubmit.disabled = true;
    const original = btnSubmit.textContent;
    btnSubmit.textContent = "送信しています…";
    const fd = new FormData(form);
    for (const [angle, v] of changed) {
      // canvas から JPEG を作り直す = EXIF (撮影位置など) を含まない
      const jpeg = await new Promise((res) => v.crop.toBlob(res, "image/jpeg", 0.85));
      fd.append(`${angle}_image`, jpeg, `${angle}.jpg`);
      fd.append(`${angle}_features`, new Blob([JSON.stringify(v.ref.features)], { type: "application/json" }), `${angle}.json`);
      fd.append(`${angle}_patch`, MI().toBase64(v.ref.patch));
      fd.append(`${angle}_mask`, MI().toBase64(v.ref.mask));
    }
    fd.append("angles", changed.map(([a]) => a).join(","));
    fd.append("delete", deleted.join(","));
    let res = null;
    let data = {};
    try {
      res = await fetch(form.dataset.api, { method: "POST", body: fd, credentials: "same-origin", headers: { "X-CSRFToken": csrf } });
      data = await res.json();
    } catch (_) {
      errorsEl.textContent = "通信できませんでした。もう一度お試しください。";
    }
    if (res && res.ok && data.ok) {
      window.location.href = data.redirect;
      return;
    }
    if (data.errors) {
      const ul = document.createElement("ul");
      data.errors.forEach((e) => {
        const li = document.createElement("li");
        li.textContent = e;
        ul.appendChild(li);
      });
      errorsEl.replaceChildren(ul);
    }
    btnSubmit.textContent = original;
    renderCells();
  }

  // ---------- イベント ----------
  cells.forEach((c) => c.addEventListener("click", () => openEditor(c.dataset.angle)));
  $("btn-cam").addEventListener("click", startCamera);
  $("btn-shutter").addEventListener("click", () => {
    if (!video.videoWidth) return;
    const c = toSourceCanvas(video, video.videoWidth, video.videoHeight);
    stopCamera();
    useSource(c);
  });
  $("reg-file").addEventListener("change", (ev) => {
    const f = ev.target.files && ev.target.files[0];
    ev.target.value = "";
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) {
      setQuality("写真が大きすぎます(20MB まで)。", "bad");
      return;
    }
    stopCamera();
    const img = new Image();
    img.onload = () => {
      useSource(toSourceCanvas(img, img.naturalWidth, img.naturalHeight));
      URL.revokeObjectURL(img.src);
    };
    img.onerror = () => setQuality("写真を読み込めませんでした。", "bad");
    img.src = URL.createObjectURL(f);
  });
  $("btn-crop").addEventListener("click", doCrop);
  $("btn-quad-reset").addEventListener("click", () => {
    quad = [{ x: 0, y: 0 }, { x: stage.width, y: 0 }, { x: stage.width, y: stage.height }, { x: 0, y: stage.height }];
    drawCrop();
  });
  $("btn-recapture").addEventListener("click", resetEditor);
  $("btn-mask-clear").addEventListener("click", () => {
    mask.getContext("2d").clearRect(0, 0, mask.width, mask.height);
    analyze();
  });
  $("btn-back-crop").addEventListener("click", () => {
    stage.width = source.width;
    stage.height = source.height;
    setStep("crop");
    drawCrop();
  });
  $("btn-angle-done").addEventListener("click", finishAngle);
  $("btn-editor-close").addEventListener("click", closeEditor);
  $("btn-angle-delete").addEventListener("click", () => {
    const v = views[current];
    if (!v) return;
    if (v.status === "existing") v.status = "deleted";
    else delete views[current];
    closeEditor();
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopCamera(); });
  form.addEventListener("submit", submit);
  renderCells();

  // 動作確認・自動テスト用のフック
  window.__mikkeRegister = { openEditor, useSource, setQuad: (q) => { quad = q; drawCrop(); }, doCrop, finishAngle, analyze, get ref() { return ref; } };
})();
