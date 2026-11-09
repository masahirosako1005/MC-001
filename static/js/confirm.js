/* data-confirm 付きフォームの確認ダイアログと二重送信防止 */
(() => {
  "use strict";
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (ev) => {
      if (!window.confirm(form.dataset.confirm)) {
        ev.preventDefault();
        return;
      }
      form.querySelectorAll("button[type=submit]").forEach((b) => { b.disabled = true; });
    });
  });
})();
