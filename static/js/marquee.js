/*
 * ログイン画面の「いま、まちで手に入るコーデ・ランキング」を右から左へ流す表示の一時停止ボタン。
 * 動きは CSS (mikke.css の .marquee)。動く表示は止められるようにする (WCAG 2.2.2)。
 * 動きを減らす設定の人には最初から流さない (CSS 側で横スクロールにする) ので、ボタンも出さない。
 */
(() => {
  "use strict";
  const marquee = document.getElementById("marquee");
  const button = document.getElementById("marquee-toggle");
  if (!marquee || !button) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  button.hidden = false;
  button.addEventListener("click", () => {
    const paused = marquee.classList.toggle("is-paused");
    button.setAttribute("aria-pressed", String(paused));
    button.textContent = paused ? "再生" : "一時停止";
  });
})();
