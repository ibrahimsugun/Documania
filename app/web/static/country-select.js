/* Belge Türleri ülke süzgeci (PRD 11.1.7). Yerleşik `<select>` seçeneğinde görüntü olamadığı için
 * bu betik `data-country-select` taşıyan `<select>`'i bayraklı bir listeye çevirir: düğme + yazarak
 * süzme + `role=listbox`. Sunucunun yazdığı `<select>` formda gizli kalır; seçim onun değerine
 * yazılır ve form gönderilir, süzme kuralı sunucudadır (11.1.5). JavaScript kapalıyken düz
 * `<select>` ve "Uygula" düğmesi çalışır (catalog.html). Görünen metinler sunucudan isteğin dilinde
 * gelir (`<select>`'in `data-search-label`, `data-search-placeholder`, `data-empty-text`
 * öznitelikleri; PLAN.md §D92 j): bu dosyada görünen dizge yoktur. */
(function () {
  "use strict";

  var counter = 0;

  // Arama harf büyüklüğüne ve işarete bakmaz, dilden bağımsızdır (§D92 i): Türkçe ı/İ/ş/ğ/ç/ö/ü ve
  // Sırpça č/ć/š/ž işaretsiz harfle eşleşir; NFD'de ayrışmayan đ hem "d" hem "dj" ile bulunur.
  // "turkiye" Türkiye'yi, "sirb" Sırbistan'ı, "cesk" Češka'yı, "djibuti" ve "dibuti" Đibuti'yi bulur.
  function fold(text, dj) {
    return text
      .toLocaleLowerCase("tr")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/ı/g, "i")
      .replace(/đ/g, dj ? "dj" : "d");
  }

  // Aranacak biçimler: đ'nin iki okunuşu.
  function searchable(text) {
    return [fold(text, false), fold(text, true)];
  }

  function matches(texts, query) {
    var folded = fold(query.trim(), false);
    return (
      folded === "" ||
      texts.some(function (text) {
        return text.indexOf(folded) !== -1;
      })
    );
  }

  // Tarayıcı dışında (node birim testi) arama kuralı denetlenebilsin diye dışarı açılır.
  globalThis.documaniaCountrySearch = { fold: fold, searchable: searchable, matches: matches };

  // Seçeneğin görünümü: bayrak (varsa) + etiket. Metin `textContent` ile yazılır, HTML olarak değil.
  function fill(target, option) {
    target.textContent = "";
    var flag = option.getAttribute("data-flag");
    if (flag) {
      var img = document.createElement("img");
      img.src = flag;
      img.alt = "";
      img.width = 20;
      img.height = 15;
      target.appendChild(img);
    }
    var text = document.createElement("span");
    text.textContent = option.textContent;
    target.appendChild(text);
  }

  function enhance(select) {
    var form = select.form;
    if (!form || !select.options.length) {
      return;
    }
    counter += 1;
    var id = "country-select-" + counter;
    var label = select.id ? form.querySelector('label[for="' + select.id + '"]') : null;

    var wrapper = document.createElement("div");
    wrapper.className = "country-select";

    var button = document.createElement("button");
    button.type = "button";
    button.id = id + "-button";
    button.className = "country-select-button";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    var current = document.createElement("span");
    current.id = id + "-current";
    current.className = "country";
    button.appendChild(current);
    if (label) {
      label.id = label.id || id + "-label";
      label.htmlFor = button.id;
      button.setAttribute("aria-labelledby", label.id + " " + current.id);
    }

    var popup = document.createElement("div");
    popup.className = "country-select-popup";
    popup.hidden = true;

    var search = document.createElement("input");
    search.type = "search";
    search.className = "country-select-search";
    search.placeholder = select.getAttribute("data-search-placeholder") || "";
    search.autocomplete = "off";
    search.setAttribute("role", "combobox");
    search.setAttribute("aria-label", select.getAttribute("data-search-label") || "");
    search.setAttribute("aria-autocomplete", "list");
    search.setAttribute("aria-expanded", "true");
    search.setAttribute("aria-controls", id + "-list");

    var list = document.createElement("ul");
    list.id = id + "-list";
    list.className = "country-select-list";
    list.setAttribute("role", "listbox");
    list.setAttribute(
      "aria-label",
      label ? label.textContent : select.getAttribute("data-search-label") || ""
    );

    var empty = document.createElement("p");
    empty.className = "country-select-empty";
    empty.textContent = select.getAttribute("data-empty-text") || "";
    empty.hidden = true;

    var items = Array.prototype.map.call(select.options, function (option, index) {
      var node = document.createElement("li");
      node.id = id + "-option-" + index;
      node.className = "country-select-option";
      node.setAttribute("role", "option");
      node.setAttribute("aria-selected", option.selected ? "true" : "false");
      fill(node, option);
      list.appendChild(node);
      return {
        node: node,
        option: option,
        texts: searchable(option.textContent + " " + option.value),
      };
    });
    var active = null;

    function selectedItem() {
      return items[select.selectedIndex] || items[0];
    }

    function visibleItems() {
      return items.filter(function (item) {
        return !item.node.hidden;
      });
    }

    function setActive(item) {
      if (active) {
        active.node.classList.remove("is-active");
      }
      active = item;
      if (item) {
        item.node.classList.add("is-active");
        search.setAttribute("aria-activedescendant", item.node.id);
        item.node.scrollIntoView({ block: "nearest" });
      } else {
        search.removeAttribute("aria-activedescendant");
      }
    }

    function applyFilter() {
      items.forEach(function (item) {
        item.node.hidden = !matches(item.texts, search.value);
      });
      var visible = visibleItems();
      empty.hidden = visible.length > 0;
      if (!active || active.node.hidden) {
        setActive(visible[0] || null);
      }
    }

    function open() {
      popup.hidden = false;
      button.setAttribute("aria-expanded", "true");
      search.value = "";
      applyFilter();
      setActive(selectedItem());
      search.focus();
    }

    function close(returnFocus) {
      if (popup.hidden) {
        return;
      }
      popup.hidden = true;
      button.setAttribute("aria-expanded", "false");
      if (returnFocus) {
        button.focus();
      }
    }

    function move(step) {
      var visible = visibleItems();
      if (!visible.length) {
        return;
      }
      var position = visible.indexOf(active) + step;
      setActive(visible[Math.max(0, Math.min(visible.length - 1, position))]);
    }

    function choose(item) {
      if (item.option.value === select.value) {
        close(true);
        return;
      }
      select.value = item.option.value;
      fill(current, item.option);
      close(false);
      form.submit();
    }

    button.addEventListener("click", function () {
      if (popup.hidden) {
        open();
      } else {
        close(true);
      }
    });
    button.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        open();
      }
    });
    search.addEventListener("input", applyFilter);
    search.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        move(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        move(-1);
      } else if (event.key === "Enter") {
        // Arama kutusunda Enter formu eski seçimle göndermesin; etkin satır seçilir.
        event.preventDefault();
        if (active) {
          choose(active);
        }
      } else if (event.key === "Escape") {
        event.preventDefault();
        close(true);
      }
    });
    // Satıra tıklamak odağı arama kutusundan almaz; seçim `click`'te yapılır.
    list.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });
    list.addEventListener("click", function (event) {
      var node = event.target.closest(".country-select-option");
      var item = items.filter(function (candidate) {
        return candidate.node === node;
      })[0];
      if (item) {
        choose(item);
      }
    });
    // Odak bileşenin dışına çıkınca (Tab, dışarıya tıklama) liste kapanır.
    wrapper.addEventListener("focusout", function (event) {
      if (!wrapper.contains(event.relatedTarget)) {
        close(false);
      }
    });

    fill(current, selectedItem().option);
    popup.appendChild(search);
    popup.appendChild(list);
    popup.appendChild(empty);
    wrapper.appendChild(button);
    wrapper.appendChild(popup);
    select.parentNode.insertBefore(wrapper, select.nextSibling);
    select.hidden = true;
  }

  if (typeof document !== "undefined") {
    Array.prototype.forEach.call(document.querySelectorAll("select[data-country-select]"), enhance);
  }
})();
