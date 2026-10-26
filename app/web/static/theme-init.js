// İlk boyamadan önce açık/koyu temayı (PRD 10.1.7; PLAN.md §D111) ve büyük yazı seçimini
// (PRD 10.1.12) uygular. Engelleyici yüklenir.
try {
  var saved = localStorage.getItem("documania-theme");
  var dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-theme", saved || (dark ? "dark" : "light"));
  if (localStorage.getItem("documania-text") === "large") {
    document.documentElement.setAttribute("data-text", "large");
  }
} catch (error) { /* gizli pencere: varsayılan açık tema, normal yazı */ }
