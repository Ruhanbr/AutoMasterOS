// ─────────────────────────────────────────────────────────────────────────────
// lib.rs — Entry point da biblioteca Tauri
// ─────────────────────────────────────────────────────────────────────────────

mod commands;
mod db;

use serde::{Deserialize, Serialize};
use std::{fs, path::PathBuf, sync::Mutex};
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WebviewUrl, WebviewWindowBuilder,
};

// ── Estado global do app (compartilhado entre comandos) ───────────────────────

pub struct AppState {
    /// Conexão SQLite local (wrapped em Mutex pois rusqlite::Connection é !Sync)
    pub db: Mutex<rusqlite::Connection>,
}

// ── Configuração do servidor (arquivo JSON em %APPDATA%) ─────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AppConfig {
    pub server_url: String,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            server_url: "http://localhost:3000".to_string(),
        }
    }
}

fn config_path(app: &tauri::AppHandle) -> PathBuf {
    app.path()
        .app_config_dir()
        .expect("Falha ao obter diretório de configuração")
        .join("config.json")
}

fn db_path(app: &tauri::AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .expect("Falha ao obter diretório de dados")
        .join("automaster.db")
}

fn load_config(app: &tauri::AppHandle) -> AppConfig {
    let path = config_path(app);
    fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_config_to_disk(app: &tauri::AppHandle, config: &AppConfig) -> Result<(), String> {
    let path = config_path(app);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(config).map_err(|e| e.to_string())?;
    fs::write(path, json).map_err(|e| e.to_string())?;
    Ok(())
}

// ── Comandos de configuração (página de setup) ────────────────────────────────

#[tauri::command]
fn get_server_url(app: tauri::AppHandle) -> String {
    load_config(&app).server_url
}

#[tauri::command]
fn save_and_navigate(app: tauri::AppHandle, url: String) -> Result<(), String> {
    let normalized = if url.starts_with("http://") || url.starts_with("https://") {
        url.trim_end_matches('/').to_string()
    } else {
        format!("http://{}", url.trim_end_matches('/'))
    };

    let parsed: url::Url = normalized
        .parse()
        .map_err(|e: url::ParseError| format!("URL inválida: {}", e))?;

    save_config_to_disk(&app, &AppConfig { server_url: normalized.clone() })?;

    if let Some(main_win) = app.get_webview_window("main") {
        main_win.navigate(parsed).map_err(|e| e.to_string())?;
    }

    if let Some(settings_win) = app.get_webview_window("settings") {
        let _ = settings_win.close();
    }

    Ok(())
}

// ── Entry point ───────────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        // Registra todos os comandos disponíveis para o frontend
        .invoke_handler(tauri::generate_handler![
            // Configuração
            get_server_url,
            save_and_navigate,
            // Auth / token
            commands::store_auth_token,
            commands::clear_auth_token,
            // Status de sincronização
            commands::get_sync_status,
            // Sync com servidor
            commands::sync_pull,
            commands::sync_push,
            // Leituras locais (offline)
            commands::local_get_clients,
            commands::local_get_machines,
            commands::local_get_service_orders,
            // Escrita offline (enfileirar)
            commands::queue_write,
        ])
        .setup(|app| {
            // ── Inicializa banco SQLite ────────────────────────────────────────
            let db_file = db_path(&app.handle());
            let conn = db::init(db_file).expect("Falha ao inicializar banco local");
            app.manage(AppState { db: Mutex::new(conn) });

            // ── Carrega configuração ──────────────────────────────────────────
            let config = load_config(&app.handle());
            let config_exists = config_path(&app.handle()).exists();

            let initial_url = if !config_exists {
                WebviewUrl::App("index.html".into())
            } else {
                WebviewUrl::External(
                    config
                        .server_url
                        .parse()
                        .unwrap_or_else(|_| "http://localhost:3000".parse().unwrap()),
                )
            };

            // ── Janela principal ──────────────────────────────────────────────
            WebviewWindowBuilder::new(app, "main", initial_url)
                .title("AutoMaster")
                .inner_size(1280.0, 800.0)
                .min_inner_size(1024.0, 600.0)
                .resizable(true)
                .center()
                .build()?;

            // ── Bandeja do sistema ────────────────────────────────────────────
            let settings_item = MenuItem::with_id(
                app,
                "settings",
                "⚙  Configurações do Servidor",
                true,
                None::<&str>,
            )?;
            let sync_item =
                MenuItem::with_id(app, "sync", "↕  Sincronizar Agora", true, None::<&str>)?;
            let reload_item =
                MenuItem::with_id(app, "reload", "↻  Recarregar", true, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(app)?;
            let quit_item =
                MenuItem::with_id(app, "quit", "✕  Sair do AutoMaster", true, None::<&str>)?;

            let tray_menu = Menu::with_items(
                app,
                &[&settings_item, &sync_item, &reload_item, &separator, &quit_item],
            )?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().cloned().unwrap())
                .menu(&tray_menu)
                .tooltip("AutoMaster — Sistema de Oficinas")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        app.exit(0);
                    }
                    "settings" => {
                        if let Some(existing) = app.get_webview_window("settings") {
                            let _ = existing.set_focus();
                        } else {
                            let _ = WebviewWindowBuilder::new(
                                app,
                                "settings",
                                WebviewUrl::App("index.html".into()),
                            )
                            .title("AutoMaster — Configurações")
                            .inner_size(520.0, 480.0)
                            .resizable(false)
                            .center()
                            .build();
                        }
                    }
                    "sync" => {
                        // Dispara sync via JavaScript na janela principal
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.eval("window.__AUTOMASTER_SYNC && window.__AUTOMASTER_SYNC()");
                        }
                    }
                    "reload" => {
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.eval("window.location.reload()");
                        }
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(win) = app.get_webview_window("main") {
                            if win.is_visible().unwrap_or(false) {
                                let _ = win.set_focus();
                            } else {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Erro ao iniciar AutoMaster");
}
