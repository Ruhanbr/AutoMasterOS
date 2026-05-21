'use client';

import { useEffect, useState, useCallback } from 'react';
import { WifiOff, RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';
import { isTauri, getSyncStatus, syncAll, type SyncStatus } from '@/lib/offline';
import { getAccessToken } from '@/lib/auth';

type SyncState = 'idle' | 'syncing' | 'success' | 'error';

export function OfflineBar() {
  const [online, setOnline] = useState(true);
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [syncState, setSyncState] = useState<SyncState>('idle');
  const [isDesktop, setIsDesktop] = useState(false);

  // Só mostra no app Tauri
  useEffect(() => {
    setIsDesktop(isTauri());
  }, []);

  // Monitora status de rede do navegador
  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    setOnline(navigator.onLine);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  // Consulta status do Tauri periodicamente
  useEffect(() => {
    if (!isDesktop) return;

    const poll = async () => {
      const s = await getSyncStatus();
      if (s) setStatus(s);
    };

    poll();
    const interval = setInterval(poll, 30_000); // a cada 30s
    return () => clearInterval(interval);
  }, [isDesktop]);

  // Quando voltar online, faz sync automático
  useEffect(() => {
    if (!isDesktop || !online) return;
    if (!status?.pending) return;

    handleSync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, isDesktop]);

  // Registra função global para o tray menu "Sincronizar Agora"
  useEffect(() => {
    if (!isDesktop) return;
    (window as typeof window & { __AUTOMASTER_SYNC?: () => void }).__AUTOMASTER_SYNC = handleSync;
    return () => {
      delete (window as typeof window & { __AUTOMASTER_SYNC?: () => void }).__AUTOMASTER_SYNC;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDesktop]);

  const handleSync = useCallback(async () => {
    const token = getAccessToken();
    const serverUrl = status?.server_url || process.env.NEXT_PUBLIC_API_URL?.replace('/api/v1', '') || 'http://localhost:8000';
    if (!token || !serverUrl) return;

    setSyncState('syncing');
    try {
      await syncAll(serverUrl, token);
      setSyncState('success');
      const s = await getSyncStatus();
      if (s) setStatus(s);
    } catch {
      setSyncState('error');
    } finally {
      setTimeout(() => setSyncState('idle'), 3000);
    }
  }, [status?.server_url]);

  // Não renderiza nada no browser comum ou quando está online sem pendências
  if (!isDesktop) return null;
  if (online && (!status?.pending || status.pending === 0) && syncState === 'idle') return null;

  return (
    <div
      className={`
        fixed bottom-0 left-0 right-0 z-50 flex items-center justify-between
        px-4 py-2 text-sm font-medium shadow-lg transition-all
        ${!online
          ? 'bg-amber-950 border-t border-amber-800 text-amber-200'
          : syncState === 'error'
          ? 'bg-red-950 border-t border-red-800 text-red-200'
          : syncState === 'success'
          ? 'bg-emerald-950 border-t border-emerald-800 text-emerald-200'
          : 'bg-blue-950 border-t border-blue-800 text-blue-200'
        }
      `}
    >
      {/* Ícone + mensagem */}
      <div className="flex items-center gap-2">
        {!online && <WifiOff className="w-4 h-4 shrink-0" />}
        {syncState === 'syncing' && (
          <RefreshCw className="w-4 h-4 shrink-0 animate-spin" />
        )}
        {syncState === 'success' && <CheckCircle2 className="w-4 h-4 shrink-0" />}
        {syncState === 'error' && <AlertCircle className="w-4 h-4 shrink-0" />}
        {online && syncState === 'idle' && status?.pending && status.pending > 0 && (
          <RefreshCw className="w-4 h-4 shrink-0" />
        )}

        <span>
          {!online && 'Sem conexão — exibindo dados do cache local'}
          {online && syncState === 'syncing' && 'Sincronizando com o servidor...'}
          {online && syncState === 'success' && 'Sincronização concluída!'}
          {online && syncState === 'error' && 'Erro ao sincronizar — tente novamente'}
          {online && syncState === 'idle' && status?.pending && status.pending > 0 &&
            `${status.pending} alteração(ões) pendente(s) de sincronização`
          }
        </span>

        {status?.last_sync && syncState === 'idle' && (
          <span className="opacity-50 text-xs ml-2">
            Último sync: {new Date(status.last_sync).toLocaleTimeString('pt-BR')}
          </span>
        )}
      </div>

      {/* Botão Sincronizar */}
      {online && syncState !== 'syncing' && (
        <button
          onClick={handleSync}
          className="
            flex items-center gap-1.5 px-3 py-1 rounded
            bg-white/10 hover:bg-white/20 transition-colors text-xs font-semibold
          "
        >
          <RefreshCw className="w-3 h-3" />
          Sincronizar
        </button>
      )}
    </div>
  );
}
