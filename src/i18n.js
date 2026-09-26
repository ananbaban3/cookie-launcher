// CookieLauncher Çok Dilli Çeviri Sistemi (TR, EN, RU)
const translations = {
  tr: {
    // Navigasyon
    nav_play: "OYNA",
    nav_instances: "PROFİLLER",
    nav_modrinth: "KEŞFET (MOD/PAKET)",
    nav_mods: "MOD YÖNETİCİSİ",
    nav_stats: "İSTATİSTİKLER",
    nav_accounts: "HESAPLAR",
    nav_gallery: "GALERİ",
    nav_settings: "AYARLAR",
    nav_console: "CANLI KONSOL",

    // Başlık ve Durum
    badge_ultra: "ULTRA OPTİMİZE",
    server_ready: "Launcher Hazır",
    status_ready: "Hazır",
    status_offline: "Çevrimdışı",
    btn_launch: "OYUNU BAŞLAT",
    btn_launching: "BAŞLATILIYOR...",
    btn_running: "OYUN ÇALIŞIYOR",

    // Oyna Sekmesi
    label_player: "Aktif Oyuncu",
    label_version: "Minecraft Sürümü",
    label_loader: "Mod Yükleyici",
    label_ram: "Ayrılan Bellek (RAM)",
    label_resolution: "Ekran Çözünürlüğü",
    label_fullbright: "FullBright (Gece Görüşü)",
    label_sodium_opt: "Sodium Optimizasyon Motoru",
    loader_fabric: "Fabric (Önerilen)",
    loader_forge: "Forge (Mod Motoru)",
    loader_vanilla: "Vanilla (Saf Minecraft)",
    opt_active_badge: "⚡ Sodium Aktif",
    skin_3d_title: "3D Karakter Önizleme",
    skin_anim_walk: "Yürüme",
    skin_anim_run: "Koşma",
    skin_anim_idle: "Hareketsiz",
    skin_anim_wave: "El Salla",
    skin_reset_cam: "Kamerayı Sıfırla",
    quick_open_dir: ".minecraft Klasörü",

    // Profiller (Instances)
    instances_title: "İzole Oyun Profilleri (Instances)",
    instances_desc: "Her profil kendi bağımsız modlarına, dünyalarına ve ayarlarına sahiptir.",
    btn_create_instance: "➕ Yeni Profil Oluştur",
    inst_name: "Profil Adı",
    inst_version: "Sürüm",
    inst_loader: "Yükleyici",
    inst_ram: "RAM (GB)",
    inst_play: "Oyna",
    inst_open_folder: "Klasörü Aç",
    inst_delete: "Sil",
    modal_inst_title: "Yeni Profil Oluştur",
    btn_create: "Oluştur",
    btn_cancel: "İptal",

    // Keşfet (Modrinth)
    modrinth_title: "Modrinth İçerik Merkezi",
    modrinth_search_ph: "Yüzbinlerce mod, modpack, shader ve kaynak paketi ara...",
    cat_mods: "Modlar",
    cat_modpacks: "Mod Paketleri",
    cat_shaders: "Shader Paketleri",
    cat_resourcepacks: "Doku Paketleri",
    filter_loader: "Yükleyici:",
    filter_version: "MC Sürümü:",
    filter_channel: "Kanal:",
    sort_downloads: "En Çok İndirilen",
    sort_relevance: "Alaka Düzeyi",
    sort_newest: "En Yeni",
    btn_quick_install: "⚡ Hızlı Kur",
    btn_choose_ver: "📋 Sürüm Seç",

    // Mod Yöneticisi
    installed_title: "Yüklü Dosya Yöneticisi",
    installed_desc: "Aktif Minecraft profilinizdeki dosyaları tek tıkla açıp kapatın veya silin.",
    tab_installed_mods: "Modlar",
    tab_installed_shaders: "Shaderlar",
    tab_installed_resourcepacks: "Doku Paketleri",
    btn_enable: "Etkinleştir",
    btn_disable: "Devre Dışı Bırak",
    btn_delete: "Sil",
    btn_open_folder: "Klasörü Aç",

    // İstatistikler
    stats_title: "Oyun İstatistikleri ve Geçmiş",
    stat_total_time: "Toplam Oynama Süresi",
    stat_launches: "Toplam Başlatma",
    stat_last_session: "Son Oturum",
    stat_history_title: "Geçmiş Oturumlar",
    col_date: "Tarih & Saat",
    col_version: "Sürüm & Profil",
    col_duration: "Süre",
    col_status: "Durum",

    // Hesaplar
    accounts_title: "Hesap & Güvenlik Yöneticisi",
    btn_add_offline: "👤 Çevrimdışı Hesap Ekle",
    btn_add_microsoft: "🟩 Microsoft ile Giriş Yap",
    acc_active_badge: "✓ AKTİF HESAP",
    btn_switch_acc: "Bu Hesaba Geç",
    btn_remove_acc: "Hesabı Sil",
    modal_offline_title: "Çevrimdışı Oyuncu Ekle",
    offline_name_ph: "Oyuncu Adı (örn. Steve, Alex, ProGamer)",

    // Galeri
    gallery_title: "Oyun İçi Ekran Görüntüleri",
    gallery_desc: "Minecraft'ta F2 tuşuyla aldığınız tüm ekran görüntüleri.",
    btn_copy_image: "Panoya Kopyala",

    // Ayarlar
    settings_title: "Gelişmiş Launcher Ayarları",
    lang_select_label: "Launcher Dili (Language)",
    jvm_flags_label: "JVM Optimizasyon Bayrakları",
    jvm_preset_aikar: "Aikar Flags (Maksimum FPS & Akıcılık)",
    jvm_preset_zgc: "ZGC Düşük Gecikme (Java 17/21+)",
    jvm_preset_default: "Standart JVM Parametreleri",
    java_path_label: "Özel Java Çalıştırılabilir Dosyası (Path)",
    java_detect_btn: "Otomatik Tespit Et",
    security_pin_label: "Başlatıcı Güvenlik PIN Kodu",
    btn_save_settings: "Ayarları Kaydet",

    // Crash Log
    crash_title: "⚠️ Oyun Beklenmedik Şekilde Kapandı!",
    crash_cause: "Tespit Edilen Olası Neden:",
    crash_log_label: "Çökme Raporu ve Hata Ayrıntıları:",
    btn_copy_crash: "Raporu Kopyala",
    btn_open_crash_dir: "Crash Klasörünü Aç",

    // Hızlı Klasörler
    quick_folders: "Klasörlere Hızlı Erişim",
    toast_copied: "Panoya kopyalandı!",
    toast_saved: "Ayarlar başarıyla kaydedildi!"
  },

  en: {
    // Navigation
    nav_play: "PLAY",
    nav_instances: "PROFILES",
    nav_modrinth: "EXPLORE",
    nav_mods: "MOD MANAGER",
    nav_stats: "STATISTICS",
    nav_accounts: "ACCOUNTS",
    nav_gallery: "GALLERY",
    nav_settings: "SETTINGS",
    nav_console: "CONSOLE",

    // Header & Status
    badge_ultra: "ULTRA OPTIMIZED",
    server_ready: "Launcher Ready",
    status_ready: "Ready",
    status_offline: "Offline",
    btn_launch: "PLAY GAME",
    btn_launching: "LAUNCHING...",
    btn_running: "GAME RUNNING",

    // Play Tab
    label_player: "Active Player",
    label_version: "Minecraft Version",
    label_loader: "Mod Loader",
    label_ram: "Allocated RAM",
    label_resolution: "Screen Resolution",
    label_fullbright: "FullBright (Night Vision)",
    label_sodium_opt: "Sodium Optimization Engine",
    loader_fabric: "Fabric (Recommended)",
    loader_forge: "Forge (Mod Engine)",
    loader_vanilla: "Vanilla (Clean)",
    opt_active_badge: "⚡ Sodium Active",
    skin_3d_title: "3D Character Preview",
    skin_anim_walk: "Walk",
    skin_anim_run: "Run",
    skin_anim_idle: "Idle",
    skin_anim_wave: "Wave",
    skin_reset_cam: "Reset Camera",
    quick_open_dir: ".minecraft Folder",

    // Instances
    instances_title: "Isolated Game Profiles (Instances)",
    instances_desc: "Every instance possesses independent mods, saves, and settings.",
    btn_create_instance: "➕ Create New Profile",
    inst_name: "Profile Name",
    inst_version: "Version",
    inst_loader: "Loader",
    inst_ram: "RAM (GB)",
    inst_play: "Play",
    inst_open_folder: "Open Folder",
    inst_delete: "Delete",
    modal_inst_title: "Create New Profile",
    btn_create: "Create",
    btn_cancel: "Cancel",

    // Modrinth
    modrinth_title: "Modrinth Content Hub",
    modrinth_search_ph: "Search thousands of mods, modpacks, shaders, and resource packs...",
    cat_mods: "Mods",
    cat_modpacks: "Modpacks",
    cat_shaders: "Shaders",
    cat_resourcepacks: "Resource Packs",
    filter_loader: "Loader:",
    filter_version: "MC Version:",
    filter_channel: "Channel:",
    sort_downloads: "Most Downloaded",
    sort_relevance: "Relevance",
    sort_newest: "Newest",
    btn_quick_install: "⚡ Quick Install",
    btn_choose_ver: "📋 Choose Version",

    // Mod Manager
    installed_title: "Installed Files Manager",
    installed_desc: "Enable, disable or delete files in your active profile with one click.",
    tab_installed_mods: "Mods",
    tab_installed_shaders: "Shaders",
    tab_installed_resourcepacks: "Resource Packs",
    btn_enable: "Enable",
    btn_disable: "Disable",
    btn_delete: "Delete",
    btn_open_folder: "Open Folder",

    // Stats
    stats_title: "Game Statistics & Playtime",
    stat_total_time: "Total Playtime",
    stat_launches: "Total Launches",
    stat_last_session: "Last Session",
    stat_history_title: "Session History",
    col_date: "Date & Time",
    col_version: "Version & Profile",
    col_duration: "Duration",
    col_status: "Status",

    // Accounts
    accounts_title: "Account & Security Manager",
    btn_add_offline: "👤 Add Offline Account",
    btn_add_microsoft: "🟩 Sign in with Microsoft",
    acc_active_badge: "✓ ACTIVE",
    btn_switch_acc: "Switch to this Account",
    btn_remove_acc: "Remove Account",
    modal_offline_title: "Add Offline Player",
    offline_name_ph: "Player Username (e.g. Steve, Alex)",

    // Gallery
    gallery_title: "In-Game Screenshots",
    gallery_desc: "All screenshot captures taken in Minecraft using F2.",
    btn_copy_image: "Copy to Clipboard",

    // Settings
    settings_title: "Advanced Launcher Settings",
    lang_select_label: "Launcher Language",
    jvm_flags_label: "JVM Optimization Flags",
    jvm_preset_aikar: "Aikar Flags (Maximum FPS & Smoothness)",
    jvm_preset_zgc: "ZGC Ultra Low-Latency (Java 17/21+)",
    jvm_preset_default: "Standard JVM Parameters",
    java_path_label: "Custom Java Executable Path",
    java_detect_btn: "Auto Detect",
    security_pin_label: "Launcher Security PIN",
    btn_save_settings: "Save Settings",

    // Crash Log
    crash_title: "⚠️ Minecraft Unexpectedly Exited!",
    crash_cause: "Detected Probable Cause:",
    crash_log_label: "Crash Report & Error Details:",
    btn_copy_crash: "Copy Report",
    btn_open_crash_dir: "Open Crash Folder",

    // Quick folders
    quick_folders: "Quick Access Folders",
    toast_copied: "Copied to clipboard!",
    toast_saved: "Settings successfully saved!"
  },

  ru: {
    // Навигация
    nav_play: "ИГРАТЬ",
    nav_instances: "ПРОФИЛИ",
    nav_modrinth: "ОБЗОР (МОДЫ)",
    nav_mods: "МЕНЕДЖЕР МОДОВ",
    nav_stats: "СТАТИСТИКА",
    nav_accounts: "АККАУНТЫ",
    nav_gallery: "ГАЛЕРЕЯ",
    nav_settings: "НАСТРОЙКИ",
    nav_console: "КОНСОЛЬ",

    // Заголовок и Статус
    badge_ultra: "УЛЬТРА ОПТИМИЗАЦИЯ",
    server_ready: "Лаунчер готов",
    status_ready: "Готов",
    status_offline: "Офлайн",
    btn_launch: "ЗАПУСТИТЬ ИГРУ",
    btn_launching: "ЗАПУСК...",
    btn_running: "ИГРА ЗАПУЩЕНА",

    // Игра
    label_player: "Активный игрок",
    label_version: "Версия Minecraft",
    label_loader: "Загрузчик модов",
    label_ram: "Оперативная память (RAM)",
    label_resolution: "Разрешение экрана",
    label_fullbright: "FullBright (Яркость 100%)",
    label_sodium_opt: "Оптимизация Sodium",
    loader_fabric: "Fabric (Рекомендуется)",
    loader_forge: "Forge (Мод-движок)",
    loader_vanilla: "Vanilla (Чистый)",
    opt_active_badge: "⚡ Sodium Активен",
    skin_3d_title: "3D Предпросмотр Скина",
    skin_anim_walk: "Шаг",
    skin_anim_run: "Бег",
    skin_anim_idle: "Покой",
    skin_anim_wave: "Махать",
    skin_reset_cam: "Сброс камеры",
    quick_open_dir: "Папка .minecraft",

    // Профили
    instances_title: "Изолированные профили (Instances)",
    instances_desc: "Каждый профиль имеет свои отдельные моды, миры и настройки.",
    btn_create_instance: "➕ Создать профиль",
    inst_name: "Имя профиля",
    inst_version: "Версия",
    inst_loader: "Загрузчик",
    inst_ram: "RAM (ГБ)",
    inst_play: "Играть",
    inst_open_folder: "Открыть папку",
    inst_delete: "Удалить",
    modal_inst_title: "Создать новый профиль",
    btn_create: "Создать",
    btn_cancel: "Отмена",

    // Modrinth
    modrinth_title: "Каталог Modrinth",
    modrinth_search_ph: "Поиск тысяч модов, сборок, шейдеров и текстур...",
    cat_mods: "Моды",
    cat_modpacks: "Сборки",
    cat_shaders: "Шейдеры",
    cat_resourcepacks: "Текстуры",
    filter_loader: "Загрузчик:",
    filter_version: "Версия MC:",
    filter_channel: "Канал:",
    sort_downloads: "По загрузкам",
    sort_relevance: "По релевантности",
    sort_newest: "Сначала новые",
    btn_quick_install: "⚡ Быстрая установка",
    btn_choose_ver: "📋 Выбрать версию",

    // Менеджер модов
    installed_title: "Установленные файлы",
    installed_desc: "Включайте, выключайте и удаляйте моды в один клик.",
    tab_installed_mods: "Моды",
    tab_installed_shaders: "Шейдеры",
    tab_installed_resourcepacks: "Текстуры",
    btn_enable: "Включить",
    btn_disable: "Отключить",
    btn_delete: "Удалить",
    btn_open_folder: "Открыть папку",

    // Статистика
    stats_title: "Статистика игры и сессии",
    stat_total_time: "Общее время в игре",
    stat_launches: "Всего запусков",
    stat_last_session: "Последняя игра",
    stat_history_title: "История сессий",
    col_date: "Дата и время",
    col_version: "Версия и профиль",
    col_duration: "Длительность",
    col_status: "Статус",

    // Аккаунты
    accounts_title: "Управление аккаунтами",
    btn_add_offline: "👤 Добавить офлайн-аккаунт",
    btn_add_microsoft: "🟩 Войти через Microsoft",
    acc_active_badge: "✓ АКТИВЕН",
    btn_switch_acc: "Переключиться",
    btn_remove_acc: "Удалить",
    modal_offline_title: "Добавить игрока",
    offline_name_ph: "Никнейм игрока (напр. Steve, Alex)",

    // Галерея
    gallery_title: "Скриншоты из игры",
    gallery_desc: "Все скриншоты, сделанные кнопкой F2 в Minecraft.",
    btn_copy_image: "Копировать",

    // Настройки
    settings_title: "Настройки лаунчера",
    lang_select_label: "Язык лаунчера (Language)",
    jvm_flags_label: "Оптимизация JVM",
    jvm_preset_aikar: "Флаги Aikar (Максимальный FPS)",
    jvm_preset_zgc: "ZGC Низкая задержка (Java 17/21+)",
    jvm_preset_default: "Стандартные параметры",
    java_path_label: "Путь к Java",
    java_detect_btn: "Автоопределение",
    security_pin_label: "PIN-код безопасности",
    btn_save_settings: "Сохранить",

    // Crash Log
    crash_title: "⚠️ Игра неожиданно завершилась!",
    crash_cause: "Вероятная причина:",
    crash_log_label: "Отчёт о сбое и стек ошибок:",
    btn_copy_crash: "Копировать отчёт",
    btn_open_crash_dir: "Открыть папку сбоев",

    // Быстрый доступ
    quick_folders: "Быстрый доступ к папкам",
    toast_copied: "Скопировано в буфер обмена!",
    toast_saved: "Настройки сохранены!"
  }
};

let currentLang = localStorage.getItem("cl_lang") || "tr";

function t(key) {
  if (translations[currentLang] && translations[currentLang][key]) {
    return translations[currentLang][key];
  }
  if (translations["tr"] && translations["tr"][key]) {
    return translations["tr"][key];
  }
  return key;
}

function applyTranslations(lang) {
  currentLang = lang || currentLang;
  localStorage.setItem("cl_lang", currentLang);

  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const val = t(key);
    if (val) {
      if (el.tagName === "INPUT" && el.hasAttribute("placeholder")) {
        el.placeholder = val;
      } else {
        el.textContent = val;
      }
    }
  });

  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    const val = t(key);
    if (val) el.title = val;
  });

  const langSelect = document.getElementById("langSelect");
  if (langSelect) langSelect.value = currentLang;
  const headerLangSelect = document.getElementById("headerLangSelect");
  if (headerLangSelect) headerLangSelect.value = currentLang;
}
