/*
 * data-confirm 付きフォームの確認ダイアログと二重送信防止。
 * ブラウザ標準の confirm() ではなく <dialog> を使う (誤タップしにくい大きなボタン・見た目をそろえる・
 * 自動操作で勝手に OK されない)。<dialog> が使えない古いブラウザでは confirm() にもどす。
 */
(() => {
  "use strict";
  const forms = document.querySelectorAll("form[data-confirm]");
  if (!forms.length) return;

  let dialog = null;
  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "confirm-dialog";
    dialog.setAttribute("aria-labelledby", "confirm-dialog-msg");
    const msg = document.createElement("p");
    msg.id = "confirm-dialog-msg";
    msg.className = "confirm-dialog-msg";
    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    const ok = document.createElement("button");
    ok.type = "button";
    ok.className = "btn btn-primary";
    ok.dataset.role = "ok";
    ok.textContent = "はい";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn-ghost";
    cancel.dataset.role = "cancel";
    cancel.textContent = "やめる";
    actions.append(cancel, ok);
    dialog.append(msg, actions);
    document.body.appendChild(dialog);
    return dialog;
  }

  function ask(message, okLabel) {
    if (typeof HTMLDialogElement !== "function") return Promise.resolve(window.confirm(message));
    const d = ensureDialog();
    d.querySelector("#confirm-dialog-msg").textContent = message;
    d.querySelector("[data-role=ok]").textContent = okLabel || "はい";
    return new Promise((resolve) => {
      const done = (answer) => {
        d.removeEventListener("cancel", onCancel);
        d.querySelector("[data-role=ok]").onclick = null;
        d.querySelector("[data-role=cancel]").onclick = null;
        d.close();
        resolve(answer);
      };
      const onCancel = (ev) => { ev.preventDefault(); done(false); };
      d.addEventListener("cancel", onCancel);
      d.querySelector("[data-role=ok]").onclick = () => done(true);
      d.querySelector("[data-role=cancel]").onclick = () => done(false);
      d.showModal();
      d.querySelector("[data-role=cancel]").focus(); // 取り消せない操作なので、既定は「やめる」
    });
  }

  forms.forEach((form) => {
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const submitter = ev.submitter;
      const opener = submitter || document.activeElement;
      if (!(await ask(form.dataset.confirm, form.dataset.confirmOk))) {
        if (opener && opener.focus) opener.focus();
        return;
      }
      // 押したボタンの name / value (例: action=delete) を送信に含める (form.submit() では送られないため)
      if (submitter && submitter.name) {
        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = submitter.name;
        hidden.value = submitter.value;
        form.appendChild(hidden);
      }
      form.querySelectorAll("button[type=submit]").forEach((b) => { b.disabled = true; });
      HTMLFormElement.prototype.submit.call(form);
    });
  });
})();
