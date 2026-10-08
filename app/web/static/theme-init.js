// İlk boyamadan önce açık/koyu temayı uygular (PRD 10.1.7; PLAN.md §D111). Engelleyici yüklenir.
try {
  var saved = localStorage.getItem("documania-theme");
  var dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-theme", saved || (dark ? "dark" : "light"));
} catch (error) { /* gizli pencere: varsayılan açık tema */ }
