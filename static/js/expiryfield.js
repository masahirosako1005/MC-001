/* 「無期限にする」にチェックがあるときは、有効期限の入力欄を隠す (クーポン登録など) */
(() => {
  "use strict";
  const noExpiry = document.getElementById("id_no_expiry");
  const field = document.getElementById("expires-field");
  if (!noExpiry || !field) return;
  const sync = () => { field.hidden = noExpiry.checked; };
  noExpiry.addEventListener("change", sync);
  sync();
})();
