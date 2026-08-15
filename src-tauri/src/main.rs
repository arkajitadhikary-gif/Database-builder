#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use rand::{distr::Alphanumeric, Rng};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, State};

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: &str = "8765";
const HEALTH_URL: &str = "http://127.0.0.1:8765/api/v1/health/live";

struct BackendProcess {
    child: Mutex<Option<Child>>,
    session_token: String,
}

impl BackendProcess {
    fn new() -> Self {
        let session_token = rand::rng()
            .sample_iter(Alphanumeric)
            .take(64)
            .map(char::from)
            .collect();
        Self {
            child: Mutex::new(None),
            session_token,
        }
    }

    fn terminate(&self) {
        if let Ok(mut child) = self.child.lock() {
            if let Some(mut running) = child.take() {
                let _ = running.kill();
                let _ = running.wait();
            }
        }
    }
}

#[tauri::command]
fn backend_session_token(state: State<'_, BackendProcess>) -> String {
    state.session_token.clone()
}

fn backend_executable(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(configured) = std::env::var("JUDICORE_BACKEND_EXECUTABLE") {
        return Ok(PathBuf::from(configured));
    }
    let resource_dir = app.path().resource_dir().map_err(|err| err.to_string())?;
    let filename = if cfg!(target_os = "windows") {
        "judicore-backend.exe"
    } else {
        "judicore-backend"
    };
    Ok(resource_dir.join("resources").join("backend").join(filename))
}

fn launch_backend(app: &AppHandle, process: &BackendProcess) -> Result<(), String> {
    let executable = backend_executable(app)?;
    if !executable.exists() {
        return Err(format!(
            "FastAPI sidecar not found at {}. Build it with the documented PyInstaller step and package it under resources/backend.",
            executable.display()
        ));
    }
    let data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    std::fs::create_dir_all(data_dir.join("reference"))
        .map_err(|err| format!("unable to create reference storage: {err}"))?;
    std::fs::create_dir_all(data_dir.join("archive"))
        .map_err(|err| format!("unable to create archive storage: {err}"))?;
    let packaged_model = app
        .path()
        .resource_dir()
        .map_err(|err| err.to_string())?
        .join("resources")
        .join("backend")
        .join("models");
    let mut command = Command::new(&executable);
    command
        .args(["--host", BACKEND_HOST, "--port", BACKEND_PORT])
        .env("SESSION_TOKEN", &process.session_token)
        .env("JUDICORE_SESSION_TOKEN", &process.session_token)
        .env("REFERENCE_ROOT", data_dir.join("reference"))
        .env("ARCHIVE_ROOT", data_dir.join("archive"));
    if packaged_model.exists() {
        command.env("EMBEDDING_MODEL", packaged_model);
    }
    let child = command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|err| format!("unable to start FastAPI sidecar: {err}"))?;
    *process
        .child
        .lock()
        .map_err(|_| "backend process lock poisoned".to_string())? = Some(child);

    let deadline = Instant::now() + Duration::from_secs(30);
    let client = reqwest::blocking::Client::new();
    while Instant::now() < deadline {
        if let Ok(response) = client
            .get(HEALTH_URL)
            .bearer_auth(&process.session_token)
            .timeout(Duration::from_secs(2))
            .send()
        {
            if response.status().is_success() {
                return Ok(());
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
    process.terminate();
    Err("FastAPI sidecar did not become healthy within 30 seconds".to_string())
}

fn main() {
    let backend = BackendProcess::new();
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(backend)
        .invoke_handler(tauri::generate_handler![backend_session_token])
        .setup(|app| {
            let state = app.state::<BackendProcess>();
            launch_backend(&app.handle(), &state)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Judicore")
        .run(|app_handle, event| {
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                if let Some(process) = app_handle.try_state::<BackendProcess>() {
                    process.terminate();
                }
            }
        });
}
