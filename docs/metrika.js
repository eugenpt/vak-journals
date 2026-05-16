/**
 * Optional Yandex Metrika (loads only when site-config.js sets metrikaId).
 */
(function () {
  "use strict";

  const id = window.VAK_SITE && window.VAK_SITE.metrikaId;
  if (!id) return;

  const counter = String(id).trim();
  if (!/^\d+$/.test(counter)) {
    console.warn("VAK: invalid metrikaId, expected digits");
    return;
  }

  (function (m, e, t, r, i, k, a) {
    m[i] =
      m[i] ||
      function () {
        (m[i].a = m[i].a || []).push(arguments);
      };
    m[i].l = 1 * new Date();
    for (let j = 0; j < document.scripts.length; j++) {
      if (document.scripts[j].src === r) return;
    }
    k = e.createElement(t);
    a = e.getElementsByTagName(t)[0];
    k.async = 1;
    k.src = r;
    a.parentNode.insertBefore(k, a);
  })(window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

  window.ym(counter, "init", {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: false,
  });

  document.body.dataset.metrika = counter;
})();
