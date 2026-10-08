// Documania açık/koyu tema düğmesi (PRD 10.1.7; PLAN.md §D111).
// Seçim tarayıcıda (localStorage) hatırlanır; ilk açılışta sistem tercihi kullanılır.
// Başlangıçtaki yanıp sönmeyi önleyen satır base.html'deki satır içi betiktedir.
(function () {
  "use strict";
  var KEY = "documania-theme";

  function current() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    apply(current());
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].addEventListener("click", function () {
        var next = current() === "dark" ? "light" : "dark";
        apply(next);
        try { localStorage.setItem(KEY, next); } catch (error) { /* gizli pencere */ }
      });
    }
  });
})();
