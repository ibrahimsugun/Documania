/* Kullanıcılar sayfası "Bağlantıyı kopyala" (PRD 12.1.4): `data-copy-target` taşıyan düğme, adı
 * verilen alanın değerini panoya yazar. Pano API'si yalnız güvenli bağlamda (https, localhost)
 * vardır; yoksa alan seçilip tarayıcının kopyalama komutu kullanılır. JavaScript kapalıyken alan
 * seçilip elle kopyalanır. "Kopyalandı" metni düğmenin `data-copied-text` özniteliğinden, isteğin
 * dilinde gelir (PLAN.md §D92 j): bu dosyada görünen dizge yoktur. */
(function () {
  "use strict";

  function copied(button) {
    var text = button.getAttribute("data-copied-text");
    if (text) {
      button.textContent = text;
    }
  }

  function fallback(field, button) {
    field.focus();
    field.select();
    if (document.execCommand && document.execCommand("copy")) {
      copied(button);
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-target]");
    if (!button) {
      return;
    }
    var field = document.getElementById(button.getAttribute("data-copy-target"));
    if (!field) {
      return;
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(field.value).then(
        function () {
          copied(button);
        },
        function () {
          fallback(field, button);
        }
      );
    } else {
      fallback(field, button);
    }
  });
})();
