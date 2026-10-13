/* Geçici bildirim (PRD 10.11.1; PLAN.md §D120 c). Sunucunun `base.html`'deki `.toasts` alanına
 * bastığı bildirimleri ve HTMX yanıtlarının `HX-Trigger: {"documania:toast": {"toasts": [...]}}`
 * olaylarını aynı görünüme bağlar: başarı ve bilgi 5 saniyede kapanır (fare ya da odak üstündeyken
 * süre durur), uyarı ve hata kullanıcı kapatana dek kalır; en fazla 3 bildirim üst üste durur, en
 * eskisi düşer; her bildirimin kapatma düğmesi vardır. Görünen metinler sunucudan isteğin dilinde
 * gelir (kapatma etiketi `.toasts`'ın `data-close-label` özniteliği; PLAN.md §D92 j): bu dosyada
 * görünen dizge yoktur. Metin `textContent` ile yazılır, HTML olarak değil. */
(function () {
  "use strict";

  var LIMIT = 3;
  var DELAY = 5000;
  var KINDS = ["success", "info", "warning", "error"];

  function region() {
    return document.querySelector(".toasts");
  }

  function persistent(kind) {
    return kind === "warning" || kind === "error";
  }

  function close(toast) {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }

  // Kendiliğinden kapanma: kalan süre fare ya da klavye odağı bildirimin üstündeyken durur.
  function schedule(toast) {
    var remaining = DELAY;
    var started = 0;
    var timer = null;
    function start() {
      started = Date.now();
      timer = window.setTimeout(function () {
        close(toast);
      }, remaining);
    }
    function pause() {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
        remaining = Math.max(0, remaining - (Date.now() - started));
      }
    }
    toast.addEventListener("mouseenter", pause);
    toast.addEventListener("focusin", pause);
    toast.addEventListener("mouseleave", start);
    toast.addEventListener("focusout", start);
    start();
  }

  function enhance(toast, label) {
    if (toast.getAttribute("data-ready") === "1") {
      return;
    }
    toast.setAttribute("data-ready", "1");
    var button = document.createElement("button");
    button.type = "button";
    button.className = "toast-close";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.textContent = "×";
    button.addEventListener("click", function () {
      close(toast);
    });
    toast.appendChild(button);
    if (!persistent(toast.getAttribute("data-kind"))) {
      schedule(toast);
    }
  }

  function trim(container) {
    var items = container.querySelectorAll(".toast");
    for (var index = 0; index < items.length - LIMIT; index++) {
      close(items[index]);
    }
  }

  function show(kind, text) {
    var container = region();
    if (!container || !text) {
      return;
    }
    if (KINDS.indexOf(kind) === -1) {
      kind = "info";
    }
    var toast = document.createElement("div");
    toast.className = "toast toast-" + kind;
    toast.setAttribute("data-kind", kind);
    toast.setAttribute("role", persistent(kind) ? "alert" : "status");
    var icon = document.createElement("span");
    icon.className = "toast-icon";
    icon.setAttribute("aria-hidden", "true");
    var paragraph = document.createElement("p");
    paragraph.className = "toast-text";
    paragraph.textContent = text;
    toast.appendChild(icon);
    toast.appendChild(paragraph);
    container.appendChild(toast);
    enhance(toast, container.getAttribute("data-close-label") || "");
    trim(container);
  }

  function init() {
    var container = region();
    if (!container) {
      return;
    }
    var label = container.getAttribute("data-close-label") || "";
    var items = container.querySelectorAll(".toast");
    for (var index = 0; index < items.length; index++) {
      enhance(items[index], label);
    }
    trim(container);
  }

  // HTMX olayı `HX-Trigger` başlığından gelir; ayrıntı `{"toasts": [{"kind", "text"}]}`.
  document.addEventListener("documania:toast", function (event) {
    var toasts = (event.detail && event.detail.toasts) || [];
    for (var index = 0; index < toasts.length; index++) {
      show(toasts[index].kind, toasts[index].text);
    }
  });

  globalThis.documaniaToast = { show: show };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
