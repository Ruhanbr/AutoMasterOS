// ─────────────────────────────────────────────────────────────────────────────
// commands.rs — Comandos Tauri chamados pelo frontend Next.js
// ─────────────────────────────────────────────────────────────────────────────

use crate::db;
use crate::AppState;
use serde::{Deserialize, Serialize};
use serde_json::Value;

// ── Tipos de retorno ──────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct SyncStatus {
    pub online: bool,
    pub pending: u32,
    pub last_sync: Option<String>,
    pub server_url: String,
}

#[derive(Debug, Serialize)]
pub struct SyncPullResult {
    pub clients: usize,
    pub machines: usize,
    pub service_orders: usize,
    pub last_sync: String,
}

#[derive(Debug, Serialize)]
pub struct SyncPushResult {
    pub pushed: usize,
    pub failed: usize,
}

// ── Helpers internos ──────────────────────────────────────────────────────────

/// Extrai o array de items de uma resposta paginada do FastAPI.
/// Suporta: { items: [...] } ou diretamente [...].
fn extract_items(response: &Value) -> Vec<Value> {
    if let Some(arr) = response.as_array() {
        return arr.clone();
    }
    if let Some(items) = response.get("items").and_then(|v| v.as_array()) {
        return items.clone();
    }
    vec![]
}

/// Faz GET em uma URL e retorna o JSON parseado.
async fn api_get(client: &reqwest::Client, url: &str, token: &str) -> Result<Value, String> {
    client
        .get(url)
        .bearer_auth(token)
        .send()
        .await
        .map_err(|e| format!("Erro de rede: {}", e))?
        .json::<Value>()
        .await
        .map_err(|e| format!("Erro ao parsear resposta: {}", e))
}

// ── Comando: verificar status de sync ────────────────────────────────────────

#[tauri::command]
pub fn get_sync_status(state: tauri::State<'_, AppState>) -> Result<SyncStatus, String> {
    let conn = state.db.lock().map_err(|e| e.to_string())?;
    let pending = db::pending_count(&conn).unwrap_or(0);
    let last_sync = db::get_meta(&conn, "last_sync");
    let server_url = db::get_meta(&conn, "server_url").unwrap_or_default();
    drop(conn);

    // Testa conectividade de forma síncrona (via header de status HTTP)
    // Usa um timeout curto para não travar a UI
    let online = std::net::TcpStream::connect_timeout(
        &std::net::SocketAddr::from(([8, 8, 8, 8], 53)),
        std::time::Duration::from_secs(1),
    )
    .is_ok();

    Ok(SyncStatus {
        online,
        pending,
        last_sync,
        server_url,
    })
}

// ── Comando: salvar token de autenticação ─────────────────────────────────────

#[tauri::command]
pub fn store_auth_token(
    state: tauri::State<'_, AppState>,
    token: String,
    server_url: String,
) -> Result<(), String> {
    let conn = state.db.lock().map_err(|e| e.to_string())?;
    db::set_meta(&conn, "auth_token", &token).map_err(|e| e.to_string())?;
    db::set_meta(&conn, "server_url", &server_url).map_err(|e| e.to_string())?;
    Ok(())
}

/// Limpa o token (ao fazer logout)
#[tauri::command]
pub fn clear_auth_token(state: tauri::State<'_, AppState>) -> Result<(), String> {
    let conn = state.db.lock().map_err(|e| e.to_string())?;
    db::set_meta(&conn, "auth_token", "").map_err(|e| e.to_string())?;
    Ok(())
}

// ── Comando: PULL — baixar dados do servidor → SQLite ────────────────────────

#[tauri::command]
pub async fn sync_pull(
    state: tauri::State<'_, AppState>,
    server_url: String,
    token: String,
) -> Result<SyncPullResult, String> {
    let base = server_url.trim_end_matches('/');
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;

    // ── 1. Busca clientes ─────────────────────────────────────────────────────
    let clients_resp = api_get(
        &client,
        &format!("{}/api/v1/clients?page_size=500&active_only=false", base),
        &token,
    )
    .await
    .unwrap_or(Value::Array(vec![]));
    let clients = extract_items(&clients_resp);

    // ── 2. Busca máquinas ─────────────────────────────────────────────────────
    let machines_resp = api_get(
        &client,
        &format!("{}/api/v1/machines?page_size=500", base),
        &token,
    )
    .await
    .unwrap_or(Value::Array(vec![]));
    let machines = extract_items(&machines_resp);

    // ── 3. Busca ordens de serviço ────────────────────────────────────────────
    let os_resp = api_get(
        &client,
        &format!("{}/api/v1/service-orders?page_size=500", base),
        &token,
    )
    .await
    .unwrap_or(Value::Array(vec![]));
    let service_orders = extract_items(&os_resp);

    // ── 4. Grava no SQLite (sem await enquanto o lock estiver aberto) ─────────
    let now = chrono::Utc::now().to_rfc3339();
    let result = {
        let conn = state.db.lock().map_err(|e| e.to_string())?;

        for c in &clients {
            db::upsert_cliente(&conn, c).ok();
        }
        for m in &machines {
            db::upsert_maquina(&conn, m).ok();
        }
        for os in &service_orders {
            db::upsert_os(&conn, os).ok();
        }
        db::set_meta(&conn, "last_sync", &now).ok();
        db::set_meta(&conn, "server_url", &server_url).ok();

        SyncPullResult {
            clients: clients.len(),
            machines: machines.len(),
            service_orders: service_orders.len(),
            last_sync: now,
        }
    }; // lock liberado aqui, antes de qualquer .await futuro

    Ok(result)
}

// ── Comando: PUSH — enviar fila offline → servidor ───────────────────────────

#[tauri::command]
pub async fn sync_push(
    state: tauri::State<'_, AppState>,
    server_url: String,
    token: String,
) -> Result<SyncPushResult, String> {
    // Pega itens da fila (lock → dados → libera)
    let items = {
        let conn = state.db.lock().map_err(|e| e.to_string())?;
        db::dequeue_all(&conn).map_err(|e| e.to_string())?
    };

    if items.is_empty() {
        return Ok(SyncPushResult { pushed: 0, failed: 0 });
    }

    let base = server_url.trim_end_matches('/');
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;

    let mut pushed = 0usize;
    let mut failed = 0usize;

    for item in &items {
        let url = format!("{}/api/v1{}", base, item.endpoint);

        let req = match item.method.to_uppercase().as_str() {
            "POST"   => client.post(&url),
            "PUT"    => client.put(&url),
            "PATCH"  => client.patch(&url),
            "DELETE" => client.delete(&url),
            _        => { failed += 1; continue; }
        };

        let body: Value = serde_json::from_str(&item.payload).unwrap_or(Value::Null);

        let result = req
            .bearer_auth(&token)
            .json(&body)
            .send()
            .await;

        // Registra resultado (lock rápido, sem await)
        let conn = state.db.lock().map_err(|e| e.to_string())?;
        match result {
            Ok(resp) if resp.status().is_success() => {
                db::mark_sent(&conn, item.id).ok();
                pushed += 1;
            }
            Ok(resp) => {
                let status = resp.status().to_string();
                db::mark_failed(&conn, item.id, &status).ok();
                failed += 1;
            }
            Err(e) => {
                db::mark_failed(&conn, item.id, &e.to_string()).ok();
                failed += 1;
            }
        }
        drop(conn);
    }

    Ok(SyncPushResult { pushed, failed })
}

// ── Leituras locais (SQLite) ──────────────────────────────────────────────────

/// Retorna clientes do cache local. Compatível com o shape da API.
#[tauri::command]
pub fn local_get_clients(
    state: tauri::State<'_, AppState>,
    search: Option<String>,
) -> Result<Value, String> {
    let conn = state.db.lock().map_err(|e| e.to_string())?;
    let items = db::query_clientes(&conn, search.as_deref())
        .map_err(|e| e.to_string())?;
    let total = items.len();
    Ok(serde_json::json!({
        "items": items,
        "total": total,
        "page": 1,
        "page_size": 200,
        "_offline": true
    }))
}

/// Retorna máquinas do cache local.
#[tauri::command]
pub fn local_get_machines(
    state: tauri::State<'_, AppState>,
    client_id: Option<String>,
) -> Result<Value, String> {
    let conn = state.db.lock().map_err(|e| e.to_string())?;
    let items = db::query_maquinas(&conn, client_id.as_deref())
        .map_err(|e| e.to_string())?;
    let total = items.len();
    Ok(serde_json::json!({
        "items": items,
        "total": total,
        "page": 1,
        "page_size": 200,
        "_offline": true
    }))
}

/// Retorna ordens de serviço do cache local.
#[tauri::command]
pub fn local_get_service_orders(
    state: tauri::State<'_, AppState>,
    status: Option<String>,
) -> Result<Value, String> {
    let conn = state.db.lock().map_err(|e| e.to_string())?;
    let items = db::query_os(&conn, status.as_deref())
        .map_err(|e| e.to_string())?;
    let total = items.len();
    Ok(serde_json::json!({
        "items": items,
        "total": total,
        "page": 1,
        "page_size": 300,
        "_offline": true
    }))
}

// ── Escrita offline (enfileirar para sync) ────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct QueueWriteArgs {
    pub method: String,
    pub endpoint: String,
    pub payload: String,
}

/// Enfileira uma operação de escrita para ser sincronizada quando houver conexão.
/// O frontend chama isso quando uma requisição de escrita falha por falta de rede.
#[tauri::command]
pub fn queue_write(
    state: tauri::State<'_, AppState>,
    method: String,
    endpoint: String,
    payload: String,
) -> Result<i64, String> {
    let conn = state.db.lock().map_err(|e| e.to_string())?;
    let id = db::enqueue(&conn, &method, &endpoint, &payload).map_err(|e| e.to_string())?;
    Ok(id)
}
