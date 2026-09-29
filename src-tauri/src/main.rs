// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::net::TcpStream;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

static BACKEND_CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// Calisan backend'in guncel API surumune sahip olup olmadigini kontrol eder.
/// Eski/stale bir Python sureci portu tutuyorsa yeni backend baslatilir (18421+).
fn backend_health_ok() -> bool {
    let addr = match "127.0.0.1:18420".parse() {
        Ok(a) => a,
        Err(_) => return false,
    };
    let mut stream = match TcpStream::connect_timeout(&addr, Duration::from_millis(400)) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(800)));
    if stream
        .write_all(b"GET /api/health HTTP/1.0\r\nHost: 127.0.0.1:18420\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut response = String::new();
    let _ = stream.read_to_string(&mut response);
    // Backend surumu degistiginde bu deger GUNCELLENMELI (backend/server.py API_VERSION ile ayni).
    response.contains("\"api_version\": 14") || response.contains("\"api_version\":14")
}

/// Backend'in bulunabilecegi tum kok dizinleri dondurur.
/// Gelistirme, kurulu uygulama (NSIS/deb/AppImage) ve resource konumlarini kapsar.
fn search_roots() -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            roots.push(dir.to_path_buf());
            roots.push(dir.join("resources"));
            // macOS .app paketi: Tauri kaynaklari Contents/Resources icine
            // koyar (ornek: CookieLauncher.app/Contents/Resources/backend/
            // cookielauncher-core). Bu yol olmadan macOS'ta gomulu cekirdek
            // bulunamayip python3'e dusuluyor, macOS'ta sistem python3
            // olmadigi icin backend HIC baslamiyordu.
            if let Some(contents) = dir.parent() {
                roots.push(contents.join("Resources"));
                roots.push(contents.join("Resources").join("backend"));
            }
            // target/release -> target -> src-tauri -> proje koku
            if let Some(p1) = dir.parent() {
                if let Some(p2) = p1.parent() {
                    if let Some(p3) = p2.parent() {
                        roots.push(p3.to_path_buf());
                    }
                }
            }
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        roots.push(cwd.clone());
        roots.push(cwd.join(".."));
    }

    roots.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(".."));

    // Linux paket kurulumlari (deb/AppImage)
    if let Ok(appdir) = std::env::var("APPDIR") {
        roots.push(PathBuf::from(&appdir).join("usr/lib"));
        roots.push(PathBuf::from(&appdir).join("usr/lib/CookieLauncher"));
    }
    roots.push(PathBuf::from("/usr/lib/CookieLauncher"));
    roots.push(PathBuf::from("/usr/lib/cookie-launcher"));

    roots
}

/// PyInstaller ile paketlenmis standalone backend calistirilabilirini arar.
fn find_backend_binary() -> Option<PathBuf> {
    let names: &[&str] = if cfg!(windows) {
        &["cookielauncher-core.exe", "cookie-launcher-core.exe"]
    } else {
        &["cookielauncher-core", "cookie-launcher-core"]
    };

    for root in search_roots() {
        for sub in ["backend", "resources/backend", "resources", ""] {
            for name in names {
                let candidate = if sub.is_empty() {
                    root.join(name)
                } else {
                    root.join(sub).join(name)
                };
                if candidate.is_file() {
                    return Some(candidate);
                }
            }
        }
    }
    None
}

/// Python ile calistirilacak backend script'ini arar (paketlenmis exe yoksa yedek).
fn find_backend_script() -> Option<PathBuf> {
    for root in search_roots() {
        for sub in ["backend/server.py", "../backend/server.py"] {
            let candidate = root.join(sub);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

/// Platforma gore Python komut adaylari (Windows: py -3, python, python3).
fn python_candidates() -> Vec<(&'static str, Vec<&'static str>)> {
    if cfg!(windows) {
        vec![("py", vec!["-3"]), ("python", vec![]), ("python3", vec![])]
    } else {
        vec![("python3", vec![]), ("python", vec![])]
    }
}

fn spawn_backend(command: &mut Command) -> std::io::Result<Child> {
    #[cfg(windows)]
    {
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command.spawn()
}

fn start_backend_if_needed() {
    if backend_health_ok() {
        println!("CookieLauncher backend API is already running.");
        return;
    }

    // 1. Tercih: paketlenmis standalone core (Python gerektirmez)
    if let Some(binary) = find_backend_binary() {
        println!("Starting bundled CookieLauncher core: {:?}", binary);
        let bin_str = binary.to_string_lossy().to_string();
        let mut cmd = Command::new(&bin_str);
        if let Some(parent) = binary.parent() {
            cmd.current_dir(parent);
        }
        match spawn_backend(&mut cmd) {
            Ok(child) => {
                if let Ok(mut lock) = BACKEND_CHILD.lock() {
                    *lock = Some(child);
                }
                println!("Bundled backend successfully spawned.");
                return;
            }
            Err(e) => eprintln!("Bundled backend baslatilamadi, Python denenecek: {e}"),
        }
    }

    // 2. Yedek: Python script (python3 / python / py -3)
    let script = match find_backend_script() {
        Some(s) => s,
        None => {
            eprintln!("CookieLauncher backend bulunamadi (cookielauncher-core veya backend/server.py).");
            eprintln!("Aranan kok dizinler: {:?}", search_roots());
            eprintln!("Platform: {}", std::env::consts::OS);
            return;
        }
    };

    let working_dir = script
        .parent()
        .and_then(|p| p.parent())
        .map(|p| p.to_path_buf());

    for (program, prefix) in python_candidates() {
        let mut args: Vec<String> = prefix.iter().map(|s| s.to_string()).collect();
        args.push(script.to_string_lossy().to_string());

        let mut cmd = Command::new(program);
        cmd.args(&args);
        if let Some(dir) = &working_dir {
            cmd.current_dir(dir);
        }

        match spawn_backend(&mut cmd) {
            Ok(child) => {
                if let Ok(mut lock) = BACKEND_CHILD.lock() {
                    *lock = Some(child);
                }
                println!("Backend spawned with '{}' -> {:?}", program, script);
                return;
            }
            Err(_) => continue,
        }
    }

    eprintln!("Backend baslatilamadi: paketlenmis core yok ve Python bulunamadi.");
}

fn cleanup_backend() {
    if let Ok(mut lock) = BACKEND_CHILD.lock() {
        if let Some(mut child) = lock.take() {
            let _ = child.kill();
        }
    }
}

fn main() {
    start_backend_if_needed();

    tauri::Builder::default()
        .setup(|_app| Ok(()))
        .run(tauri::generate_context!())
        .expect("Tauri uygulaması başlatılırken hata oluştu");

    cleanup_backend();
}
