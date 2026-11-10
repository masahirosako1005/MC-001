/*
 * みっけ 「こんな人が獲得しているよ」: 直近に同じスポットでみっけした人と、その人のコーデ。
 * コーデを手に入れたスポット名から「これをみっけに行く」で地図に案内する。
 * reward_dialog.js が出す mikke:reward-shown を受け取って表示する。
 */
(() => {
  "use strict";
  const root = document.getElementById("ar");
  const dialog = document.getElementById("reward-dialog");
  if (!root || !dialog || !document.getElementById("reward-finders")) return;
  const $ = (id) => document.getElementById(id);

  // ---------- こんな人が獲得しているよ (直近 30 分に同じシンボルでみっけした人) ----------
  const finderSection = $("reward-finders");
  const finderList = $("finder-list");
  const finderView = $("finder-view");
  const rewardMain = $("reward-main");
  const finderItems = $("finder-items");
  const finderObtained = $("finder-obtained");
  const finderAvatar = $("finder-avatar");
  // URL は {% url %} で作った雛形 (…/finders/TOKEN/) の TOKEN を置き換えて作る
  const finderUrl = (token, rest = "") => root.dataset.finderUrl.replace("TOKEN", encodeURIComponent(token)) + rest;
  let finderOpener = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function renderFinders(list) {
    finderList.replaceChildren();
    finderSection.hidden = !list.length;
    for (const f of list) {
      const li = el("li");
      const b = el("button", "finder-chip");
      b.type = "button";
      const img = el("img");
      img.src = finderUrl(f.token, "avatar.svg");
      img.alt = "";
      img.width = 44;
      img.height = 66;
      img.loading = "lazy";
      b.append(img, el("span", "finder-chip-name", f.nickname), el("span", "finder-chip-ago", f.ago));
      b.setAttribute("aria-label", `${f.nickname}さん(${f.ago})のコーデを見る`);
      b.addEventListener("click", () => openFinder(f, b));
      li.appendChild(b);
      finderList.appendChild(li);
    }
  }

  function showFinderView(on) {
    finderView.hidden = !on;
    rewardMain.hidden = on;
    // ダイアログの名前 (読み上げ) を、いま見えている見出しに合わせる (隠れた見出しを指さないように)
    dialog.setAttribute("aria-labelledby", on ? "finder-name" : "reward-title");
  }

  async function openFinder(f, opener) {
    finderOpener = opener;
    showFinderView(true);
    $("finder-name").textContent = `${f.nickname}さんのコーデ`;
    finderAvatar.src = finderUrl(f.token, "avatar.svg");
    finderAvatar.alt = `${f.nickname}さんのアバター`;
    finderItems.replaceChildren();
    $("finder-goto").hidden = true;
    finderObtained.textContent = "読み込んでいます…";
    $("finder-back").focus();
    let d;
    try {
      const res = await fetch(finderUrl(f.token), { credentials: "same-origin" });
      if (!res.ok) throw new Error(String(res.status));
      d = await res.json();
    } catch (_) {
      finderObtained.textContent = "この人のコーデは、いまは見られません(公開をやめたか、時間がたちました)。";
      return;
    }
    finderObtained.textContent = "アイテムを押すと、どこで手に入れたかが見られます。";
    for (const it of d.items) {
      const li = el("li");
      const b = el("button", "finder-item");
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      const img = el("img");
      img.src = it.image;
      img.alt = "";
      img.width = 64;
      img.height = 64;
      img.loading = "lazy";
      b.append(img, el("span", "finder-item-cat", it.category), el("span", "finder-item-name", it.name));
      b.addEventListener("click", () => {
        for (const other of finderItems.querySelectorAll("button")) other.setAttribute("aria-pressed", "false");
        b.setAttribute("aria-pressed", "true");
        showObtained(it);
      });
      li.appendChild(b);
      finderItems.appendChild(li);
    }
  }

  $("finder-back").addEventListener("click", () => {
    showFinderView(false);
    if (finderOpener) finderOpener.focus();
  });

  // どこで手に入れたか。スポット名は押せるようにして「これをみっけに行く」につなぐ
  const gotoBox = $("finder-goto");
  let gotoTarget = null;

  function showObtained(it) {
    gotoBox.hidden = true;
    finderObtained.replaceChildren();
    if (!it.spot) {
      finderObtained.textContent = `「${it.name}」は、${it.obtained}`;
      return;
    }
    const link = el("button", "spot-link", it.spot.name);
    link.type = "button";
    link.setAttribute("aria-label", `${it.spot.name}(地図で見る)`);
    link.addEventListener("click", () => openGoto(it, link));
    finderObtained.append(`「${it.name}」は、`, link, `でみっけ${it.season ? `(${it.season})` : ""}`);
  }

  function openGoto(it, opener) {
    gotoTarget = { ...it.spot, item: it.name, opener };
    $("finder-goto-title").textContent = `「${it.name}」を ${it.spot.name} でみっけしよう`;
    gotoBox.hidden = false;
    $("finder-goto-yes").focus();
  }

  $("finder-goto-no").addEventListener("click", () => {
    gotoBox.hidden = true;
    if (gotoTarget && gotoTarget.opener) gotoTarget.opener.focus();
  });

  $("finder-goto-yes").addEventListener("click", () => {
    if (!gotoTarget) return;
    const target = gotoTarget;
    gotoBox.hidden = true;
    dialog.close();
    // カメラ中なら止めて、地図 (①さがす) にもどってからスポットを表示する (camera.js)
    document.dispatchEvent(new CustomEvent("mikke:go-map"));
    document.dispatchEvent(new CustomEvent("mikke:focus-spot", {
      detail: { id: target.id, name: target.name, lat: target.lat, lng: target.lng, item: target.item,
                symbol: target.symbol || null },
    }));
  });


  // ---------- レア度の右の「こんな人も獲得しているよ」(同じアイテムを直近に手に入れた人) ----------
  const alsoSection = $("reward-also");
  const alsoList = $("reward-also-list");
  const hero = $("reward-hero");

  function renderAlso(list) {
    if (!alsoSection) return;
    alsoList.replaceChildren();
    alsoSection.hidden = !list.length;
    if (hero) hero.classList.toggle("has-also", list.length > 0);
    for (const f of list) {
      const li = el("li");
      const b = el("button", "also-chip");
      b.type = "button";
      const img = el("img");
      img.src = finderUrl(f.token, "avatar.svg");
      img.alt = "";
      img.width = 40;
      img.height = 60;
      img.loading = "lazy";
      b.append(img, el("span", "also-chip-name", f.nickname), el("span", "also-chip-ago", f.ago));
      b.setAttribute("aria-label", `${f.nickname}さん(${f.ago}に獲得)のコーデを見る`);
      b.addEventListener("click", () => openFinder(f, b));
      li.appendChild(b);
      alsoList.appendChild(li);
    }
  }

  document.addEventListener("mikke:reward-shown", (ev) => {
    renderAlso(ev.detail.item_finders || []);
    renderFinders(ev.detail.recent_finders || []);
    showFinderView(false);
  });
})();
