/*
 * みっけ 結果ダイアログ: 受け取ったもの (コーデ・クーポン) を絵で見せる。
 * camera.js が受け取りに成功すると mikke:reward イベント (detail = 受け取り結果) を出すので、それを表示する。
 */
(() => {
  "use strict";
  const root = document.getElementById("ar");
  const dialog = document.getElementById("reward-dialog");
  if (!root || !dialog) return;
  const $ = (id) => document.getElementById(id);

  // ---------- 結果ダイアログ ----------
  function showReward(d) {
    const title = $("reward-title");
    const spot = $("reward-spot");
    const art = $("reward-art");
    const img = $("reward-img");
    const badgeNew = $("reward-new");
    const rarity = $("reward-rarity");
    const text = $("reward-text");
    const extra = $("reward-extra");
    const list = $("reward-achievements");
    const link = $("reward-link");
    const itemImg = (code) => `${root.dataset.itemSvgBase}${encodeURIComponent(code)}.svg`;
    const couponImg = (id) => `${root.dataset.couponBase}${encodeURIComponent(id)}.svg`;
    // 手に入れた物の絵を出す (読み込めなかったときは絵の枠ごと隠し、文字だけで伝える)
    const zoom = $("reward-zoom");
    // 小さなパーツ (くつ・顔など) は、全身の絵に虫めがね風の拡大図を重ねて、何を手に入れたか分かるようにする
    const ZOOMABLE = new Set(["shoes", "bottom", "top", "hair", "face"]);
    function showZoom(code) {
      zoom.onerror = () => { zoom.hidden = true; };
      zoom.src = `${itemImg(code)}?zoom=1`;
      zoom.hidden = false;
    }
    function showArt(src, alt, kind, w, h) {
      zoom.hidden = true;
      art.className = `reward-art is-${kind}`;
      img.onerror = () => { art.hidden = true; };
      img.width = w;
      img.height = h;
      img.alt = alt;
      img.src = src;
      art.hidden = false;
    }

    spot.textContent = d.symbol ? `${d.symbol.spot} ・ ${d.symbol.name}` : "";
    art.hidden = true;
    badgeNew.hidden = true;
    rarity.textContent = "";
    link.hidden = false;
    list.replaceChildren();
    const notes = [];
    if (d.visit_days > 1 && d.is_revisit_day) notes.push(`このスポット ${d.visit_days} 日目の訪問!再訪限定のごほうびが出やすくなっています。`);

    if (d.reward_kind === "item" && d.item) {
      title.textContent = d.item.new ? "NEW!みっけ!" : "みっけ!";
      showArt(itemImg(d.item.code), `手に入れたアイテム: ${d.item.name}${d.item.new ? "" : "(取得済み)"}`, "item", 180, 242);
      if (ZOOMABLE.has(d.item.slot)) showZoom(d.item.code);
      // 初めてなら「NEW」、もう持っているコーデなら「取得済み」
      badgeNew.hidden = false;
      badgeNew.textContent = d.item.new ? "NEW" : "取得済み";
      badgeNew.classList.toggle("is-owned", !d.item.new);
      if (d.item.rarity) rarity.textContent = "★".repeat(d.item.rarity);
      text.textContent = `${d.item.name} を手に入れた!`;
      // 星の記号だけでは読み上げで伝わらないので「レア度 3/5」も書く
      if (d.item.rarity) notes.unshift(`${d.item.category || ""} レア度 ${d.item.rarity}/5 ${"★".repeat(d.item.rarity)}${"☆".repeat(5 - d.item.rarity)}`);
      if (!d.item.new) notes.push("取得済みのコーデです(コレクション回数が増えました)。");
      link.textContent = "着せかえる";
      link.href = root.dataset.wardrobeUrl;
    } else if (d.reward_kind === "coupon" && d.coupon) {
      title.textContent = "クーポンをみっけ!";
      showArt(couponImg(d.coupon.id), `手に入れたクーポン: ${d.coupon.shop || ""}「${d.coupon.title}」`, "coupon", 288, 180);
      badgeNew.hidden = false;
      badgeNew.textContent = "NEW";
      badgeNew.classList.remove("is-owned");
      text.textContent = `${d.coupon.shop || ""}「${d.coupon.title}」`;
      if (d.coupon.benefit) notes.unshift(d.coupon.benefit);
      link.textContent = "クーポンを見る";
      link.href = `${root.dataset.couponBase}${encodeURIComponent(d.coupon.id)}/`;
    } else {
      // ふつうは必ずコーデが出る (衣装全振り)。アイテムが 1 つも登録されていない場合だけここに来る
      title.textContent = "みっけ!";
      text.textContent = "シンボルをみっけしました。";
      link.hidden = true;
    }
    extra.textContent = notes.join(" ");
    // 実績のごほうびも、絵つきで並べる
    for (const a of d.achievements || []) {
      const li = document.createElement("li");
      const head = document.createElement("span");
      head.textContent = `${a.icon} 実績「${a.name}」達成!`;
      li.appendChild(head);
      const gifts = [];
      if (a.item) gifts.push({ src: itemImg(a.item.code), label: `アイテム「${a.item.name}」`, cls: "is-item" });
      if (a.coupon) gifts.push({ src: couponImg(a.coupon.id), label: `クーポン「${a.coupon.title}」`, cls: "is-coupon" });
      for (const g of gifts) {
        const fig = document.createElement("span");
        fig.className = `reward-gift ${g.cls}`;
        const gi = document.createElement("img");
        gi.src = g.src;
        gi.alt = "";
        gi.onerror = () => gi.remove();
        const cap = document.createElement("span");
        cap.textContent = `${g.label} も手に入れた!`;
        fig.append(gi, cap);
        li.appendChild(fig);
      }
      list.appendChild(li);
    }
    // 「こんな人が獲得しているよ」(finders.js) に結果を渡す
    document.dispatchEvent(new CustomEvent("mikke:reward-shown", { detail: d }));
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  $("reward-close").addEventListener("click", () => dialog.close());


  document.addEventListener("mikke:reward", (ev) => showReward(ev.detail));
})();
