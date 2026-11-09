/* 着せ替え画面: 選択を変えるとプレビュー画像を更新する (保存はボタンで) */
(() => {
  "use strict";
  const form = document.getElementById("wardrobe-form");
  const img = document.getElementById("avatar-preview");
  if (!form || !img) return;
  let timer = 0;
  form.addEventListener("change", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const params = new URLSearchParams();
      for (const [k, v] of new FormData(form)) {
        if (k !== "csrfmiddlewaretoken" && k !== "version") params.append(k, v);
      }
      img.src = `${form.dataset.previewUrl}?${params.toString()}`;
      img.alt = "選択中の服装のプレビュー(まだ保存されていません)";
    }, 120);
  });
})();
