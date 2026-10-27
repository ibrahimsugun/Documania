/* Önizleme ön yükleme (PRD 11.9.8; PLAN.md §D131). Önizlemeleri kullanıcı beklemeden, arka planda
 * ve düşük öncelikle tarayıcının HTTP önbelleğine indirir; sonraki `<img>` ve açma istekleri ağa
 * gitmez. Service worker ve Cache API kullanılmaz.
 *
 * - Aşama 1 (küçükler): sayfa yüklenip tarayıcı boşa düşünce `/previews/thumbs` listesinden bütün
 *   küçük önizlemeler iner; bitince `localStorage`'a yalnız liste sürümü yazılır ve aynı sürüm için
 *   bir daha başlamaz. Yarıda kalırsa sayısal imleç `sessionStorage`'da kalır.
 * - Aşama 2 (sayfa büyükleri): sayfadaki `[data-preview-large]` adresleri, görünüme yakın olan önce
 *   (`IntersectionObserver`), aşama 1'in önüne alınır.
 * - Aynı anda en çok 2 istek, aralarında ~150 ms; `fetch` `priority: "low"`. Kullanıcı tıklayınca,
 *   HTMX isteği başlayınca ya da sayfadan çıkınca bekleyen sıra ve etkin istekler iptal edilir
 *   (`AbortController`). Sekme gizliyken, veri tasarrufu açıkken ya da bağlantı `2g`/`slow-2g`
 *   iken çalışmaz. `429`/`503`'te `Retry-After` ile üstel geri çekilir (en çok 60 sn).
 * - Web depolamaya belge adı, çalışan ya da içerik yazılmaz; yalnız sürüm ve imleç. Orijinal dosya
 *   adresi hiç istenmez (liste yalnız önizleme adresi verir). Görünen dizge yoktur. */
(function () {
  "use strict";

  var LIST_URL = "/previews/thumbs";
  var VERSION_KEY = "previewWarm:v1";
  var CURSOR_KEY = "previewWarmCursor:v1";
  var PREFETCH_HEADER = "X-Preview-Prefetch";
  var WORKERS = 2;
  var GAP = 150;
  var IDLE_FALLBACK = 2000;
  var RESUME_DELAY = 3000;
  var MAX_BACKOFF = 60000;
  var MAX_LARGE = 100;

  var large = [];
  var small = [];
  var seen = {};
  var listState = { version: null, next: 0, done: false, loading: false };
  var controller = null;
  var running = 0;
  var paused = true;
  var leaving = false;
  var waitUntil = 0;
  var backoff = 1000;
  var resumeTimer = null;

  function storage(kind) {
    try {
      return window[kind];
    } catch (error) {
      return null;
    }
  }

  function read(kind, key) {
    var store = storage(kind);
    try {
      return store ? store.getItem(key) : null;
    } catch (error) {
      return null;
    }
  }

  function write(kind, key, value) {
    var store = storage(kind);
    try {
      if (!store) {
        return;
      }
      if (value === null) {
        store.removeItem(key);
      } else {
        store.setItem(key, value);
      }
    } catch (error) {
      /* depolama kapalı ya da dolu: ön yükleme yine çalışır, yalnız hatırlamaz */
    }
  }

  function allowed() {
    if (document.hidden || leaving) {
      return false;
    }
    var connection = navigator.connection;
    if (connection) {
      if (connection.saveData) {
        return false;
      }
      if (connection.effectiveType === "2g" || connection.effectiveType === "slow-2g") {
        return false;
      }
    }
    return true;
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function retryAfter(response) {
    var value = parseInt(response.headers.get("Retry-After") || "", 10);
    var asked = isNaN(value) ? 0 : value * 1000;
    var delay = Math.min(MAX_BACKOFF, Math.max(asked, backoff));
    backoff = Math.min(MAX_BACKOFF, backoff * 2);
    waitUntil = Date.now() + delay;
  }

  function request(url) {
    var headers = {};
    headers[PREFETCH_HEADER] = "1";
    return fetch(url, {
      credentials: "same-origin",
      priority: "low",
      headers: headers,
      signal: controller ? controller.signal : undefined
    });
  }

  // --- aşama 1: liste -------------------------------------------------------------------------
  function loadList() {
    if (listState.done || listState.loading || listState.next === null) {
      return Promise.resolve();
    }
    listState.loading = true;
    var url = LIST_URL + "?after=" + listState.next;
    return fetch(url, {
      credentials: "same-origin",
      priority: "low",
      headers: { "Accept": "application/json" },
      signal: controller ? controller.signal : undefined
    })
      .then(function (response) {
        if (response.status === 429 || response.status === 503) {
          retryAfter(response);
          return null;
        }
        if (!response.ok) {
          listState.done = true;
          return null;
        }
        return response.json();
      })
      .then(function (data) {
        if (!data) {
          return;
        }
        backoff = 1000;
        if (listState.version === null) {
          listState.version = data.version;
          if (read("localStorage", VERSION_KEY) === data.version) {
            listState.done = true; // bu sürüm zaten ısıtıldı
            return;
          }
        } else if (data.version !== listState.version) {
          listState.version = data.version; // liste değişti: baştan, önbellekteki ağa gitmez
          listState.next = 0;
          return;
        }
        data.items.forEach(function (item) {
          if (!seen[item]) {
            small.push(item);
          }
        });
        listState.next = data.next;
        write("sessionStorage", CURSOR_KEY, data.next === null ? null : data.version + ":" + data.next);
      })
      .catch(function () {
        /* iptal ya da ağ hatası: imleç yerinde kalır */
      })
      .then(function () {
        listState.loading = false;
      });
  }

  function listFinished() {
    return listState.done || (listState.next === null && small.length === 0);
  }

  function markWarm() {
    if (!listState.done && listState.next === null && listState.version !== null) {
      write("localStorage", VERSION_KEY, listState.version);
      write("sessionStorage", CURSOR_KEY, null);
      listState.done = true;
    }
  }

  // --- işçiler ----------------------------------------------------------------------------------
  // Sıradaki adres ve geldiği sıra (başarısız olursa aynı sıranın başına döner).
  function nextItem() {
    var queues = [large, small];
    for (var index = 0; index < queues.length; index += 1) {
      while (queues[index].length) {
        var url = queues[index].shift();
        if (!seen[url]) {
          return { url: url, queue: queues[index] };
        }
      }
    }
    return null;
  }

  function work() {
    if (paused || !allowed()) {
      return Promise.resolve();
    }
    var delay = waitUntil - Date.now();
    if (delay > 0) {
      return wait(delay).then(work);
    }
    var item = nextItem();
    if (item === null) {
      if (listFinished()) {
        markWarm();
        return Promise.resolve();
      }
      return loadList().then(function () {
        return wait(GAP);
      }).then(work);
    }
    var url = item.url;
    seen[url] = true;
    function again() {
      seen[url] = false;
      item.queue.unshift(url);
    }
    return request(url)
      .then(function (response) {
        if (response.status === 429 || response.status === 503) {
          again();
          retryAfter(response);
          return null;
        }
        backoff = 1000;
        // Gövde okunur ki önbelleğe tam yazılsın.
        return response.ok ? response.arrayBuffer() : null;
      })
      .catch(again)
      .then(function () {
        return wait(GAP);
      })
      .then(work);
  }

  function start() {
    if (!paused || leaving || !allowed()) {
      return;
    }
    paused = false;
    controller = typeof AbortController === "function" ? new AbortController() : null;
    for (var index = running; index < WORKERS; index += 1) {
      running += 1;
      work().then(function () {
        running -= 1;
      });
    }
  }

  // Kullanıcının kendi isteği önceliklidir: bekleyen sıra ve etkin ön yükleme istekleri iptal.
  function stop(resume) {
    paused = true;
    if (controller) {
      controller.abort();
      controller = null;
    }
    if (resumeTimer !== null) {
      window.clearTimeout(resumeTimer);
      resumeTimer = null;
    }
    if (resume && !leaving) {
      resumeTimer = window.setTimeout(function () {
        resumeTimer = null;
        idle(start);
      }, RESUME_DELAY);
    }
  }

  function idle(callback) {
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(callback, { timeout: IDLE_FALLBACK * 5 });
    } else {
      window.setTimeout(callback, IDLE_FALLBACK);
    }
  }

  // --- aşama 2: sayfa büyükleri -----------------------------------------------------------------
  function distance(element) {
    var rect = element.getBoundingClientRect();
    var height = window.innerHeight || document.documentElement.clientHeight;
    if (rect.bottom < 0) {
      return -rect.bottom;
    }
    return rect.top > height ? rect.top - height : 0;
  }

  function collectLarge() {
    var elements = Array.prototype.slice.call(document.querySelectorAll("[data-preview-large]"));
    elements.sort(function (a, b) {
      return distance(a) - distance(b);
    });
    elements.slice(0, MAX_LARGE).forEach(function (element) {
      var url = element.getAttribute("data-preview-large");
      if (url && url.charAt(0) === "/" && url.charAt(1) !== "/" && large.indexOf(url) < 0) {
        large.push(url);
      }
    });
    if (typeof IntersectionObserver !== "function") {
      return;
    }
    // Görünüme yaklaşan belgenin büyüğü sıranın başına geçer.
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) {
            return;
          }
          var url = entry.target.getAttribute("data-preview-large");
          var at = large.indexOf(url);
          if (at > 0) {
            large.splice(at, 1);
            large.unshift(url);
          }
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "400px 0px" }
    );
    elements.forEach(function (element) {
      observer.observe(element);
    });
  }

  function resumeCursor() {
    var saved = read("sessionStorage", CURSOR_KEY);
    var match = saved ? /^([0-9a-f]+):([0-9]+)$/.exec(saved) : null;
    if (match) {
      listState.version = match[1];
      listState.next = parseInt(match[2], 10);
    }
  }

  function boot() {
    if (!window.fetch || !window.Promise) {
      return;
    }
    resumeCursor();
    collectLarge();
    document.addEventListener("pointerdown", function () {
      stop(true);
    }, true);
    document.addEventListener("htmx:beforeRequest", function () {
      stop(true);
    });
    document.addEventListener("htmx:afterSettle", function () {
      collectLarge();
    });
    window.addEventListener("pagehide", function () {
      leaving = true;
      stop(false);
    });
    window.addEventListener("pageshow", function (event) {
      if (event.persisted) {
        leaving = false;
        idle(start);
      }
    });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        stop(false);
      } else {
        idle(start);
      }
    });
    idle(start);
  }

  if (document.readyState === "complete") {
    boot();
  } else {
    window.addEventListener("load", boot);
  }
}());
