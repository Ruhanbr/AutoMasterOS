'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { Bell, Check, CheckCheck, AlertTriangle, Tractor, ClipboardList, Info, X } from 'lucide-react';
import { notificationsApi } from '@/lib/api';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  link: string | null;
  read: boolean;
  created_at: string;
}

function NotificationIcon({ type }: { type: string }) {
  if (type === 'JD_ALERT') return <Tractor className="w-4 h-4 text-green-700 flex-shrink-0" />;
  if (type === 'OS_ATRIBUIDA') return <ClipboardList className="w-4 h-4 text-blue-600 flex-shrink-0" />;
  if (type === 'OS_CRIADA') return <ClipboardList className="w-4 h-4 text-indigo-600 flex-shrink-0" />;
  return <Info className="w-4 h-4 text-gray-500 flex-shrink-0" />;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const queryClient = useQueryClient();

  // Contagem não lidas — polling a cada 30s
  const { data: countData } = useQuery({
    queryKey: ['notifications-count'],
    queryFn: async () => (await notificationsApi.unreadCount()).data as { count: number },
    refetchInterval: 30_000,
    staleTime: 20_000,
  });

  // Lista de notificações — busca ao abrir
  const { data: listData } = useQuery({
    queryKey: ['notifications-list'],
    queryFn: async () => (await notificationsApi.list()).data as Notification[],
    enabled: open,
    staleTime: 10_000,
  });

  const markReadMutation = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications-count'] });
      queryClient.invalidateQueries({ queryKey: ['notifications-list'] });
    },
  });

  const markAllMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications-count'] });
      queryClient.invalidateQueries({ queryKey: ['notifications-list'] });
    },
  });

  const handleClick = (n: Notification) => {
    if (!n.read) markReadMutation.mutate(n.id);
    if (n.link) {
      router.push(n.link);
      setOpen(false);
    }
  };

  const unread = countData?.count ?? 0;
  const notifications = listData ?? [];

  return (
    <div className="relative">
      {/* Botão sino */}
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 rounded-lg hover:bg-gray-100 transition"
        aria-label="Notificações"
      >
        <Bell className="w-5 h-5 text-gray-600" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center leading-none">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {/* Painel */}
      {open && (
        <>
          {/* Overlay */}
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />

          <div className="absolute right-0 top-full mt-2 w-96 bg-white rounded-xl shadow-xl border border-gray-200 z-30 flex flex-col max-h-[520px]">
            {/* Header do painel */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-gray-600" />
                <span className="text-sm font-semibold text-gray-800">Notificações</span>
                {unread > 0 && (
                  <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full font-medium">
                    {unread} não lida{unread > 1 ? 's' : ''}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {unread > 0 && (
                  <button
                    onClick={() => markAllMutation.mutate()}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50 transition"
                    title="Marcar todas como lidas"
                  >
                    <CheckCheck className="w-3.5 h-3.5" />
                    Marcar todas
                  </button>
                )}
                <button
                  onClick={() => setOpen(false)}
                  className="p-1 rounded hover:bg-gray-100 transition"
                >
                  <X className="w-4 h-4 text-gray-400" />
                </button>
              </div>
            </div>

            {/* Lista */}
            <div className="overflow-y-auto flex-1">
              {notifications.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                  <Bell className="w-8 h-8 mb-2 opacity-30" />
                  <p className="text-sm">Nenhuma notificação</p>
                </div>
              ) : (
                notifications.map((n) => (
                  <button
                    key={n.id}
                    onClick={() => handleClick(n)}
                    className={`w-full text-left flex items-start gap-3 px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition ${
                      !n.read ? 'bg-blue-50/40' : ''
                    }`}
                  >
                    {/* Ícone tipo */}
                    <div className="mt-0.5">
                      <NotificationIcon type={n.type} />
                    </div>

                    {/* Conteúdo */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm leading-snug ${!n.read ? 'font-semibold text-gray-900' : 'font-medium text-gray-700'}`}>
                        {n.title}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{n.message}</p>
                      <p className="text-[11px] text-gray-400 mt-1">
                        {formatDistanceToNow(new Date(n.created_at), { addSuffix: true, locale: ptBR })}
                      </p>
                    </div>

                    {/* Indicador não lida */}
                    {!n.read && (
                      <div className="mt-1.5 w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" />
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
