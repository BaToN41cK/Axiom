//! AXIOM desktop shell.
//!
//! Spawns the real Python core (ChatSession: Ollama, streaming, tools,
//! history) as a JSONL stdio subprocess and shuttles requests/events between
//! the Tauri webview and that process.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager, State};

struct Bridge {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<std::process::ChildStdin>>,
}

fn find_root() -> PathBuf {
    if let Ok(env_root) = std::env::var("AXIOM_DESKTOP_ROOT") {
        return PathBuf::from(env_root);
    }
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.clone());
        if let Some(parent) = cwd.parent() {
            candidates.push(parent.to_path_buf());
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            // dev build: <root>/desktop/src-tauri/target/debug
            for ancestor in dir.ancestors().skip(1).take(5) {
                candidates.push(ancestor.to_path_buf());
            }
        }
    }
    for candidate in candidates {
        if candidate.join("desktop/src-tauri/bridge/axiom_bridge.py").exists() {
            return candidate;
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn find_python() -> String {
    if let Ok(py) = std::env::var("AXIOM_PYTHON") {
        if !py.trim().is_empty() {
            return py;
        }
    }
    // A repository virtualenv already has the `axiom` package installed
    // (`pip install -e .`), so prefer it over whatever is first on PATH.
    let root = find_root();
    for rel in [
        ".venv/Scripts/python.exe",
        ".venv/bin/python",
        "venv/Scripts/python.exe",
        "venv/bin/python",
    ] {
        let candidate = root.join(rel);
        if candidate.exists() {
            return candidate.to_string_lossy().to_string();
        }
    }
    for candidate in ["python.exe", "python", "py"] {
        if Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok()
        {
            return candidate.to_string();
        }
    }
    "python".to_string()
}



fn spawn_bridge(app: &AppHandle) -> Result<(), String> {
    let python = find_python();
    // 1. Repository layout (dev): <root>/desktop/src-tauri/bridge/axiom_bridge.py
    // 2. Bundled layout (installed): the bridge script ships as a Tauri
    //    resource (tauri.conf.json `bundle.resources`) next to the exe.
    let mut bridge_py: Option<PathBuf> = None;
    let mut src_dir: Option<PathBuf> = None;
    let repo_root = find_root();
    let repo_bridge = repo_root.join("desktop/src-tauri/bridge/axiom_bridge.py");
    if repo_bridge.exists() {
        bridge_py = Some(repo_bridge);
        src_dir = Some(repo_root.join("src"));
    }
    if bridge_py.is_none() {
        if let Ok(resource_dir) = app.path().resource_dir() {
            let bundled = resource_dir.join("bridge/axiom_bridge.py");
            if bundled.exists() {
                bridge_py = Some(bundled);
            }
        }
    }
    let bridge_py = bridge_py
        .ok_or_else(|| "bridge script not found (repo layout and bundled resources)".to_string())?;

    let mut cmd = Command::new(&python);
    cmd.arg("-u").arg(&bridge_py);
    if let Some(src) = src_dir {
        // Repository layout: import the working-tree package. An installed
        // bundle has no src/ — the `axiom` package must be installed in the
        // Python environment (see docs/gui.md).
        cmd.env("PYTHONPATH", &src);
    }
    // Give the core a private data home unless the user already set one.
    if std::env::var("AXIOM_HOME").is_err() {
        let home = std::env::var("AXIOM_DESKTOP_ROOT")
            .map(|root| PathBuf::from(root).join("desktop/data"))
            .unwrap_or_else(|_| repo_root.join("desktop/data"));
        if home.parent().is_some() && home.parent().map(|p| p.exists()).unwrap_or(false) {
            let _ = std::fs::create_dir_all(&home);
            cmd.env("AXIOM_HOME", &home);
        }
        // Bundled installs without a repo layout keep the default ~/.axiom.
    }
    cmd.env("PYTHONIOENCODING", "utf-8");
    cmd.env("PYTHONUTF8", "1");
    // Workspace filesystem tools operate on the project AXIOM was launched from
    // (the repo root found above) unless the user set an explicit workspace.
    if std::env::var("AXIOM_WORKSPACE").is_err() {
        cmd.env("AXIOM_WORKSPACE", &repo_root);
    }
    cmd.stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("failed to start Python core ({}): {}", python, e))?;
    let stdin = child
        .stdin
        .take()
        .ok_or_else(|| "no stdin for bridge".to_string())?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "no stdout for bridge".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "no stderr for bridge".to_string())?;

    // Forward every core line to the webview.
    let emitter = app.clone();
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines().map_while(Result::ok) {
            let payload: Value = match serde_json::from_str(&line) {
                Ok(v) => v,
                Err(_) => Value::String(line.clone()),
            };
            let _ = emitter.emit("bridge://line", payload);
        }
        let _ = emitter.emit(
            "bridge://line",
            serde_json::json!({
                "type": "reply",
                "req": 0,
                "ok": false,
                "error": "bridge-exited"
            }),
        );
    });

    let err_app = app.clone();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stderr);
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    let text = String::from_utf8_lossy(&buf[..n]).to_string();
                    let _ = err_app.emit("bridge://stderr", text);
                }
            }
        }
    });

    let state: State<Bridge> = app.state();
    *state.child.lock().unwrap() = Some(child);
    *state.stdin.lock().unwrap() = Some(stdin);
    Ok(())
}

#[tauri::command]
fn bridge_request(state: State<'_, Bridge>, payload: Value) -> Result<Value, String> {
    let mut guard = state.stdin.lock().unwrap();
    let stdin = guard
        .as_mut()
        .ok_or_else(|| "bridge is not running".to_string())?;
    let mut line = serde_json::to_string(&payload).map_err(|e| e.to_string())?;
    line.push('\n');
    stdin
        .write_all(line.as_bytes())
        .and_then(|_| stdin.flush())
        .map_err(|e| format!("bridge write failed: {}", e))?;
    Ok(Value::Null)
}

#[tauri::command]
fn bridge_restart(app: AppHandle) -> Result<(), String> {
    {
        let state: State<Bridge> = app.state();
        if let Some(child) = state.child.lock().unwrap().as_mut() {
            let _ = child.kill();
        }
        *state.child.lock().unwrap() = None;
        *state.stdin.lock().unwrap() = None;
    }
    std::thread::sleep(std::time::Duration::from_millis(300));
    spawn_bridge(&app)
}

/// Open an http(s) link in the user's real browser.
///
/// The webview must never navigate away from the app, and AXIOM ships no
/// browser plugin, so links are handed to the OS directly.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    let lower = url.trim().to_ascii_lowercase();
    if !(lower.starts_with("http://") || lower.starts_with("https://") || lower.starts_with("mailto:")) {
        return Err("only http(s) and mailto links can be opened".to_string());
    }
    let target = url.trim().to_string();
    #[cfg(target_os = "windows")]
    let spawn = Command::new("cmd")
        .args(["/C", "start", "", &target])
        .spawn();
    #[cfg(target_os = "macos")]
    let spawn = Command::new("open").arg(&target).spawn();
    #[cfg(all(unix, not(target_os = "macos")))]
    let spawn = Command::new("xdg-open").arg(&target).spawn();
    spawn.map(|_| ()).map_err(|e| format!("could not open the link: {e}"))
}

/// Open a native folder picker and return the chosen directory (if any).
#[tauri::command]
fn pick_folder(app: AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let selection = app
        .dialog()
        .file()
        .set_title("Открыть проект — выбрать папку")
        .blocking_pick_folder();
    Ok(selection.map(|p| p.to_string()))
}

/// Close AXIOM (used by the `/exit` command and the window-close shortcut).
#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let handle = app.handle().clone();
            app.manage(Bridge {
                child: Mutex::new(None),
                stdin: Mutex::new(None),
            });
            if let Err(err) = spawn_bridge(&handle) {
                eprintln!("bridge startup error: {err}");
                let _ = handle.emit("bridge://stderr", err.clone());
                // Unblock any pending frontend requests instead of hanging.
                let _ = handle.emit(
                    "bridge://line",
                    serde_json::json!({
                        "type": "reply",
                        "req": 0,
                        "ok": false,
                        "error": format!("bridge-exited: {err}")
                    }),
                );
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<Bridge>();
                let mut guard = state.child.lock().unwrap();
                if let Some(child) = guard.as_mut() {
                    let _ = child.kill();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            bridge_request,
            bridge_restart,
            open_url,
            pick_folder,
            quit_app
        ])
        .run(tauri::generate_context!())
        .expect("error while running AXIOM");
}

