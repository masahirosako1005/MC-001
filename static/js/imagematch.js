/*
 * みっけ 画像シンボル認識モジュール (window.MikkeImage)
 *
 * jsfeat 0.0.8 を使った平面画像の検出:
 *   1. グレースケール化 + ガウスぼかし
 *   2. YAPE06 で特徴点検出 → 方向 (intensity centroid) → ORB 記述子 (32 バイト)
 *   3. ハミング距離 + 比率テストで対応付け
 *   4. RANSAC で射影変換 (ホモグラフィ) を推定 → 参照画像の四隅を映像上に投影
 *   5. 射影変換で映像から 32x32 パッチを切り出し、サーバーで照合する
 * 参照画像は複数の縮尺で特徴量を作り、遠くに小さく写った場合にも対応する。
 */
(() => {
  "use strict";
  const J = window.jsfeat;
  if (!J) return;

  const DESC = 32;
  const PATCH = 32;
  const BORDER = 17; // ORB の 32px パッチ + 方向計算 (半径 15) に必要な余白
  const U_MAX = new Int32Array([15, 15, 15, 15, 14, 14, 14, 13, 13, 12, 11, 10, 9, 8, 6, 3, 0]);
  const IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1];
  const REF_LONG_EDGE = 480;
  // 遠くから小さく写った場合にも合うよう、参照画像は 6 段階の縮尺で特徴量を作る
  const REF_SCALES = [1, 0.75, 0.56, 0.42, 0.32, 0.24];
  const REF_COUNTS = [240, 160, 140, 110, 100, 90]; // 合計 840 (サーバー上限 900 以内)
  const GRID = 4; // 特徴点を 4x4 の区画に分散させ、背景の模様に点を取られすぎないようにする
  // 距離・角度に厳密すぎないよう、対応点の条件はゆるめにしている (最終判定はサーバーの類似度 65%)
  const MIN_MATCHES = 8;
  const MAX_HAMMING = 72;
  const RATIO = 0.85;
  // 無関係な画像でも RANSAC は偶然 4〜5 点そろうことがあるため、正解とみなすのは 10 点以上
  const MIN_INLIERS = 10;
  const MIN_INLIER_RATIO = 0.08;
  const SAME_POINT_PX = 6; // 参照画像 (基準縮尺) 上でこれ以内なら同じ点とみなす
  const debug = { matches: 0, inliers: 0 }; // 直近の照合結果 (調整・検証用)

  const kernel = new J.motion_model.homography2d();
  const ransacParams = new J.ransac_params_t(4, 4, 0.5, 0.99);
  const pool = [];
  const rasterCanvas = document.createElement("canvas");
  const rasterCtx = rasterCanvas.getContext("2d", { willReadFrequently: true });

  function ensurePool(n) {
    while (pool.length < n) pool.push(new J.keypoint_t(0, 0, 0, 0, -1));
  }

  function rasterize(source, w, h) {
    rasterCanvas.width = w;
    rasterCanvas.height = h;
    rasterCtx.drawImage(source, 0, 0, w, h);
    return rasterCtx.getImageData(0, 0, w, h);
  }

  function grayFromImageData(img) {
    const g = new J.matrix_t(img.width, img.height, J.U8C1_t);
    J.imgproc.grayscale(img.data, img.width, img.height, g, J.COLOR_RGBA2GRAY);
    const b = new J.matrix_t(img.width, img.height, J.U8C1_t);
    J.imgproc.gaussian_blur(g, b, 5, 0);
    return b;
  }

  // 特徴点まわりの明るさの重心方向 (ORB の回転不変化に使う)
  function icAngle(img, px, py) {
    const src = img.data;
    const step = img.cols;
    const center = (py * step + px) | 0;
    let m01 = 0;
    let m10 = 0;
    for (let u = -15; u <= 15; ++u) m10 += u * src[center + u];
    for (let v = 1; v <= 15; ++v) {
      let vSum = 0;
      const d = U_MAX[v];
      for (let u = -d; u <= d; ++u) {
        const plus = src[center + u + v * step];
        const minus = src[center + u - v * step];
        vSum += plus - minus;
        m10 += u * (plus + minus);
      }
      m01 += v * vSum;
    }
    return Math.atan2(m01, m10);
  }

  function detectAndDescribe(gray, maxCount) {
    const w = gray.cols;
    const h = gray.rows;
    if (w <= BORDER * 2 + 2 || h <= BORDER * 2 + 2) return { kps: [], desc: new Uint8Array(0) };
    ensurePool(((w * h) >> 2) + 64);
    let n = 0;
    // 模様が少ない画像でも点が取れるよう、しきい値を段階的に下げる
    for (const [lap, eig] of [[30, 25], [18, 14], [10, 8]]) {
      J.yape06.laplacian_threshold = lap;
      J.yape06.min_eigen_value_threshold = eig;
      n = J.yape06.detect(gray, pool, BORDER);
      if (n >= maxCount * 0.6) break;
    }
    const order = new Array(n);
    for (let i = 0; i < n; i++) order[i] = i;
    order.sort((a, b) => pool[b].score - pool[a].score);
    // 区画ごとの上限まで強い点から選び、余った枠を残りの強い点で埋める
    const quota = Math.ceil(maxCount / (GRID * GRID));
    const perCell = new Int32Array(GRID * GRID);
    const chosen = [];
    const rest = [];
    for (let i = 0; i < n; i++) {
      const c = pool[order[i]];
      const cell = Math.min(GRID - 1, (c.y * GRID / h) | 0) * GRID + Math.min(GRID - 1, (c.x * GRID / w) | 0);
      if (perCell[cell] < quota) {
        perCell[cell]++;
        chosen.push(order[i]);
      } else {
        rest.push(order[i]);
      }
    }
    for (let i = 0; chosen.length < maxCount && i < rest.length; i++) chosen.push(rest[i]);
    const k = Math.min(chosen.length, maxCount);
    const pts = new Array(k);
    for (let i = 0; i < k; i++) {
      const c = pool[chosen[i]];
      pts[i] = new J.keypoint_t(c.x, c.y, c.score, 0, icAngle(gray, c.x, c.y));
    }
    const descM = new J.matrix_t(DESC, Math.max(1, k), J.U8C1_t);
    if (k > 0) J.orb.describe(gray, pts, k, descM);
    const desc = new Uint8Array(k * DESC);
    desc.set(descM.data.subarray(0, k * DESC));
    return { kps: pts.map((p) => ({ x: p.x, y: p.y })), desc };
  }

  function popcnt(v) {
    v -= (v >>> 1) & 0x55555555;
    v = (v & 0x33333333) + ((v >>> 2) & 0x33333333);
    return Math.imul((v + (v >>> 4)) & 0x0f0f0f0f, 0x01010101) >>> 24;
  }

  function project(H, x, y) {
    const w = H[6] * x + H[7] * y + H[8];
    return { x: (H[0] * x + H[1] * y + H[2]) / w, y: (H[3] * x + H[4] * y + H[5]) / w };
  }

  function validQuad(q, fw, fh) {
    let sign = 0;
    for (let i = 0; i < 4; i++) {
      const a = q[i];
      const b = q[(i + 1) % 4];
      const c = q[(i + 2) % 4];
      const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
      if (!Number.isFinite(cross) || Math.abs(cross) < 1e-6) return false;
      const s = Math.sign(cross);
      if (sign === 0) sign = s;
      else if (s !== sign) return false; // 凸でない = ありえない変形
      if (Math.hypot(b.x - a.x, b.y - a.y) < 12) return false;
    }
    let area = 0;
    for (let i = 0; i < 4; i++) {
      const a = q[i];
      const b = q[(i + 1) % 4];
      area += a.x * b.y - b.x * a.y;
    }
    area = Math.abs(area) / 2;
    const frameArea = fw * fh;
    if (area < frameArea * 0.004 || area > frameArea * 6) return false;
    return q.every((p) => p.x > -fw * 1.5 && p.x < fw * 2.5 && p.y > -fh * 1.5 && p.y < fh * 2.5);
  }

  function toBase64(u8) {
    let s = "";
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  }

  function fromBase64(b64) {
    const s = atob(b64);
    const u8 = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u8[i] = s.charCodeAt(i);
    return u8;
  }

  /** 射影変換 H (参照画像座標 → グレー画像座標) で 32x32 の照合用パッチを切り出す */
  function patchFromGray(gray, H, refW, refH) {
    const out = new Uint8Array(PATCH * PATCH);
    const w = gray.cols;
    const h = gray.rows;
    const d = gray.data;
    for (let cy = 0; cy < PATCH; cy++) {
      for (let cx = 0; cx < PATCH; cx++) {
        let sum = 0;
        let cnt = 0;
        for (let sy = 0; sy < 3; sy++) {
          for (let sx = 0; sx < 3; sx++) {
            const u = ((cx + (sx + 0.5) / 3) * refW) / PATCH;
            const v = ((cy + (sy + 0.5) / 3) * refH) / PATCH;
            const p = project(H, u, v);
            const xi = Math.round(p.x);
            const yi = Math.round(p.y);
            if (xi >= 0 && yi >= 0 && xi < w && yi < h) {
              sum += d[yi * w + xi];
              cnt++;
            }
          }
        }
        out[cy * PATCH + cx] = cnt ? Math.round(sum / cnt) : 0;
      }
    }
    return out;
  }

  /**
   * 除外マスク (塗りつぶし) を w×h の真偽配列にする。true = 判定しない。
   * maskCanvas は参照画像と同じ縦横比で、塗った部分の不透明度 > 0。
   */
  function maskGrid(maskCanvas, w, h) {
    if (!maskCanvas) return null;
    const img = rasterize(maskCanvas, w, h).data;
    const out = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) out[i] = img[i * 4 + 3] > 64 ? 1 : 0;
    return out;
  }

  /** 32x32 マスク (1 = 除外) を 128 バイトのビット列に詰める */
  function packMask32(maskCanvas) {
    const bits = new Uint8Array(PATCH * PATCH / 8);
    if (!maskCanvas) return bits;
    const g = maskGrid(maskCanvas, PATCH * 3, PATCH * 3);
    for (let cy = 0; cy < PATCH; cy++) {
      for (let cx = 0; cx < PATCH; cx++) {
        let n = 0;
        for (let sy = 0; sy < 3; sy++) for (let sx = 0; sx < 3; sx++) n += g[(cy * 3 + sy) * PATCH * 3 + cx * 3 + sx];
        if (n >= 5) { // セルの半分以上を塗ったら除外
          const i = cy * PATCH + cx;
          bits[i >> 3] |= 0x80 >> (i & 7);
        }
      }
    }
    return bits;
  }

  /**
   * スタッフの登録用: 参照画像 (切り抜き済み) から複数縮尺の特徴量と照合用パッチを作る。
   * maskCanvas で塗った部分の特徴点は使わない。
   */
  function extractReference(source, maskCanvas = null) {
    const sw = source.naturalWidth || source.videoWidth || source.width;
    const sh = source.naturalHeight || source.videoHeight || source.height;
    const s0 = Math.min(1, REF_LONG_EDGE / Math.max(sw, sh));
    const w0 = Math.round(sw * s0);
    const h0 = Math.round(sh * s0);
    const mask0 = maskGrid(maskCanvas, w0, h0);
    const kp = [];
    const parts = [];
    for (const s of REF_SCALES) {
      const w = Math.round(w0 * s);
      const h = Math.round(h0 * s);
      if (Math.min(w, h) < 64) break;
      const f = detectAndDescribe(grayFromImageData(rasterize(source, w, h)), REF_COUNTS[REF_SCALES.indexOf(s)]);
      const keep = [];
      f.kps.forEach((p, i) => {
        const x = p.x / s;
        const y = p.y / s;
        if (mask0 && mask0[Math.min(h0 - 1, Math.round(y)) * w0 + Math.min(w0 - 1, Math.round(x))]) return;
        if (kp.length + keep.length >= 880) return;
        kp.push([Math.round(x * 10) / 10, Math.round(y * 10) / 10]);
        keep.push(i);
      });
      const d = new Uint8Array(keep.length * DESC);
      keep.forEach((i, j) => d.set(f.desc.subarray(i * DESC, (i + 1) * DESC), j * DESC));
      parts.push(d);
    }
    const desc = new Uint8Array(kp.length * DESC);
    let off = 0;
    for (const p of parts) {
      desc.set(p, off);
      off += p.length;
    }
    const gray0 = grayFromImageData(rasterize(source, w0, h0));
    const patch = patchFromGray(gray0, IDENTITY, w0, h0);
    return {
      features: { v: 1, w: w0, h: h0, kp, desc: toBase64(desc) },
      patch, mask: packMask32(maskCanvas), width: w0, height: h0,
    };
  }

  /** 4 点の対応から射影変換 (src → dst) を求める */
  function homography4(src, dst) {
    const m = new J.matrix_t(3, 3, J.F32C1_t);
    J.math.perspective_4point_transform(m,
      src[0].x, src[0].y, dst[0].x, dst[0].y,
      src[1].x, src[1].y, dst[1].x, dst[1].y,
      src[2].x, src[2].y, dst[2].x, dst[2].y,
      src[3].x, src[3].y, dst[3].x, dst[3].y);
    return Array.from(m.data.subarray(0, 9));
  }

  /**
   * 写真の中の四角形 quad (左上・右上・右下・左下) を切り抜き、正面から見た長方形に補正する。
   * 斜めから撮った看板もまっすぐな画像になる。
   */
  function cropQuad(source, quad, maxEdge = 800) {
    const sw = source.naturalWidth || source.width;
    const sh = source.naturalHeight || source.height;
    const src = rasterize(source, sw, sh);
    const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
    let w = (dist(quad[0], quad[1]) + dist(quad[3], quad[2])) / 2;
    let h = (dist(quad[0], quad[3]) + dist(quad[1], quad[2])) / 2;
    const k = Math.min(1, maxEdge / Math.max(w, h));
    w = Math.max(64, Math.round(w * k));
    h = Math.max(64, Math.round(h * k));
    const H = homography4([{ x: 0, y: 0 }, { x: w, y: 0 }, { x: w, y: h }, { x: 0, y: h }], quad);
    const out = new ImageData(w, h);
    const sd = src.data;
    const od = out.data;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const p = project(H, x + 0.5, y + 0.5);
        const fx = Math.min(Math.max(p.x - 0.5, 0), sw - 1.001);
        const fy = Math.min(Math.max(p.y - 0.5, 0), sh - 1.001);
        const x0 = fx | 0;
        const y0 = fy | 0;
        const ax = fx - x0;
        const ay = fy - y0;
        const i00 = (y0 * sw + x0) * 4;
        const i10 = i00 + 4;
        const i01 = i00 + sw * 4;
        const i11 = i01 + 4;
        const o = (y * w + x) * 4;
        for (let c = 0; c < 3; c++) {
          od[o + c] = (sd[i00 + c] * (1 - ax) + sd[i10 + c] * ax) * (1 - ay) + (sd[i01 + c] * (1 - ax) + sd[i11 + c] * ax) * ay;
        }
        od[o + 3] = 255;
      }
    }
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    c.getContext("2d").putImageData(out, 0, 0);
    return c;
  }

  /** サーバーから受け取った特徴量を照合しやすい形に変換 */
  function prepareReference(f) {
    const u8 = fromBase64(f.desc);
    return {
      id: f.id,
      view: f.view,
      w: f.w,
      h: f.h,
      kps: f.kp.map((p) => ({ x: p[0], y: p[1] })),
      d32: new Int32Array(u8.buffer, 0, u8.length >> 2),
    };
  }

  /** カメラ映像 1 フレーム分の特徴量 */
  function frameFeatures(imageData, maxCount = 420) {
    const gray = grayFromImageData(imageData);
    const f = detectAndDescribe(gray, maxCount);
    return { gray, w: imageData.width, h: imageData.height, kps: f.kps, d32: new Int32Array(f.desc.buffer) };
  }

  /** フレームの中に参照画像があれば {H, corners, inliers} を返す */
  function match(frame, ref) {
    const fd = frame.d32;
    const rd = ref.d32;
    const fn = frame.kps.length;
    const rn = ref.kps.length;
    if (fn < MIN_MATCHES || rn < MIN_MATCHES) return null;
    const from = [];
    const to = [];
    const rk = ref.kps;
    // 同じ点が複数の縮尺に入っているので、比率テストの「2 番目」は別の位置の点だけで数える
    const far = (a, b) => Math.abs(rk[a].x - rk[b].x) + Math.abs(rk[a].y - rk[b].y) > SAME_POINT_PX;
    for (let i = 0; i < fn; i++) {
      const fo = i * 8;
      let best = 1e9;
      let second = 1e9;
      let bj = -1;
      for (let j = 0; j < rn; j++) {
        const ro = j * 8;
        // 前半 128 bit の時点で 2 番目より遠ければ打ち切る (高速化)
        let dist = popcnt(fd[fo] ^ rd[ro]) + popcnt(fd[fo + 1] ^ rd[ro + 1])
          + popcnt(fd[fo + 2] ^ rd[ro + 2]) + popcnt(fd[fo + 3] ^ rd[ro + 3]);
        if (dist >= second) continue; // 残りを足しても best にも 2 番目にもならない
        dist += popcnt(fd[fo + 4] ^ rd[ro + 4]) + popcnt(fd[fo + 5] ^ rd[ro + 5])
          + popcnt(fd[fo + 6] ^ rd[ro + 6]) + popcnt(fd[fo + 7] ^ rd[ro + 7]);
        if (dist < best) {
          if (bj < 0 || far(j, bj)) second = best;
          best = dist;
          bj = j;
        } else if (dist < second && far(j, bj)) {
          second = dist;
        }
      }
      if (bj >= 0 && best <= MAX_HAMMING && best < RATIO * second) {
        from.push(ref.kps[bj]);
        to.push(frame.kps[i]);
      }
    }
    const count = from.length;
    debug.matches = count;
    debug.inliers = 0;
    if (count < MIN_MATCHES) return null;
    const Hm = new J.matrix_t(3, 3, J.F32C1_t);
    const mask = new J.matrix_t(count, 1, J.U8C1_t);
    if (!J.motion_estimator.ransac(ransacParams, kernel, from, to, count, Hm, mask, 2000)) return null;
    let inliers = 0;
    for (let i = 0; i < count; i++) inliers += mask.data[i];
    debug.inliers = inliers;
    if (inliers < MIN_INLIERS || inliers < count * MIN_INLIER_RATIO) return null;
    // RANSAC の結果は 4 点だけから作られるので、すべての正解点で作り直して精度を上げる
    const inFrom = [];
    const inTo = [];
    for (let i = 0; i < count; i++) {
      if (mask.data[i]) {
        inFrom.push(from[i]);
        inTo.push(to[i]);
      }
    }
    const refined = new J.matrix_t(3, 3, J.F32C1_t);
    if (kernel.run(inFrom, inTo, refined, inliers) > 0 && Number.isFinite(refined.data[0])) {
      refined.copy_to(Hm);
    }
    const H = Array.from(Hm.data.subarray(0, 9));
    const corners = [[0, 0], [ref.w, 0], [ref.w, ref.h], [0, ref.h]].map(([x, y]) => project(H, x, y));
    if (!validQuad(corners, frame.w, frame.h)) return null;
    return { H, corners, inliers };
  }

  window.MikkeImage = {
    extractReference, prepareReference, frameFeatures, match, patchFromGray, rasterize, toBase64, IDENTITY,
    cropQuad, homography4, debug,
  };
})();
