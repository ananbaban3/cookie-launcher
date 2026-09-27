/* Cookie / izin yonetici
 *
 * ONEMLI: Bu sitede su an HICBIR cerez, analitik, piksel, reklam kodu veya
 * ucuncu taraf izleme kodu yoktur. Bu dosya yalnizca:
 *   1) kullanicinin tercihini kaydetmek icin (localStorage, sunucuya GITMEZ),
 *   2) ileride bir izleme kodu eklendiginde onayi olmadan yuklenmesini engellemek
 *      icin bir "kapi" fonksiyonu sunar.
 *
 * Zorunlu olmayan herhangi bir izleme kodu eklenirse, ASAGIDAKI sekilde
 * kullanilmadan yuklenmemelidir:
 *
 *     <script>
 *       if (window.CookieConsent && CookieConsent.has('analytics')) {
 *         // ... analitik kodunu burada yukle ...
 *       }
 *     </script>
 */
(function () {
  'use strict';

  var KEY = 'cl_consent_v1';
  var DEFAULTS = { necessary: true, analytics: false, marketing: false, updated: null };
  var CATEGORIES = [
    { id: 'necessary', label: 'Zorunlu', locked: true,
      desc: 'Siteyi calistirmak icin gereklidir. Bu sitede zaten hicbir cerez kullanilmaz; bu kayit sadece tercihinizi hatirlamak icin tutulur.' },
    { id: 'analytics', label: 'Olcum / Analitik', locked: false,
      desc: 'Ziyaretci sayisi ve sayfa performansi gibi olculer. Su anda bu sitede analitik kodu YOKTUR; bu ayar ileride eklenecek olcumlere icindir.' },
    { id: 'marketing', label: 'Hedefleme / Reklam', locked: false,
      desc: 'Ilgi alaniniza gore reklam gosterimi. Su anda bu sitede reklam kodu YOKTUR ve reklam gosterilmez.' }
  ];

  function read() {
    try {
      var raw = window.localStorage.getItem(KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return null;
      return parsed;
    } catch (e) { return null; }
  }

  function write(prefs) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify({
        necessary: true,
        analytics: prefs.analytics === true,
        marketing: prefs.marketing === true,
        updated: new Date().toISOString(),
        version: 1
      }));
    } catch (e) { /* Gizli sekmede yazilamayabilir; sessizce gec. */ }
  }

  function clear() {
    try { window.localStorage.removeItem(KEY); } catch (e) {}
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  var panel = null;
  var banner = null;

  function buildBanner() {
    var wrap = el('div', 'fixed inset-x-0 bottom-0 z-[60] p-3 sm:p-4');
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Cerez tercihleri');

    var box = el('div', 'max-w-4xl mx-auto rounded-2xl border border-surface-border bg-surface-card/95 backdrop-blur-md shadow-2xl p-4 sm:p-5');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'false');
    box.setAttribute('aria-labelledby', 'consent-banner-title');
    box.setAttribute('aria-describedby', 'consent-banner-desc');

    var h = el('h2', 'text-sm sm:text-base font-bold text-white', 'Cerez ve benzeri teknolojiler');
    h.id = 'consent-banner-title';

    var p = el('p', 'text-xs sm:text-sm text-slate-400 leading-relaxed mt-2');
    p.id = 'consent-banner-desc';
    p.innerHTML = 'Bu site <strong class="text-slate-200">çerez kullanmaz</strong> ve hiçbir analitik, ' +
      'piksel veya reklam kodu yüklemez. Yalnızca bu tercihinizi hatırlamak için tarayıcınızın ' +
      '<code class="font-mono text-cookie-300">localStorage</code> alanına küçük bir kayıt yazılır; ' +
      'bu kayıt sunucuya gönderilmez.';

    var row = el('div', 'mt-4 flex flex-col sm:flex-row gap-2 sm:justify-end');
    var bManage = el('button', 'px-4 py-2 rounded-xl text-sm font-semibold border border-surface-border bg-surface-base text-slate-200 hover:border-cookie-500/50 hover:text-white transition-colors', 'Tercihlerimi yönet');
    bManage.type = 'button';
    bManage.addEventListener('click', function () { openPanel(); });
    var bOk = el('button', 'px-4 py-2 rounded-xl text-sm font-bold bg-cookie-500 hover:bg-cookie-400 text-slate-950 transition-colors', 'Anladım');
    bOk.type = 'button';
    bOk.addEventListener('click', function () { write({ analytics: false, marketing: false }); hideBanner(); });
    row.appendChild(bManage);
    row.appendChild(bOk);

    box.appendChild(h);
    box.appendChild(p);
    box.appendChild(row);
    wrap.appendChild(box);
    return wrap;
  }

  function buildPanel() {
    var wrap = el('div', 'fixed inset-0 z-[70] hidden items-center justify-center p-4 bg-black/70');
    var box = el('div', 'w-full max-w-xl rounded-2xl border border-surface-border bg-surface-card shadow-2xl p-5 sm:p-6 max-h-[85vh] overflow-y-auto');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', 'consent-panel-title');

    var h = el('h2', 'text-lg sm:text-xl font-extrabold text-white', 'Çerez tercihlerinizi yönetin');
    h.id = 'consent-panel-title';

    var intro = el('p', 'text-xs sm:text-sm text-slate-400 leading-relaxed mt-2',
      'Bu sitede şu anda hiçbir çerez veya benzeri teknoloji çalışmıyor. Aşağıdaki ayarlar, ileride ' +
      'eklenebilecek isteğe bağlı araçlar için saklanır. "Zorunlu" kategorisi kapatılamaz; ancak bu ' +
      'sitede zorunlu çerez de bulunmuyor.');

    var list = el('div', 'mt-5 space-y-3');
    var inputs = {};
    CATEGORIES.forEach(function (c) {
      var row = el('div', 'rounded-xl border border-surface-border bg-surface-base p-4');
      var head = el('div', 'flex items-center justify-between gap-3');
      var left = el('div', 'flex items-center gap-2.5');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.id = 'consent-' + c.id;
      cb.className = 'w-5 h-5 rounded border-surface-border bg-surface-card text-cookie-500 focus:ring-2 focus:ring-cookie-400 cursor-pointer';
      if (c.locked) { cb.checked = true; cb.disabled = true; }
      var lab = el('label', 'text-sm font-bold text-white', c.label);
      lab.setAttribute('for', cb.id);
      if (c.locked) { lab.appendChild(el('span', 'ml-2 text-[10px] font-mono uppercase text-cookie-300 border border-cookie-500/30 rounded px-1.5 py-0.5', 'hep açık')); }
      left.appendChild(cb);
      left.appendChild(lab);
      head.appendChild(left);
      var desc = el('p', 'text-xs text-slate-400 leading-relaxed mt-2', c.desc);
      row.appendChild(head);
      row.appendChild(desc);
      list.appendChild(row);
      inputs[c.id] = cb;
    });

    var note = el('p', 'text-[11px] text-slate-400 leading-relaxed mt-4',
      'Kaydınız yalnızca bu tarayıcıda saklanır ve sunucuya gönderilmez. Tarayıcı verilerinizi silerek ' +
      'kaydı istediğiniz anda kaldırabilirsiniz. Ayrıntılar: <a href="cerez-politikasi.html" class="text-cookie-400 underline underline-offset-2">Çerez Politikası</a>.');

    var row = el('div', 'mt-5 flex flex-col sm:flex-row gap-2 sm:justify-between');
    var leftBtns = el('div', 'flex flex-col sm:flex-row gap-2');
    var bReject = el('button', 'px-3.5 py-2 rounded-xl text-xs sm:text-sm font-semibold border border-surface-border bg-surface-base text-slate-300 hover:text-white transition-colors', 'Tümünü kapat');
    bReject.type = 'button';
    bReject.addEventListener('click', function () {
      write({ analytics: false, marketing: false });
      closePanel();
      hideBanner();
    });
    var bAccept = el('button', 'px-3.5 py-2 rounded-xl text-xs sm:text-sm font-semibold border border-surface-border bg-surface-base text-slate-300 hover:text-white transition-colors', 'Tümünü aç');
    bAccept.type = 'button';
    bAccept.addEventListener('click', function () {
      write({ analytics: true, marketing: true });
      closePanel();
      hideBanner();
    });
    leftBtns.appendChild(bReject);
    leftBtns.appendChild(bAccept);

    var bSave = el('button', 'px-5 py-2 rounded-xl text-sm font-bold bg-cookie-500 hover:bg-cookie-400 text-slate-950 transition-colors', 'Tercihlerimi kaydet');
    bSave.type = 'button';
    bSave.addEventListener('click', function () {
      write({
        analytics: inputs.analytics.checked,
        marketing: inputs.marketing.checked
      });
      closePanel();
      hideBanner();
    });

    row.appendChild(leftBtns);
    row.appendChild(bSave);

    box.appendChild(h);
    box.appendChild(intro);
    box.appendChild(list);
    box.appendChild(note);
    box.appendChild(row);
    wrap.appendChild(box);

    wrap.addEventListener('click', function (e) { if (e.target === wrap) closePanel(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !wrap.classList.contains('hidden')) closePanel();
    });

    return wrap;
  }

  function currentPrefs() {
    var stored = read();
    if (stored) return stored;
    return DEFAULTS;
  }

  function syncPanel() {
    var p = currentPrefs();
    document.getElementById('consent-necessary').checked = true;
    document.getElementById('consent-analytics').checked = p.analytics === true;
    document.getElementById('consent-marketing').checked = p.marketing === true;
  }

  function openPanel() {
    if (!panel) return;
    syncPanel();
    panel.classList.remove('hidden');
    panel.classList.add('flex');
    var first = document.getElementById('consent-analytics');
    if (first) first.focus();
  }

  function closePanel() {
    if (!panel) return;
    panel.classList.add('hidden');
    panel.classList.remove('flex');
  }

  function hideBanner() {
    if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
    banner = null;
  }

  function showBanner() {
    if (read()) return;
    if (banner || !document.body) return;
    banner = buildBanner();
    document.body.appendChild(banner);
  }

  // Genel API: baska kodlar tercihi okuyabilir.
  window.CookieConsent = {
    get: read,
    has: function (category) {
      var p = read();
      if (!p) return false;
      if (category === 'necessary') return true;
      return p[category] === true;
    },
    save: function (prefs) {
      write(prefs || {});
      hideBanner();
      return read();
    },
    reset: function () { clear(); },
    open: openPanel
  };

  function init() {
    panel = buildPanel();
    document.body.appendChild(panel);
    document.querySelectorAll('[data-consent-manage]').forEach(function (b) {
      b.addEventListener('click', function (e) { e.preventDefault(); openPanel(); });
    });
    showBanner();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
