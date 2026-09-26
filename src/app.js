/* ==============================================================================
   COOKIELAUNCHER - FRONTEND CLIENT CONTROLLER (FREESM / PRISM ARCHITECTURE)
   Zero-Lag, Non-Blocking, CORS-Safe, Tolerant Network, Canli MB Ilerlemesi
   ============================================================================== */

let API_BASE = "http://127.0.0.1:18420";

// ================== DURUMLAR ==================
const state = {
  username: localStorage.getItem("cl_username") || "Steve",
  selectedVersion: localStorage.getItem("cl_version") || "26.2",
  loader: localStorage.getItem("cl_loader") || "fabric",
  cookieOptimize: localStorage.getItem("cl_optimize") !== "false",
  ram: parseInt(localStorage.getItem("cl_ram") || "4"),

  // Sürüm Verileri
  versions: [],
  installedVersions: [],
  versionSearchQuery: "",
  versionFilters: {
    optimized: false,
    release: true,
    snapshot: false,
    beta: false,
    alpha: false,
    experimental: false
  },

  // Profiller (Instances)
  instances: [],
  activeInstanceId: localStorage.getItem("cl_instance") || "",
  modrinthTargetId: localStorage.getItem("cl_modrinth_target") || "",

  // Modrinth Durumu
  modrinthType: "mod",
  modrinthLoader: "fabric",
  modrinthSort: "downloads",
  modrinthQuery: "",
  modrinthHits: [],
  modrinthOffset: 0,
  modrinthLimit: 20,
  modrinthHasMore: true,
  modrinthLoading: false,
  packPollTimer: null,
  hideInstalled: localStorage.getItem("cl_hide_installed") === "true",
  installedModSlugs: new Set(),
  installedModFiles: [],
  coreModsWarned: false,

  // 3D Skin Viewer
  skinViewer: null,
  activeAnim: "walk",

  // Başlatma / Polling
  isPollingStatus: false,
  statusTimer: null,
  pollTick: 0,
  coreFailCount: 0,
  launchRequested: false,
  progressOpen: false,
  progressDismissed: false,
  progressCloseTimer: null,
  lastErrorShown: null
};

// Backend'e erişilemezse gösterilecek yerel sürüm listesi (uygulama asla boş kalmasın)
const FALLBACK_VERSIONS = [
  "26.3", "26.2", "26.1.2", "26.1.1", "26.1",
  "1.21.4", "1.21.3", "1.21.2", "1.21.1", "1.21",
  "1.20.6", "1.20.4", "1.20.2", "1.20.1", "1.20",
  "1.19.4", "1.19.2", "1.18.2", "1.17.1", "1.16.5",
  "1.12.2", "1.8.9", "1.7.10"
].map(id => ({ id, type: "release", releaseTime: "", is_optimized: true }));

// ================== YARDIMCI FONKSİYONLAR ==================
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

function showErrorOnce(message) {
  if (!message) return;
  if (state.lastErrorShown === message) return;
  state.lastErrorShown = message;
  showToast(message, "error");
}

// ================== ASLA HATA FIRLATMAYAN API KATMANI ==================
async function apiGet(path, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function apiPost(path, body, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      signal: controller.signal
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function detectApiBase() {
  for (const port of [18420, 18421, 18422, 18423]) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 900);
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/health`, {
        signal: controller.signal,
        cache: "no-store"
      });
      if (res.ok) {
        const data = await res.json();
        // Eski/stale backend süreçlerini atla: yalnızca güncel API sürümü kabul
        if (data && Number(data.api_version) >= 3) {
          API_BASE = `http://127.0.0.1:${port}`;
          return true;
        }
      }
    } catch (_) {
      // sessizce sıradaki porta geç
    } finally {
      clearTimeout(timer);
    }
  }
  return false;
}

// ================== BAŞLATMA (INIT) ==================
document.addEventListener("DOMContentLoaded", async () => {
  await detectApiBase();
  initUI();
  setupEventListeners();
  initSkinViewer(state.username);
  loadVersions();
  loadInstances();
  startStatusPolling();
  setupTauriWindowControls();
});

function initUI() {
  const uInput = document.getElementById("usernameInput");
  if (uInput) uInput.value = state.username;

  const vInput = document.getElementById("versionInput");
  if (vInput) vInput.value = state.selectedVersion;

  const lRadio = document.querySelector(`input[name="loaderRadio"][value="${state.loader}"]`);
  if (lRadio) {
    lRadio.checked = true;
    document.querySelectorAll('input[name="loaderRadio"]').forEach(r => {
      const card = r.closest(".loader-card");
      if (card) card.classList.toggle("active", r.checked);
    });
  }

  const optToggle = document.getElementById("cookieOptimizeToggle");
  if (optToggle) optToggle.checked = state.cookieOptimize;

  const ramSlider = document.getElementById("ramSlider");
  const ramText = document.getElementById("ramValueText");
  if (ramSlider && ramText) {
    ramSlider.value = state.ram;
    ramText.textContent = `${state.ram} GB`;
  }
}

function setupEventListeners() {
  // Sekme Değişimi
  document.querySelectorAll(".nav-tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.getAttribute("data-tab")));
  });

  // Hızlı Klasörler Menüsü
  const btnQuick = document.getElementById("btnQuickFolders");
  const quickMenu = document.getElementById("quickFoldersMenu");
  if (btnQuick && quickMenu) {
    btnQuick.addEventListener("click", (e) => {
      e.stopPropagation();
      quickMenu.classList.toggle("show");
    });
    window.addEventListener("click", () => quickMenu.classList.remove("show"));
  }

  document.querySelectorAll(".dropdown-item[data-folder]").forEach(item => {
    item.addEventListener("click", () => openSystemFolder(item.getAttribute("data-folder")));
  });

  // Oyuncu Adı Değişimi
  const uInput = document.getElementById("usernameInput");
  if (uInput) {
    uInput.addEventListener("input", (e) => {
      state.username = e.target.value.trim() || "Steve";
      localStorage.setItem("cl_username", state.username);
      updateSkinAvatar(state.username);
    });
  }

  // Sürüm Doğrudan Girişi
  const vInput = document.getElementById("versionInput");
  if (vInput) {
    vInput.addEventListener("input", (e) => {
      state.selectedVersion = e.target.value.trim();
      localStorage.setItem("cl_version", state.selectedVersion);
    });
    vInput.addEventListener("change", (e) => {
      const val = e.target.value.trim();
      if (!val) return;
      state.selectedVersion = val;
      localStorage.setItem("cl_version", val);
      if (state.activeInstanceId) updateActiveInstance({ version: val });
    });
  }

  // Aktif Profil Seçici
  const activeSelect = document.getElementById("activeInstanceSelect");
  if (activeSelect) {
    activeSelect.addEventListener("change", (e) => setActiveInstance(e.target.value));
  }

  // Profil Oluşturma Modalı
  const btnCreateInstance = document.getElementById("btnCreateInstance");
  if (btnCreateInstance) btnCreateInstance.addEventListener("click", openCreateInstanceModal);

  const btnCloseCreateInstance = document.getElementById("btnCloseCreateInstanceModal");
  if (btnCloseCreateInstance) btnCloseCreateInstance.addEventListener("click", closeCreateInstanceModal);

  const btnCancelCreateInstance = document.getElementById("btnCancelCreateInstance");
  if (btnCancelCreateInstance) btnCancelCreateInstance.addEventListener("click", closeCreateInstanceModal);

  const btnConfirmCreateInstance = document.getElementById("btnConfirmCreateInstance");
  if (btnConfirmCreateInstance) btnConfirmCreateInstance.addEventListener("click", confirmCreateInstance);

  const instanceNameInput = document.getElementById("instanceNameInput");
  if (instanceNameInput) {
    instanceNameInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") confirmCreateInstance();
    });
  }

  document.querySelectorAll('input[name="instanceLoaderRadio"]').forEach(radio => {
    radio.addEventListener("change", () => {
      document.querySelectorAll('input[name="instanceLoaderRadio"]').forEach(r => {
        const card = r.closest(".loader-card");
        if (card) card.classList.toggle("active", r.checked);
      });
    });
  });

  // Modrinth Kurulum Hedefi
  const modrinthTargetSelect = document.getElementById("modrinthInstanceSelect");
  if (modrinthTargetSelect) {
    modrinthTargetSelect.addEventListener("change", (e) => {
      const id = e.target.value || "";
      state.modrinthTargetId = getInstanceById(id) ? id : "";
      if (state.modrinthTargetId) {
        localStorage.setItem("cl_modrinth_target", state.modrinthTargetId);
      } else {
        localStorage.removeItem("cl_modrinth_target");
      }
      renderModrinthTargetBar();
      fetchModrinth(true);
    });
  }

  // Modrinth sonsuz kaydırma (infinite scroll)
  const mainContent = document.querySelector(".main-content");
  if (mainContent) {
    mainContent.addEventListener("scroll", () => {
      const modrinthPane = document.getElementById("tab-modrinth");
      if (!modrinthPane || !modrinthPane.classList.contains("active")) return;
      if (!state.modrinthHasMore || state.modrinthLoading) return;
      if (mainContent.scrollTop + mainContent.clientHeight >= mainContent.scrollHeight - 400) {
        fetchModrinth(false);
      }
    });
  }

  // ===== Offline Skin =====
  const btnUploadSkin = document.getElementById("btnUploadSkin");
  const skinFileInput = document.getElementById("skinFileInput");
  if (btnUploadSkin && skinFileInput) {
    btnUploadSkin.addEventListener("click", () => skinFileInput.click());
    skinFileInput.addEventListener("change", handleSkinFileSelected);
  }

  const btnSkinUrl = document.getElementById("btnSkinUrl");
  const skinUrlRow = document.getElementById("skinUrlRow");
  if (btnSkinUrl && skinUrlRow) {
    btnSkinUrl.addEventListener("click", () => {
      skinUrlRow.style.display = skinUrlRow.style.display === "none" ? "flex" : "none";
    });
  }

  const btnSaveSkinUrl = document.getElementById("btnSaveSkinUrl");
  if (btnSaveSkinUrl) {
    btnSaveSkinUrl.addEventListener("click", handleSkinUrlSave);
  }

  // Sürüm Seçim Modalı
  const btnOpenVModal = document.getElementById("btnOpenVersionModal");
  if (btnOpenVModal) btnOpenVModal.addEventListener("click", openVersionSelectorModal);

  const btnCloseVModal = document.getElementById("btnCloseVersionSelectorModal");
  if (btnCloseVModal) btnCloseVModal.addEventListener("click", closeVersionSelectorModal);

  const btnCancelVModal = document.getElementById("btnCancelVersionSelectorModal");
  if (btnCancelVModal) btnCancelVModal.addEventListener("click", closeVersionSelectorModal);

  // Sürüm Tablosu Arama
  const vTableSearch = document.getElementById("versionTableSearchInput");
  const btnClearVSearch = document.getElementById("btnClearVersionSearch");
  if (vTableSearch) {
    vTableSearch.addEventListener("input", (e) => {
      state.versionSearchQuery = e.target.value;
      if (btnClearVSearch) btnClearVSearch.style.display = e.target.value ? "block" : "none";
      filterAndRenderVersionTable();
    });
  }
  if (btnClearVSearch && vTableSearch) {
    btnClearVSearch.addEventListener("click", () => {
      vTableSearch.value = "";
      state.versionSearchQuery = "";
      btnClearVSearch.style.display = "none";
      filterAndRenderVersionTable();
    });
  }

  // Sağ Düşey Filtre Paneli
  document.querySelectorAll(".version-filter-cb").forEach(cb => {
    cb.addEventListener("change", () => {
      state.versionFilters[cb.getAttribute("data-category")] = cb.checked;
      filterAndRenderVersionTable();
    });
  });

  // Yükleyici Seçimi
  document.querySelectorAll('input[name="loaderRadio"]').forEach(radio => {
    radio.addEventListener("change", (e) => {
      state.loader = e.target.value;
      localStorage.setItem("cl_loader", state.loader);
      document.querySelectorAll('input[name="loaderRadio"]').forEach(r => {
        const card = r.closest(".loader-card");
        if (card) card.classList.toggle("active", r.checked);
      });
      if (state.activeInstanceId) updateActiveInstance({ loader: state.loader });
    });
  });

  // Optimize Toggle
  const optToggle = document.getElementById("cookieOptimizeToggle");
  if (optToggle) {
    optToggle.addEventListener("change", (e) => {
      state.cookieOptimize = e.target.checked;
      localStorage.setItem("cl_optimize", state.cookieOptimize);
      showToast(state.cookieOptimize ? "⚡ Optimize motoru devrede!" : "Vanilla moduna geçildi.", "info");
    });
  }

  // RAM Slider
  const ramSlider = document.getElementById("ramSlider");
  const ramText = document.getElementById("ramValueText");
  if (ramSlider && ramText) {
    ramSlider.addEventListener("input", (e) => {
      state.ram = parseInt(e.target.value);
      localStorage.setItem("cl_ram", state.ram);
      ramText.textContent = `${state.ram} GB`;
    });
  }

  // OYUNU BAŞLAT
  const btnLaunch = document.getElementById("btnLaunchGame");
  if (btnLaunch) btnLaunch.addEventListener("click", handleLaunchGame);

  // Progress Modal Gizle
  const btnDismissProgress = document.getElementById("btnDismissProgressModal");
  if (btnDismissProgress) {
    btnDismissProgress.addEventListener("click", () => {
      closeProgressModal();
    });
  }

  // 3D Animasyon Butonları
  document.querySelectorAll(".btn-skin-anim[data-anim]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".btn-skin-anim").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      setSkinAnimation(btn.getAttribute("data-anim"));
    });
  });

  const btnResetCam = document.getElementById("btnResetSkinCam");
  if (btnResetCam) {
    btnResetCam.addEventListener("click", () => {
      if (state.skinViewer && state.skinViewer.controls) state.skinViewer.controls.reset();
    });
  }

  // Modrinth Arama
  const btnSearch = document.getElementById("btnDoSearch");
  const sInput = document.getElementById("modrinthSearchInput");
  if (btnSearch && sInput) {
    btnSearch.addEventListener("click", () => {
      state.modrinthQuery = sInput.value;
      fetchModrinth(true);
    });
    sInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        state.modrinthQuery = sInput.value;
        fetchModrinth(true);
      }
    });
  }

  document.querySelectorAll(".cat-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".cat-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      state.modrinthType = pill.getAttribute("data-type");
      fetchModrinth(true);
    });
  });

  const mLoaderSelect = document.getElementById("modrinthLoaderSelect");
  if (mLoaderSelect) {
    mLoaderSelect.addEventListener("change", (e) => {
      state.modrinthLoader = e.target.value;
      fetchModrinth(true);
    });
  }

  const mSortSelect = document.getElementById("modrinthSortSelect");
  if (mSortSelect) {
    mSortSelect.addEventListener("change", (e) => {
      state.modrinthSort = e.target.value;
      fetchModrinth(true);
    });
  }

  // Yüklü modları gizleme anahtarı
  const hideInstalledToggle = document.getElementById("hideInstalledToggle");
  if (hideInstalledToggle) {
    hideInstalledToggle.checked = state.hideInstalled;
    hideInstalledToggle.addEventListener("change", async (e) => {
      state.hideInstalled = e.target.checked;
      localStorage.setItem("cl_hide_installed", state.hideInstalled);

      // Liste daha önce boş yüklendiyse önce yüklü modları tazele
      if (state.installedModSlugs.size === 0 && state.installedModFiles.length === 0) {
        await refreshInstalledMods();
      }
      applyInstalledStates();

      showToast(
        state.hideInstalled
          ? "Yüklü modlar listeden gizlendi."
          : "Yüklü modlar tekrar gösteriliyor.",
        "info"
      );
    });
  }

  // Ekran Görüntüsü Klasörü
  const btnOpenScreenshots = document.getElementById("btnOpenScreenshotsFolder");
  if (btnOpenScreenshots) {
    btnOpenScreenshots.addEventListener("click", () => openSystemFolder("screenshots"));
  }

  // Konsol Temizle
  const btnClearConsole = document.getElementById("btnClearConsole");
  if (btnClearConsole) {
    btnClearConsole.addEventListener("click", () => {
      const cOut = document.getElementById("consoleOutput");
      if (cOut) cOut.textContent = "Konsol temizlendi.\n";
    });
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

  const targetTab = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
  const targetPane = document.getElementById(tabId);

  if (targetTab) targetTab.classList.add("active");
  if (targetPane) targetPane.classList.add("active");

  if (tabId === "tab-modrinth") {
    renderModrinthTargetBar();
    if (state.modrinthHits.length === 0) {
      fetchModrinth(true);
    } else {
      refreshInstalledMods().then(applyInstalledStates);
    }
  } else if (tabId === "tab-gallery") {
    loadScreenshots();
  } else if (tabId === "tab-instances") {
    loadInstances();
  }
}

// ================== PROFİLLER (INSTANCES) ==================
function getInstanceById(id) {
  if (!id) return null;
  return state.instances.find(i => i.id === id) || null;
}

function getActiveInstance() {
  return getInstanceById(state.activeInstanceId);
}

function getModrinthTarget() {
  return getInstanceById(state.modrinthTargetId) || getActiveInstance();
}

async function loadInstances() {
  const data = await apiGet("/api/instances", 8000);
  state.instances = (data && Array.isArray(data.instances)) ? data.instances : [];

  if (state.activeInstanceId && !getInstanceById(state.activeInstanceId)) {
    state.activeInstanceId = "";
    localStorage.removeItem("cl_instance");
  }
  if (state.modrinthTargetId && !getInstanceById(state.modrinthTargetId)) {
    state.modrinthTargetId = "";
    localStorage.removeItem("cl_modrinth_target");
  }

  populateActiveInstanceSelect();
  renderInstances();
  renderModrinthTargetBar();
  applyActiveInstanceToUI();
  ensurePackPolling();
}

function ensurePackPolling() {
  const hasInstalling = state.instances.some(i => i.install_status === "installing");
  if (hasInstalling && !state.packPollTimer) {
    state.packPollTimer = setInterval(async () => {
      await loadInstances();
      if (!state.instances.some(i => i.install_status === "installing")) {
        clearInterval(state.packPollTimer);
        state.packPollTimer = null;
        showToast("📦 Modpack kurulumu tamamlandı!", "success");
      }
    }, 3000);
  }
}

function populateActiveInstanceSelect() {
  const select = document.getElementById("activeInstanceSelect");
  if (!select) return;

  select.innerHTML = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "Profil yok — Genel .minecraft kullanılır";
  select.appendChild(none);

  state.instances.forEach(inst => {
    const opt = document.createElement("option");
    opt.value = inst.id;
    opt.textContent = `${inst.name} — MC ${inst.version} (${inst.loader})`;
    select.appendChild(opt);
  });
}

function renderInstances() {
  const wrap = document.getElementById("instancesGridWrap");
  if (!wrap) return;
  wrap.innerHTML = "";

  if (state.instances.length === 0) {
    const empty = document.createElement("div");
    empty.className = "loading-state";
    empty.innerHTML = `
      <span style="font-size: 38px;">🗂️</span>
      <span>Henüz profil oluşturulmamış.<br>Modların nereye kurulacağını belirlemek için ilk profilinizi oluşturun.</span>
      <button class="btn-primary-action" id="btnEmptyCreateInstance" style="margin-top: 6px;">➕ Yeni Profil Oluştur</button>
    `;
    wrap.appendChild(empty);
    const btn = document.getElementById("btnEmptyCreateInstance");
    if (btn) btn.addEventListener("click", () => openCreateInstanceModal());
    return;
  }

  state.instances.forEach((inst, idx) => {
    const isActive = inst.id === state.activeInstanceId;
    const installing = inst.install_status === "installing";
    const failed = inst.install_status === "failed";
    const card = document.createElement("div");
    card.className = "instance-card" + (isActive ? " active" : "") + (installing ? " installing" : "");
    card.style.animationDelay = `${Math.min(idx * 0.05, 0.4)}s`;

    const iconBox = document.createElement("div");
    iconBox.className = "inst-icon-box";
    if (inst.icon) {
      const img = document.createElement("img");
      img.src = inst.icon;
      img.alt = "";
      img.loading = "lazy";
      img.addEventListener("error", () => {
        img.remove();
        iconBox.textContent = (inst.name || "?").trim().charAt(0).toUpperCase() || "?";
        iconBox.classList.add("inst-icon-letter");
      });
      iconBox.appendChild(img);
    } else {
      iconBox.textContent = (inst.name || "?").trim().charAt(0).toUpperCase() || "?";
      iconBox.classList.add("inst-icon-letter");
    }

    const metaText = installing
      ? `⏳ ${escapeHtml(inst.install_detail || "Kuruluyor...")} %${inst.install_progress || 0}`
      : failed
        ? `⚠️ Kurulum hatası: ${escapeHtml(inst.install_detail || "")}`
        : `MC ${escapeHtml(inst.version)} • ${escapeHtml(inst.loader)} • ${inst.mod_count || 0} mod`;

    const top = document.createElement("div");
    top.className = "inst-card-top";
    top.appendChild(iconBox);

    const info = document.createElement("div");
    info.className = "inst-info";
    info.innerHTML = `
      <h4 class="inst-name" title="${escapeHtml(inst.name)}">${escapeHtml(inst.name)}</h4>
      <span class="inst-meta">${metaText}</span>
    `;
    top.appendChild(info);

    if (isActive) {
      const badge = document.createElement("span");
      badge.className = "inst-badge-active";
      badge.textContent = "AKTİF";
      top.appendChild(badge);
    }

    const actions = document.createElement("div");
    actions.className = "inst-card-actions";

    const btnActivate = document.createElement("button");
    btnActivate.className = "btn-inst btn-inst-primary";
    btnActivate.textContent = isActive ? "✓ Seçili" : "Aktif Yap";
    btnActivate.disabled = installing;
    btnActivate.addEventListener("click", () => setActiveInstance(inst.id));

    const btnMods = document.createElement("button");
    btnMods.className = "btn-inst";
    btnMods.textContent = "📂 Modlar";
    btnMods.addEventListener("click", () => openSystemFolder(`instances/${inst.id}/mods`));

    const btnDelete = document.createElement("button");
    btnDelete.className = "btn-inst btn-inst-danger";
    btnDelete.textContent = "Sil";
    btnDelete.addEventListener("click", () => deleteInstance(inst.id, inst.name));

    actions.appendChild(btnActivate);
    actions.appendChild(btnMods);
    actions.appendChild(btnDelete);

    card.appendChild(top);
    card.appendChild(actions);
    wrap.appendChild(card);
  });
}

function setActiveInstance(id) {
  state.activeInstanceId = getInstanceById(id) ? id : "";

  if (state.activeInstanceId) {
    localStorage.setItem("cl_instance", state.activeInstanceId);
  } else {
    localStorage.removeItem("cl_instance");
  }

  // Modrinth kurulum hedefi aktif profile otomatik uyum sağlar
  state.modrinthTargetId = state.activeInstanceId;
  if (state.modrinthTargetId) {
    localStorage.setItem("cl_modrinth_target", state.modrinthTargetId);
  } else {
    localStorage.removeItem("cl_modrinth_target");
  }

  applyActiveInstanceToUI();
  renderInstances();
  renderModrinthTargetBar();
  fetchModrinth(true);

  const inst = getActiveInstance();
  if (inst) {
    const versionInput = document.getElementById("versionInput");
    if (versionInput) versionInput.value = inst.version;
    showToast(`🗂️ Aktif profil: ${inst.name} (MC ${inst.version} • ${inst.loader})`, "info");
  }
}

function applyActiveInstanceToUI() {
  const select = document.getElementById("activeInstanceSelect");
  const inst = getActiveInstance();

  if (select) select.value = inst ? inst.id : "";

  const vInput = document.getElementById("versionInput");
  const hint = document.getElementById("versionLabelHint");

  if (inst) {
    state.selectedVersion = inst.version;
    state.loader = inst.loader;
    localStorage.setItem("cl_version", state.selectedVersion);
    localStorage.setItem("cl_loader", state.loader);

    if (vInput) vInput.value = inst.version;
    if (hint) hint.textContent = `"${inst.name}" profiline bağlı — değişiklik profile kaydedilir`;

    const radio = document.querySelector(`input[name="loaderRadio"][value="${inst.loader}"]`);
    if (radio) {
      radio.checked = true;
      document.querySelectorAll('input[name="loaderRadio"]').forEach(r => {
        const card = r.closest(".loader-card");
        if (card) card.classList.toggle("active", r.checked);
      });
    }
  } else if (hint) {
    hint.textContent = "İstediğiniz sürümü doğrudan yazabilir veya listeden seçebilirsiniz";
  }
}

async function updateActiveInstance(fields) {
  const inst = getActiveInstance();
  if (!inst) return;

  Object.assign(inst, fields);
  renderInstances();
  renderModrinthTargetBar();

  const data = await apiPost("/api/instances/update", {
    id: inst.id,
    version: inst.version,
    loader: inst.loader,
    name: inst.name
  }, 8000);

  if (data && data.success && data.instance) {
    const idx = state.instances.findIndex(i => i.id === inst.id);
    if (idx >= 0) state.instances[idx] = data.instance;
    renderInstances();
    renderModrinthTargetBar();
  }
}

function openCreateInstanceModal() {
  const modal = document.getElementById("createInstanceModal");
  if (!modal) return;

  const nameInput = document.getElementById("instanceNameInput");
  const versionInput = document.getElementById("instanceVersionInput");
  const iconInput = document.getElementById("instanceIconInput");
  const active = getActiveInstance();

  if (nameInput) nameInput.value = "";
  if (iconInput) iconInput.value = "";
  if (versionInput) versionInput.value = (active && active.version) || state.selectedVersion || "1.20.4";

  const defaultLoader = (active && active.loader) ||
    (["fabric", "forge", "vanilla"].includes(state.loader) ? state.loader : "fabric");

  document.querySelectorAll('input[name="instanceLoaderRadio"]').forEach(r => {
    r.checked = (r.value === defaultLoader);
    const card = r.closest(".loader-card");
    if (card) card.classList.toggle("active", r.checked);
  });

  modal.style.display = "flex";
  if (nameInput) setTimeout(() => nameInput.focus(), 60);
}

function closeCreateInstanceModal() {
  const modal = document.getElementById("createInstanceModal");
  if (modal) modal.style.display = "none";
}

async function confirmCreateInstance() {
  const nameInput = document.getElementById("instanceNameInput");
  const versionInput = document.getElementById("instanceVersionInput");
  const iconInput = document.getElementById("instanceIconInput");
  const name = (nameInput && nameInput.value || "").trim();
  const version = (versionInput && versionInput.value || "").trim() || state.selectedVersion || "1.20.4";
  const icon = (iconInput && iconInput.value || "").trim();
  const loaderRadio = document.querySelector('input[name="instanceLoaderRadio"]:checked');
  const loader = loaderRadio ? loaderRadio.value : "fabric";

  if (!name) {
    showToast("Lütfen bir profil adı girin.", "info");
    if (nameInput) nameInput.focus();
    return;
  }

  const data = await apiPost("/api/instances/create", { name, version, loader, icon }, 10000);

  if (data && data.success && data.instance) {
    closeCreateInstanceModal();
    state.modrinthTargetId = data.instance.id;
    localStorage.setItem("cl_modrinth_target", data.instance.id);
    await loadInstances();
    setActiveInstance(data.instance.id);
    showToast(`✓ "${data.instance.name}" profili oluşturuldu ve aktif edildi.`, "success");
    fetchModrinth(true);
  } else {
    showToast(`⚠️ ${(data && data.error) || "Profil oluşturulamadı."}`, "error");
  }
}

async function deleteInstance(id, name) {
  const inst = getInstanceById(id);
  if (!inst) return;

  if (!window.confirm(`"${name}" profili ve içindeki tüm modlar kalıcı olarak silinecek. Emin misiniz?`)) {
    return;
  }

  const data = await apiPost("/api/instances/delete", { id }, 10000);

  if (data && data.success) {
    if (state.activeInstanceId === id) {
      state.activeInstanceId = "";
      localStorage.removeItem("cl_instance");
    }
    if (state.modrinthTargetId === id) {
      state.modrinthTargetId = "";
      localStorage.removeItem("cl_modrinth_target");
    }
    await loadInstances();
    showToast(`🗑️ "${name}" profili silindi.`, "info");
  } else {
    showToast(`⚠️ ${(data && data.error) || "Profil silinemedi."}`, "error");
  }
}

function renderModrinthTargetBar() {
  const select = document.getElementById("modrinthInstanceSelect");
  const hint = document.getElementById("modrinthTargetHint");
  const loaderSelect = document.getElementById("modrinthLoaderSelect");
  if (!select) return;

  select.innerHTML = "";

  if (state.instances.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Profil yok — önce profil oluşturun";
    select.appendChild(opt);
    select.disabled = true;
    if (loaderSelect) loaderSelect.disabled = false;
    if (hint) hint.textContent = "Mod kurmak için önce bir profil oluşturun; modlar o profilin mods klasörüne kurulur.";
    return;
  }

  state.instances.forEach(inst => {
    const opt = document.createElement("option");
    opt.value = inst.id;
    opt.textContent = `${inst.name} — MC ${inst.version} (${inst.loader})`;
    select.appendChild(opt);
  });

  const target = getModrinthTarget();
  select.value = target ? target.id : state.instances[0].id;
  select.disabled = false;

  const effective = target || state.instances[0];

  if (loaderSelect) {
    loaderSelect.disabled = true;
    loaderSelect.value = ["fabric", "forge"].includes(effective.loader) ? effective.loader : "Tümü";
  }

  if (hint) {
    const vanillaWarning = effective.loader === "vanilla" ? " ⚠️ Vanilla profillere mod kurulmaz." : "";
    hint.textContent = `"${effective.name}" profiline kurulacak • MC ${effective.version} • ${effective.loader} • ${effective.mod_count || 0} mevcut mod${vanillaWarning}`;
  }
}

// ================== SÜRÜM YÖNETİMİ & KOMBİNE FİLTRELEME ==================
async function loadVersions() {
  const data = await apiGet("/api/versions", 12000);

  if (data && Array.isArray(data.versions) && data.versions.length > 0) {
    state.versions = data.versions;
    state.installedVersions = Array.isArray(data.installed) ? data.installed : [];
  } else if (state.versions.length === 0) {
    // Core'a ulaşılamadı: uygulama asla boş kalmasın, yerel listeyle devam et
    state.versions = FALLBACK_VERSIONS.slice();
    state.installedVersions = [];
  }

  const datalist = document.getElementById("versionsDatalist");
  if (datalist) {
    datalist.innerHTML = "";
    state.versions.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v.id;
      datalist.appendChild(opt);
    });
  }

  filterAndRenderVersionTable();
}

function openVersionSelectorModal() {
  const modal = document.getElementById("versionSelectorModal");
  if (!modal) return;
  modal.style.display = "flex";
  filterAndRenderVersionTable();
  const searchInp = document.getElementById("versionTableSearchInput");
  if (searchInp) setTimeout(() => searchInp.focus(), 60);
}

function closeVersionSelectorModal() {
  const modal = document.getElementById("versionSelectorModal");
  if (modal) modal.style.display = "none";
}

function selectVersion(vid) {
  state.selectedVersion = vid;
  localStorage.setItem("cl_version", vid);

  const vInput = document.getElementById("versionInput");
  if (vInput) vInput.value = vid;

  if (state.activeInstanceId) {
    updateActiveInstance({ version: vid });
  }

  closeVersionSelectorModal();
  showToast(`Sürüm seçildi: ${vid}`, "info");
}

function filterAndRenderVersionTable() {
  const tbody = document.getElementById("versionTableListBody");
  const noResults = document.getElementById("versionNoResults");
  const countText = document.getElementById("versionFilteredCountText");
  if (!tbody) return;

  tbody.innerHTML = "";
  const query = (state.versionSearchQuery || "").toLowerCase().trim();

  const filtered = state.versions.filter(v => {
    if (state.versionFilters.optimized) {
      if (!v.is_optimized) return false;
    } else if (!state.versionFilters[v.type]) {
      return false;
    }
    if (query && !String(v.id).toLowerCase().includes(query)) return false;
    return true;
  });

  if (countText) countText.textContent = `${filtered.length} sürüm listeleniyor`;

  if (filtered.length === 0) {
    if (noResults) noResults.style.display = "block";
    return;
  }
  if (noResults) noResults.style.display = "none";

  const typeLabels = {
    release: "Sürüm",
    snapshot: "Snapshot",
    beta: "Beta",
    alpha: "Alpha",
    experimental: "Deneysel"
  };

  filtered.forEach(v => {
    const tr = document.createElement("tr");
    if (v.id === state.selectedVersion) tr.classList.add("active-row");

    const tdName = document.createElement("td");
    tdName.className = "v-cell-name";
    tdName.innerHTML = `
      <span>${escapeHtml(v.id)}</span>
      ${v.is_optimized ? '<span class="badge-opt-pill" title="Cookie Launcher Performans Profili Hazır">⚡ OPTİMİZE</span>' : ""}
      ${v.id === state.selectedVersion ? '<span class="v-star">★</span>' : ""}
    `;

    const tdType = document.createElement("td");
    tdType.innerHTML = `<span class="badge-vtype ${escapeHtml(v.type)}">${typeLabels[v.type] || escapeHtml(v.type)}</span>`;

    const tdStatus = document.createElement("td");
    tdStatus.style.textAlign = "right";
    if (v.is_installed) {
      tdStatus.innerHTML = `<span class="badge-status installed">✓ Yüklü</span>`;
    } else {
      tdStatus.innerHTML = `<span class="badge-status ready">İndirilebilir</span>`;
    }

    tr.appendChild(tdName);
    tr.appendChild(tdType);
    tr.appendChild(tdStatus);
    tr.addEventListener("click", () => selectVersion(v.id));
    tbody.appendChild(tr);
  });
}

// ================== NON-BLOCKING OYUN BAŞLATMA AKIŞI ==================
function setLaunchButton(mode) {
  const btnLaunch = document.getElementById("btnLaunchGame");
  const btnText = document.getElementById("btnLaunchText");
  if (btnText) {
    const labels = {
      idle: "OYUNU BAŞLAT",
      busy: "BAŞLATILIYOR...",
      installing: "YÜKLENİYOR...",
      running: "🎮 OYUN ÇALIŞIYOR"
    };
    btnText.textContent = labels[mode] || labels.idle;
  }
  if (btnLaunch) btnLaunch.disabled = (mode !== "idle");
}

function openProgressModal() {
  const modal = document.getElementById("launchProgressModal");
  if (!modal) return;
  modal.style.display = "flex";
  state.progressOpen = true;
}

function ensureProgressModal() {
  if (state.progressDismissed) return;
  const modal = document.getElementById("launchProgressModal");
  if (!modal) return;
  if (modal.style.display === "none" || !state.progressOpen) {
    modal.style.display = "flex";
  }
  state.progressOpen = true;
}

function closeProgressModal() {
  const modal = document.getElementById("launchProgressModal");
  if (modal) modal.style.display = "none";
  state.progressOpen = false;
  state.progressDismissed = true;
}

function scheduleCloseProgressModal(delayMs) {
  if (state.progressCloseTimer) return;
  state.progressCloseTimer = setTimeout(() => {
    closeProgressModal();
    state.progressCloseTimer = null;
  }, delayMs);
}

function setProgressBar(percent) {
  const barFill = document.getElementById("launchProgressBarFill");
  const percentText = document.getElementById("launchProgressPercent");
  const value = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
  if (barFill) barFill.style.width = `${value}%`;
  if (percentText) percentText.textContent = `${value}%`;
}

function setProgressTexts(status, detail, mb) {
  const statusMsg = document.getElementById("launchProgressStatusText");
  const detailMsg = document.getElementById("launchProgressDetailText");
  const mbText = document.getElementById("launchProgressMbText");

  if (statusMsg && status) statusMsg.textContent = status;
  if (detailMsg) detailMsg.textContent = detail || "";
  if (mbText) {
    const mbValue = Number(mb);
    mbText.textContent = `⬇ ${(Number.isFinite(mbValue) ? mbValue : 0).toFixed(1)} MB`;
  }
}

async function handleLaunchGame() {
  if (state.launchRequested) return;

  const btnLaunch = document.getElementById("btnLaunchGame");
  if (btnLaunch && btnLaunch.disabled) return;

  const activeInst = getActiveInstance();
  const versionToLaunch = activeInst ? activeInst.version : ((state.selectedVersion || "").trim() || "1.20.4");

  state.launchRequested = true;
  state.progressDismissed = false;
  state.progressCloseTimer = null;
  state.lastErrorShown = null;

  openProgressModal();
  setLaunchButton("busy");
  setProgressBar(2);
  setProgressTexts(
    "Oyun hazırlanıyor...",
    activeInst ? `"${activeInst.name}" profili başlatılıyor...` : "Arka plan servisine bağlanılıyor...",
    0
  );

  const payload = {
    username: state.username,
    version: versionToLaunch,
    loader: activeInst ? activeInst.loader : state.loader,
    cookie_optimized: state.cookieOptimize,
    ram: state.ram,
    jvm_preset: "aikar"
  };
  if (activeInst) payload.instance_id = activeInst.id;

  let accepted = false;
  let backendError = null;

  for (let attempt = 1; attempt <= 2 && !accepted; attempt++) {
    const data = await apiPost("/api/launch", payload, 15000);

    if (data && data.success) {
      accepted = true;
      break;
    }
    if (data && data.error) {
      backendError = data.error;
      break;
    }
    if (attempt === 1) {
      setProgressTexts("Oyun hazırlanıyor...", "Core servisi yanıt vermedi, yeniden deneniyor...", 0);
    }
    await sleep(700);
  }

  if (accepted) {
    setProgressTexts("Başlatma isteği kabul edildi", "İndirme akışı arka planda sürüyor...", 0);
    return;
  }

  // İstek kabul edilmedi: modalı kapat, butonu eski haline getir, tek seferlik bilgi ver
  state.launchRequested = false;
  closeProgressModal();
  setLaunchButton("idle");
  showErrorOnce(backendError || "Core servisine ulaşılamadı. Arka plan servisini yeniden başlatın.");
}

// ================== CANLI DURUM & İLERLEME POLLING ==================
function startStatusPolling() {
  if (state.isPollingStatus) return;
  state.isPollingStatus = true;
  state.statusTimer = setInterval(pollStatus, 700);
}

async function pollStatus() {
  state.pollTick++;

  const data = await apiGet("/api/status", 5000);

  if (!data) {
    state.coreFailCount++;
    if (state.coreFailCount >= 3) {
      const engineStatus = document.getElementById("engineStatusText");
      if (engineStatus) engineStatus.textContent = "Core Bekleniyor...";
    }
    // Her ~7 saniyede bir portu yeniden keşfetmeyi dene
    if (state.coreFailCount % 10 === 0) {
      await detectApiBase();
    }
    return;
  }

  state.coreFailCount = 0;
  updateProgressUI(data);

  // Konsol loglarını daha seyrek güncelle (gereksiz yükü önler)
  if (state.pollTick % 3 === 0) {
    const logData = await apiGet("/api/logs", 5000);
    const cOut = document.getElementById("consoleOutput");
    if (logData && Array.isArray(logData.logs) && cOut) {
      cOut.textContent = logData.logs.join("\n");
      cOut.scrollTop = cOut.scrollHeight;
    }
  }
}

function updateEngineStatus(installing, running) {
  const engineStatus = document.getElementById("engineStatusText");
  if (!engineStatus) return;
  if (running) {
    engineStatus.textContent = "Oyun Çalışıyor";
  } else if (installing) {
    engineStatus.textContent = "Hazırlanıyor...";
  } else {
    engineStatus.textContent = "Core Hazır";
  }
}

function updateProgressUI(data) {
  const installing = !!data.is_installing;
  const running = !!data.is_running;
  const error = data.error || null;

  updateEngineStatus(installing, running);

  // 1. İndirme / Hazırlama sürüyor
  if (installing) {
    state.launchRequested = true;
    state.progressCloseTimer = null;
    ensureProgressModal();
    setProgressBar(data.percent || 2);
    setProgressTexts(data.status || "Hazırlanıyor...", data.detail || "", data.downloaded_mb);
    setLaunchButton("installing");
    return;
  }

  // 2. Oyun başarıyla açıldı
  if (running) {
    if (!state.progressDismissed) {
      ensureProgressModal();
      setProgressBar(100);
      setProgressTexts("✨ Oyun Başarıyla Açıldı!", "İyi oyunlar!", data.downloaded_mb);
      scheduleCloseProgressModal(1200);
    }
    state.launchRequested = false;
    setLaunchButton("running");
    return;
  }

  // 3. Boşta
  if (state.launchRequested) {
    state.launchRequested = false;
    closeProgressModal();
  }
  if (error) {
    showErrorOnce(error);
    closeProgressModal();
    apiPost("/api/clear-error", {}, 5000);
  }
  setLaunchButton("idle");
}

// ================== MODRINTH İÇERİK MERKEZİ ==================
function isModInstalled(hit) {
  if (!hit || hit.project_type === "modpack") return false;
  const slug = String(hit.slug || "").toLowerCase();
  if (!slug) return false;

  if (state.installedModSlugs.has(slug)) return true;

  const patterns = [slug, slug.replace(/-/g, "_"), slug.replace(/_/g, "-")];
  return state.installedModFiles.some(file => {
    const name = String(file).toLowerCase();
    return patterns.some(p =>
      name === `${p}.jar` ||
      name.startsWith(`${p}-`) ||
      name.startsWith(`${p}_`) ||
      name.includes(`-${p}-`) ||
      name.includes(`_${p}_`)
    );
  });
}

async function refreshInstalledMods() {
  state.installedModSlugs = new Set();
  state.installedModFiles = [];

  const target = getModrinthTarget();
  if (!target) return;

  const data = await apiGet(`/api/instances/mods?instance_id=${encodeURIComponent(target.id)}`, 8000);
  if (!data || data.success !== true) {
    // Core eski sürümdeyse (endpoint yoksa) kullanıcıyı bir kez bilgilendir
    if (!state.coreModsWarned) {
      state.coreModsWarned = true;
      showToast("Core güncel değil: yüklü mod tespiti için launcher'ı yeniden başlatın.", "info");
    }
    return;
  }

  const manifest = data.manifest || {};
  Object.keys(manifest).forEach(slug => state.installedModSlugs.add(String(slug).toLowerCase()));
  state.installedModFiles = Array.isArray(data.files) ? data.files : [];
}

function applyInstalledStates() {
  document.querySelectorAll(".mod-card[data-slug]").forEach(card => {
    const slug = card.getAttribute("data-slug");
    const installed = state.installedModSlugs.has(String(slug).toLowerCase()) ||
      isModInstalled({ slug: slug, project_type: "mod" });

    if (installed) {
      card.classList.add("installed");
      const btn = card.querySelector(".btn-mod-dl");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "✓ Yüklü";
      }
      if (state.hideInstalled) {
        card.style.display = "none";
        return;
      }
    } else {
      card.classList.remove("installed");
      const btn = card.querySelector(".btn-mod-dl");
      if (btn && btn.dataset.kind !== "modpack") {
        btn.disabled = false;
        btn.textContent = "⚡ Hızlı Kur";
      }
    }
    card.style.display = "";
  });
}

function buildModCard(hit, index) {
  const target = getModrinthTarget();
  const isModpack = (hit.project_type === "modpack") || (state.modrinthType === "modpack");
  const installed = !isModpack && isModInstalled(hit);

  const card = document.createElement("div");
  card.className = "mod-card" + (installed ? " installed" : "");
  card.dataset.slug = hit.slug || "";
  card.style.animationDelay = `${Math.min(index * 0.03, 0.5)}s`;

  const iconBox = document.createElement("div");
  iconBox.className = "mod-icon-box";
  if (hit.icon_url) {
    const img = document.createElement("img");
    img.src = hit.icon_url;
    img.alt = hit.title || "";
    img.loading = "lazy";
    img.addEventListener("error", () => {
      img.remove();
      iconBox.textContent = isModpack ? "📦" : "🧩";
    });
    iconBox.appendChild(img);
  } else {
    iconBox.textContent = isModpack ? "📦" : "🧩";
  }

  let buttonLabel = "⚡ Hızlı Kur";
  if (isModpack) buttonLabel = "📦 Profil Olarak Kur";
  else if (installed) buttonLabel = "✓ Yüklü";

  const content = document.createElement("div");
  content.className = "mod-content";
  content.innerHTML = `
    <h4 class="mod-title" title="${escapeHtml(hit.title)}">${escapeHtml(hit.title)}</h4>
    <p class="mod-desc">${escapeHtml(hit.description || "Açıklama bulunmuyor.")}</p>
    <div class="mod-bottom-row">
      <span style="font-size: 11px; color: var(--text-muted);">⬇ ${(hit.downloads || 0).toLocaleString()}</span>
      ${installed ? '<span class="mod-installed-chip">✓ Bu profilde yüklü</span>' : ""}
      ${!installed && target ? `<span class="mod-target-chip" title="Kurulum hedefi: ${escapeHtml(target.name)}">📥 ${escapeHtml(target.name)}</span>` : ""}
      <button class="btn-mod-dl" data-kind="${isModpack ? "modpack" : "mod"}">${buttonLabel}</button>
    </div>
  `;

  const dlButton = content.querySelector(".btn-mod-dl");
  if (dlButton) {
    if (installed) {
      dlButton.disabled = true;
    } else {
      dlButton.addEventListener("click", () => installModrinthProject(hit, dlButton));
    }
  }

  if (installed && state.hideInstalled) {
    card.style.display = "none";
  }

  card.appendChild(iconBox);
  card.appendChild(content);
  return card;
}

function updateModrinthFooter(total = 0) {
  const wrap = document.getElementById("modrinthResultsWrap");
  if (!wrap) return;

  let footer = document.getElementById("modrinthLoadMore");
  if (!footer) {
    footer = document.createElement("div");
    footer.id = "modrinthLoadMore";
    footer.className = "loading-state modrinth-load-more";
    wrap.appendChild(footer);
  }

  if (state.modrinthLoading) {
    footer.innerHTML = `<div class="spinner"></div><span>Daha fazla içerik yükleniyor...</span>`;
  } else if (state.modrinthHasMore) {
    footer.innerHTML = `<span>↓ Kaydırdıkça daha fazla içerik otomatik yüklenecek...</span>`;
  } else if (state.modrinthHits.length > 0) {
    footer.innerHTML = `<span>✓ Tüm sonuçlar yüklendi (${state.modrinthHits.length}${total ? "/" + total : ""}).</span>`;
  } else {
    footer.innerHTML = "";
  }
}

async function fetchModrinth(reset = true) {
  const wrap = document.getElementById("modrinthResultsWrap");
  if (!wrap || state.modrinthLoading) return;
  if (!reset && !state.modrinthHasMore) return;

  state.modrinthLoading = true;

  if (reset) {
    state.modrinthOffset = 0;
    state.modrinthHits = [];
    state.modrinthHasMore = true;
    wrap.innerHTML = `<div class="loading-state"><div class="spinner"></div><span>Modrinth taranıyor...</span></div>`;
    await refreshInstalledMods();
  } else {
    updateModrinthFooter();
  }

  const target = getModrinthTarget();
  const effectiveVersion = target ? target.version : (state.selectedVersion || "");
  const effectiveLoader = target
    ? (target.loader === "vanilla" ? "Tümü" : target.loader)
    : (state.modrinthLoader || "fabric");

  const params = new URLSearchParams({
    q: state.modrinthQuery || "",
    type: state.modrinthType || "mod",
    version: effectiveVersion,
    loader: effectiveLoader,
    sort: state.modrinthSort || "downloads",
    limit: state.modrinthLimit,
    offset: state.modrinthOffset
  });

  const data = await apiGet(`/api/modrinth/search?${params.toString()}`, 15000);
  state.modrinthLoading = false;

  if (!data) {
    if (reset) {
      wrap.innerHTML = `<div class="loading-state"><span>Modrinth şu anda yanıt vermiyor. Daha sonra tekrar deneyin.</span></div>`;
    }
    return;
  }

  const hits = Array.isArray(data.hits) ? data.hits : [];
  const total = Number(data.total_hits) || 0;
  state.modrinthOffset += hits.length;
  state.modrinthHasMore = hits.length > 0 && (total === 0 || state.modrinthOffset < total);

  if (reset) {
    state.modrinthHits = hits;
    wrap.innerHTML = "";
  } else {
    state.modrinthHits = state.modrinthHits.concat(hits);
  }

  if (state.modrinthHits.length === 0) {
    wrap.innerHTML = `<div class="loading-state"><span>Aradığınız kriterlere uygun içerik bulunamadı.</span></div>`;
    state.modrinthHasMore = false;
    return;
  }

  const footer = document.getElementById("modrinthLoadMore");
  const startIndex = reset ? 0 : state.modrinthHits.length - hits.length;
  hits.forEach((hit, i) => {
    const card = buildModCard(hit, startIndex + i);
    if (footer) wrap.insertBefore(card, footer);
    else wrap.appendChild(card);
  });

  updateModrinthFooter(total);
}

async function installModrinthProject(hit, buttonEl) {
  const isModpack = (hit.project_type === "modpack") || (state.modrinthType === "modpack");
  if (isModpack) {
    await installModpackAsProfile(hit, buttonEl);
  } else {
    await downloadModrinthProject(hit.slug, buttonEl);
  }
}

async function installModpackAsProfile(hit, buttonEl) {
  const target = getModrinthTarget();
  const gameVersion = target ? target.version : (state.selectedVersion || "");
  const originalText = buttonEl ? buttonEl.textContent : null;

  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = "📦 Profil oluşturuluyor...";
  }

  showToast(`📦 ${hit.title || hit.slug} yeni profil olarak ekleniyor...`, "info");

  const data = await apiPost("/api/modrinth/modpack/install", {
    slug: hit.slug,
    game_version: gameVersion
  }, 60000);

  if (buttonEl) {
    buttonEl.disabled = false;
    buttonEl.textContent = originalText || "📦 Profil Olarak Kur";
  }

  if (data && data.success && data.instance) {
    await loadInstances();
    ensurePackPolling();
    switchTab("tab-instances");
    showToast(`✓ "${data.instance.name}" profili oluşturuldu, kurulum arka planda sürüyor.`, "success");
  } else {
    showToast(`⚠️ ${(data && data.error) || "Modpack profili oluşturulamadı."}`, "error");
  }
}

async function downloadModrinthProject(slug, buttonEl) {
  if (!slug) return;

  const target = getModrinthTarget();

  // Hedef profil yoksa sessizce nereye kurulacağı belirsiz olmasın: profil oluşturmaya yönlendir
  if (!target) {
    showToast("Mod kurmak için önce bir profil oluşturun.", "info");
    openCreateInstanceModal();
    return;
  }

  if (target.loader === "vanilla") {
    showToast("Vanilla profil mod yüklemez. PROFİLLER sekmesinden Fabric/Forge profili seçin.", "info");
    return;
  }

  const originalText = buttonEl ? buttonEl.textContent : null;
  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = "Kuruluyor...";
  }

  showToast(`📥 ${slug} → "${target.name}" profiline indiriliyor...`, "info");

  const data = await apiPost("/api/modrinth/install", {
    slug: slug,
    version: target.version,
    loader: target.loader,
    instance_id: target.id
  }, 120000);

  if (buttonEl) {
    buttonEl.disabled = false;
    buttonEl.textContent = originalText || "⚡ Hızlı Kur";
  }

  if (data && data.success) {
    showToast(`✓ ${data.filename || slug} → "${target.name}" profiline kuruldu.`, "success");
    await refreshInstalledMods();
    applyInstalledStates();
    loadInstances();
  } else if (data && data.error) {
    showToast(`⚠️ ${data.error}`, "error");
  } else {
    showToast("⚠️ Mod indirme isteği tamamlanamadı, tekrar deneyin.", "error");
  }
}

// ================== GALERİ (EKRAN GÖRÜNTÜLERİ) ==================
async function loadScreenshots() {
  const wrap = document.getElementById("screenshotsGridWrap");
  if (!wrap) return;

  const data = await apiGet("/api/screenshots", 10000);
  wrap.innerHTML = "";

  if (!data) {
    wrap.innerHTML = `<div class="loading-state" style="grid-column: 1/-1;"><span>Galeriye şu anda ulaşılamıyor.</span></div>`;
    return;
  }

  const shots = Array.isArray(data.screenshots) ? data.screenshots : [];
  if (shots.length === 0) {
    wrap.innerHTML = `<div class="loading-state" style="grid-column: 1/-1;"><span>Henüz ekran görüntüsü alınmamış (Oyunda F2 tuşuna basın).</span></div>`;
    return;
  }

  shots.forEach(sc => {
    const card = document.createElement("div");
    card.className = "gallery-card";
    card.innerHTML = `
      <div class="gallery-thumb">
        <span style="font-size: 32px;">📸</span>
      </div>
      <div class="gallery-meta">
        <span>${escapeHtml(sc.name)}</span>
        <span>${Math.round((sc.size || 0) / 1024)} KB</span>
      </div>
    `;
    wrap.appendChild(card);
  });
}

// ================== SİSTEM KLASÖRÜ AÇMA ==================
async function openSystemFolder(folderName) {
  await apiPost("/api/open-folder", { folder: folderName || "" }, 8000);
}

// ================== 3D SKIN GÖRÜNTÜLEYİCİ ==================
function initSkinViewer(username) {
  const canvas = document.getElementById("skinCanvas");
  if (!canvas || typeof skinview3d === "undefined") return;

  try {
    state.skinViewer = new skinview3d.SkinViewer({
      canvas: canvas,
      width: 280,
      height: 340,
      skin: `https://mc-heads.net/skin/${encodeURIComponent(username || "Steve")}`
    });

    state.skinViewer.camera.position.set(0, 0, 60);
    state.skinViewer.controls.enableRotate = true;
    state.skinViewer.controls.enableZoom = true;
    state.skinViewer.controls.enablePan = false;

    setSkinAnimation("walk");
    applySkinForUsername(username);
  } catch (e) {
    console.warn("3D SkinViewer başlatılamadı:", e);
  }
}

function setSkinAnimation(animType) {
  if (!state.skinViewer || typeof skinview3d === "undefined") return;
  state.activeAnim = animType;

  try {
    if (animType === "walk") {
      state.skinViewer.animation = new skinview3d.WalkingAnimation();
      state.skinViewer.animation.speed = 0.6;
    } else if (animType === "run") {
      state.skinViewer.animation = new skinview3d.RunningAnimation();
      state.skinViewer.animation.speed = 0.9;
    } else if (animType === "wave") {
      state.skinViewer.animation = new skinview3d.WaveAnimation();
      state.skinViewer.animation.speed = 1.0;
    } else {
      state.skinViewer.animation = new skinview3d.IdleAnimation();
      state.skinViewer.animation.speed = 0.4;
    }
  } catch (e) {
    console.warn("Skin animasyonu değiştirilemedi:", e);
  }
}

function updateSkinAvatar(username) {
  applySkinForUsername(username);
}

async function applySkinForUsername(username) {
  if (!state.skinViewer) return;
  const clean = (username || "Steve").trim() || "Steve";

  const info = await apiGet(`/api/skin/info?username=${encodeURIComponent(clean)}`, 5000);
  if (info && info.has_skin && info.skin_url) {
    loadViewerSkin(`${API_BASE}${info.skin_url}?t=${Date.now()}`, clean);
    return;
  }
  loadViewerSkin(`https://mc-heads.net/skin/${encodeURIComponent(clean)}`, clean);
}

function loadViewerSkin(url, fallbackName) {
  if (!state.skinViewer) return;
  try {
    const result = state.skinViewer.loadSkin(url);
    if (result && typeof result.catch === "function") {
      result.catch(() => {
        try {
          state.skinViewer.loadSkin(`https://mc-heads.net/skin/${encodeURIComponent(fallbackName || "Steve")}`);
        } catch (_) {}
      });
    }
  } catch (_) {}
}

async function handleSkinFileSelected(e) {
  const file = e.target.files && e.target.files[0];
  e.target.value = "";
  if (!file) return;

  if (!String(file.type).includes("png")) {
    showToast("Lütfen PNG formatında bir skin dosyası seçin.", "error");
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    showToast("Skin dosyası en fazla 2 MB olabilir.", "error");
    return;
  }

  const reader = new FileReader();
  reader.onload = async () => {
    const data = await apiPost("/api/skin/save", { username: state.username, data_url: reader.result }, 20000);
    if (data && data.success) {
      showToast("✓ Skin kaydedildi ve önizlemeye uygulandı.", "success");
      applySkinForUsername(state.username);
    } else {
      showToast(`⚠️ ${(data && data.error) || "Skin kaydedilemedi."}`, "error");
    }
  };
  reader.readAsDataURL(file);
}

async function handleSkinUrlSave() {
  const input = document.getElementById("skinUrlInput");
  const url = ((input && input.value) || "").trim();
  if (!url) {
    showToast("Lütfen bir görsel URL'si girin.", "info");
    return;
  }
  const data = await apiPost("/api/skin/save", { username: state.username, url }, 20000);
  if (data && data.success) {
    showToast("✓ Skin URL'den kaydedildi.", "success");
    applySkinForUsername(state.username);
  } else {
    showToast(`⚠️ ${(data && data.error) || "Skin indirilemedi."}`, "error");
  }
}

// ================== TAURI NATIVE PENCERE KONTROLLERİ ==================
function setupTauriWindowControls() {
  const btnMin = document.getElementById("btnWinMinimize");
  const btnMax = document.getElementById("btnWinMaximize");
  const btnClose = document.getElementById("btnWinClose");

  if (window.__TAURI__ && window.__TAURI__.window) {
    try {
      const appWin = window.__TAURI__.window.getCurrentWindow();
      if (btnMin) btnMin.addEventListener("click", () => appWin.minimize());
      if (btnMax) btnMax.addEventListener("click", () => appWin.toggleMaximize());
      if (btnClose) btnClose.addEventListener("click", () => appWin.close());
      return;
    } catch (_) {}
  }

  if (btnMin) btnMin.addEventListener("click", () => window.blur());
  if (btnClose) btnClose.addEventListener("click", () => window.close());
}
