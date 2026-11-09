/*
 * 着せ替え画面
 * - 選択を変えるとプレビュー画像を更新する (保存はボタンで)
 * - 体のタイプに合うパーツだけを表示する (管理者は「ほかのタイプも表示」で全パーツ)
 */
(() => {
  "use strict";
  const form = document.getElementById("wardrobe-form");
  const img = document.getElementById("avatar-preview");
  if (!form || !img) return;
  const showAll = document.getElementById("show-all-types");
  let timer = 0;

  function bodyType() {
    const r = form.querySelector('input[name="body_type"]:checked');
    return r ? r.value : "girl";
  }

  function applyFilter() {
    const bt = bodyType();
    const all = showAll && showAll.checked;
    form.querySelectorAll("[data-body]").forEach((el) => {
      const b = el.dataset.body;
      const locked = el.dataset.locked === "1";
      // 未発見の枠は選んだタイプのものだけ。パーツは「共通」か選んだタイプ (管理者の全表示なら全部)
      el.hidden = locked ? b !== bt : !(all || b === "any" || b === bt);
    });
    // 隠れたパーツが選ばれていたら「なし」に戻す
    form.querySelectorAll(".item-grid").forEach((grid) => {
      const checked = grid.querySelector("input[type=radio]:checked");
      if (checked && checked.closest("[data-body]") && checked.closest("[data-body]").hidden) {
        const none = grid.querySelector('input[value="none"]');
        if (none) none.checked = true;
      }
    });
  }

  function updatePreview() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const params = new URLSearchParams();
      for (const [k, v] of new FormData(form)) {
        if (k !== "csrfmiddlewaretoken" && k !== "version") params.append(k, v);
      }
      img.src = `${form.dataset.previewUrl}?${params.toString()}`;
      img.alt = "選択中の服装のプレビュー(まだ保存されていません)";
    }, 120);
  }

  form.addEventListener("change", (ev) => {
    if (ev.target.name === "body_type" || ev.target === showAll) applyFilter();
    updatePreview();
  });
  applyFilter();
})();
