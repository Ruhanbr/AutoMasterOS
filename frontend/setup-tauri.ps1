# ============================================================
# setup-tauri.ps1 — Configura o ambiente para build do Tauri
# Execute uma única vez no computador de desenvolvimento.
# ============================================================

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  AutoMaster — Setup do App Desktop (Tauri)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Verifica Rust ─────────────────────────────────────────
Write-Host "[1/4] Verificando Rust..." -ForegroundColor Yellow
if (Get-Command rustc -ErrorAction SilentlyContinue) {
    $rustVersion = rustc --version
    Write-Host "  ✅ Rust encontrado: $rustVersion" -ForegroundColor Green
} else {
    Write-Host "  ❌ Rust NÃO encontrado. Instalando..." -ForegroundColor Red
    Write-Host "  → Abrindo instalador do Rust (rustup)..." -ForegroundColor Gray
    Start-Process "https://win.rustup.rs/x86_64" -Wait
    Write-Host ""
    Write-Host "  ⚠  Após instalar o Rust, feche este terminal e execute novamente." -ForegroundColor Yellow
    Write-Host "  ⚠  Certifique-se de reiniciar o terminal para que o PATH seja atualizado." -ForegroundColor Yellow
    exit 1
}

# ── 2. Verifica target Windows ───────────────────────────────
Write-Host "[2/4] Verificando target Windows..." -ForegroundColor Yellow
$targets = rustup target list --installed
if ($targets -match "x86_64-pc-windows-msvc") {
    Write-Host "  ✅ Target Windows (MSVC) já instalado." -ForegroundColor Green
} else {
    Write-Host "  → Instalando target Windows MSVC..." -ForegroundColor Gray
    rustup target add x86_64-pc-windows-msvc
    Write-Host "  ✅ Target instalado." -ForegroundColor Green
}

# ── 3. Instala dependências npm (inclui @tauri-apps/cli) ─────
Write-Host "[3/4] Instalando dependências npm..." -ForegroundColor Yellow
Set-Location $PSScriptRoot
npm install
Write-Host "  ✅ Dependências instaladas." -ForegroundColor Green

# ── 4. Gera ícones ───────────────────────────────────────────
Write-Host "[4/4] Verificando ícones..." -ForegroundColor Yellow
$iconSource = "src-tauri\assets\icon.png"
$iconDir    = "src-tauri\icons"

if (-Not (Test-Path $iconDir)) {
    New-Item -ItemType Directory -Path $iconDir | Out-Null
}

if (Test-Path $iconSource) {
    Write-Host "  → Gerando ícones a partir de $iconSource..." -ForegroundColor Gray
    npx tauri icon $iconSource
    Write-Host "  ✅ Ícones gerados com sucesso." -ForegroundColor Green
} else {
    Write-Host "  ⚠  Ícone fonte não encontrado em: $iconSource" -ForegroundColor Yellow
    Write-Host "  → Crie a pasta src-tauri\assets\ e coloque um PNG 1024x1024 chamado icon.png" -ForegroundColor Gray
    Write-Host "  → Depois execute: npx tauri icon src-tauri\assets\icon.png" -ForegroundColor Gray
}

# ── Resultado ────────────────────────────────────────────────
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Setup concluído!" -ForegroundColor Green
Write-Host ""
Write-Host "  Próximos passos:" -ForegroundColor White
Write-Host ""
Write-Host "  Testar em desenvolvimento:" -ForegroundColor Gray
Write-Host "    npm run tauri:dev" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Gerar instalador .exe:" -ForegroundColor Gray
Write-Host "    npm run tauri:build" -ForegroundColor Yellow
Write-Host ""
Write-Host "  O instalador será gerado em:" -ForegroundColor Gray
Write-Host "    src-tauri\target\release\bundle\nsis\AutoMaster_1.0.0_x64-setup.exe" -ForegroundColor Yellow
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
