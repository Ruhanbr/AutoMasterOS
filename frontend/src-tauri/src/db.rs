// ─────────────────────────────────────────────────────────────────────────────
// db.rs — SQLite local (cache offline + fila de sincronização)
// ─────────────────────────────────────────────────────────────────────────────

use rusqlite::{params, Connection, Result};
use serde_json::Value;
use std::path::PathBuf;

// ── Inicialização ─────────────────────────────────────────────────────────────

/// Abre/cria o banco SQLite e aplica o schema.
pub fn init(db_path: PathBuf) -> Result<Connection> {
    if let Some(parent) = db_path.parent() {
        std::fs::create_dir_all(parent).ok();
    }

    let conn = Connection::open(db_path)?;

    // Otimizações de performance
    conn.execute_batch("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;")?;

    // Schema
    conn.execute_batch("
        -- Metadados da aplicação (last_sync, auth_token, etc.)
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        -- Cache de clientes
        CREATE TABLE IF NOT EXISTS clientes (
            id         TEXT PRIMARY KEY,
            nome       TEXT NOT NULL DEFAULT '',
            cpf_cnpj   TEXT,
            telefone   TEXT,
            data_json  TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes(nome);

        -- Cache de máquinas/veículos
        CREATE TABLE IF NOT EXISTS maquinas (
            id         TEXT PRIMARY KEY,
            cliente_id TEXT,
            placa      TEXT,
            marca      TEXT,
            modelo     TEXT,
            data_json  TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_maquinas_cliente ON maquinas(cliente_id);

        -- Cache de ordens de serviço
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id           TEXT PRIMARY KEY,
            numero       TEXT,
            status       TEXT NOT NULL DEFAULT '',
            cliente_nome TEXT,
            data_json    TEXT NOT NULL,
            updated_at   TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_os_status ON ordens_servico(status);

        -- Fila de escritas offline (sincroniza quando voltar online)
        CREATE TABLE IF NOT EXISTS sync_queue (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            method     TEXT NOT NULL,           -- POST, PUT, PATCH, DELETE
            endpoint   TEXT NOT NULL,           -- ex: /service-orders
            payload    TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            attempts   INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );
    ")?;

    Ok(conn)
}

// ── Meta ──────────────────────────────────────────────────────────────────────

pub fn get_meta(conn: &Connection, key: &str) -> Option<String> {
    conn.query_row(
        "SELECT value FROM meta WHERE key = ?1",
        params![key],
        |row| row.get(0),
    )
    .ok()
}

pub fn set_meta(conn: &Connection, key: &str, value: &str) -> Result<()> {
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        params![key, value],
    )?;
    Ok(())
}

// ── Upsert helpers ────────────────────────────────────────────────────────────

/// Insere ou atualiza um cliente no cache local.
pub fn upsert_cliente(conn: &Connection, row: &Value) -> Result<()> {
    let id = row["id"].as_str().unwrap_or("");
    let nome = row["full_name"].as_str()
        .or_else(|| row["nome"].as_str())
        .unwrap_or("");
    let cpf = row["cpf_cnpj"].as_str()
        .or_else(|| row["document"].as_str());
    let tel = row["phone"].as_str()
        .or_else(|| row["telefone"].as_str());
    let updated = row["updated_at"].as_str().unwrap_or("");

    conn.execute(
        "INSERT INTO clientes(id, nome, cpf_cnpj, telefone, data_json, updated_at)
         VALUES(?1, ?2, ?3, ?4, ?5, ?6)
         ON CONFLICT(id) DO UPDATE SET
           nome       = excluded.nome,
           cpf_cnpj   = excluded.cpf_cnpj,
           telefone   = excluded.telefone,
           data_json  = excluded.data_json,
           updated_at = excluded.updated_at",
        params![id, nome, cpf, tel, row.to_string(), updated],
    )?;
    Ok(())
}

/// Insere ou atualiza uma máquina/veículo no cache local.
pub fn upsert_maquina(conn: &Connection, row: &Value) -> Result<()> {
    let id = row["id"].as_str().unwrap_or("");
    let cliente_id = row["client_id"].as_str()
        .or_else(|| row["cliente_id"].as_str());
    let placa = row["plate"].as_str()
        .or_else(|| row["placa"].as_str());
    let marca = row["brand"].as_str()
        .or_else(|| row["make"].as_str())
        .or_else(|| row["marca"].as_str());
    let modelo = row["model"].as_str()
        .or_else(|| row["modelo"].as_str());
    let updated = row["updated_at"].as_str().unwrap_or("");

    conn.execute(
        "INSERT INTO maquinas(id, cliente_id, placa, marca, modelo, data_json, updated_at)
         VALUES(?1, ?2, ?3, ?4, ?5, ?6, ?7)
         ON CONFLICT(id) DO UPDATE SET
           cliente_id = excluded.cliente_id,
           placa      = excluded.placa,
           marca      = excluded.marca,
           modelo     = excluded.modelo,
           data_json  = excluded.data_json,
           updated_at = excluded.updated_at",
        params![id, cliente_id, placa, marca, modelo, row.to_string(), updated],
    )?;
    Ok(())
}

/// Insere ou atualiza uma OS no cache local.
pub fn upsert_os(conn: &Connection, row: &Value) -> Result<()> {
    let id = row["id"].as_str().unwrap_or("");
    let numero = row["order_number"].as_str()
        .or_else(|| row["numero"].as_str());
    let status = row["status"].as_str().unwrap_or("UNKNOWN");
    let cliente_nome = row["client_name"].as_str()
        .or_else(|| row["cliente_nome"].as_str())
        .or_else(|| row["client"]["full_name"].as_str());
    let updated = row["updated_at"].as_str().unwrap_or("");

    conn.execute(
        "INSERT INTO ordens_servico(id, numero, status, cliente_nome, data_json, updated_at)
         VALUES(?1, ?2, ?3, ?4, ?5, ?6)
         ON CONFLICT(id) DO UPDATE SET
           numero       = excluded.numero,
           status       = excluded.status,
           cliente_nome = excluded.cliente_nome,
           data_json    = excluded.data_json,
           updated_at   = excluded.updated_at",
        params![id, numero, status, cliente_nome, row.to_string(), updated],
    )?;
    Ok(())
}

// ── Queries ───────────────────────────────────────────────────────────────────

pub fn query_clientes(conn: &Connection, search: Option<&str>) -> Result<Vec<Value>> {
    let sql = match search {
        Some(_) => "SELECT data_json FROM clientes WHERE nome LIKE ?1 OR cpf_cnpj LIKE ?1 ORDER BY nome LIMIT 200",
        None    => "SELECT data_json FROM clientes ORDER BY nome LIMIT 200",
    };

    let pattern = search.map(|s| format!("%{}%", s));
    let mut stmt = conn.prepare(sql)?;

    let rows = if let Some(ref p) = pattern {
        stmt.query_map(params![p], |row| row.get::<_, String>(0))?
            .filter_map(|r| r.ok())
            .filter_map(|s| serde_json::from_str(&s).ok())
            .collect()
    } else {
        stmt.query_map([], |row| row.get::<_, String>(0))?
            .filter_map(|r| r.ok())
            .filter_map(|s| serde_json::from_str(&s).ok())
            .collect()
    };

    Ok(rows)
}

pub fn query_maquinas(conn: &Connection, client_id: Option<&str>) -> Result<Vec<Value>> {
    let sql = match client_id {
        Some(_) => "SELECT data_json FROM maquinas WHERE cliente_id = ?1 ORDER BY marca, modelo LIMIT 200",
        None    => "SELECT data_json FROM maquinas ORDER BY marca, modelo LIMIT 200",
    };

    let mut stmt = conn.prepare(sql)?;

    let rows = if let Some(cid) = client_id {
        stmt.query_map(params![cid], |row| row.get::<_, String>(0))?
            .filter_map(|r| r.ok())
            .filter_map(|s| serde_json::from_str(&s).ok())
            .collect()
    } else {
        stmt.query_map([], |row| row.get::<_, String>(0))?
            .filter_map(|r| r.ok())
            .filter_map(|s| serde_json::from_str(&s).ok())
            .collect()
    };

    Ok(rows)
}

pub fn query_os(conn: &Connection, status: Option<&str>) -> Result<Vec<Value>> {
    let sql = match status {
        Some(_) => "SELECT data_json FROM ordens_servico WHERE status = ?1 ORDER BY updated_at DESC LIMIT 300",
        None    => "SELECT data_json FROM ordens_servico ORDER BY updated_at DESC LIMIT 300",
    };

    let mut stmt = conn.prepare(sql)?;

    let rows = if let Some(s) = status {
        stmt.query_map(params![s], |row| row.get::<_, String>(0))?
            .filter_map(|r| r.ok())
            .filter_map(|j| serde_json::from_str(&j).ok())
            .collect()
    } else {
        stmt.query_map([], |row| row.get::<_, String>(0))?
            .filter_map(|r| r.ok())
            .filter_map(|j| serde_json::from_str(&j).ok())
            .collect()
    };

    Ok(rows)
}

// ── Sync Queue ────────────────────────────────────────────────────────────────

pub fn enqueue(conn: &Connection, method: &str, endpoint: &str, payload: &str) -> Result<i64> {
    let now = chrono::Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO sync_queue(method, endpoint, payload, created_at) VALUES(?1, ?2, ?3, ?4)",
        params![method, endpoint, payload, now],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn pending_count(conn: &Connection) -> Result<u32> {
    conn.query_row(
        "SELECT COUNT(*) FROM sync_queue",
        [],
        |row| row.get::<_, u32>(0),
    )
}

#[derive(Debug)]
pub struct QueueItem {
    pub id: i64,
    pub method: String,
    pub endpoint: String,
    pub payload: String,
    pub attempts: u32,
}

pub fn dequeue_all(conn: &Connection) -> Result<Vec<QueueItem>> {
    let mut stmt = conn.prepare(
        "SELECT id, method, endpoint, payload, attempts FROM sync_queue ORDER BY id ASC",
    )?;

    let items = stmt
        .query_map([], |row| {
            Ok(QueueItem {
                id:       row.get(0)?,
                method:   row.get(1)?,
                endpoint: row.get(2)?,
                payload:  row.get(3)?,
                attempts: row.get(4)?,
            })
        })?
        .filter_map(|r| r.ok())
        .collect();

    Ok(items)
}

pub fn mark_sent(conn: &Connection, id: i64) -> Result<()> {
    conn.execute("DELETE FROM sync_queue WHERE id = ?1", params![id])?;
    Ok(())
}

pub fn mark_failed(conn: &Connection, id: i64, error: &str) -> Result<()> {
    conn.execute(
        "UPDATE sync_queue SET attempts = attempts + 1, last_error = ?2 WHERE id = ?1",
        params![id, error],
    )?;
    Ok(())
}
