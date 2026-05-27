'use client';

import { use, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  ArrowLeft, User, Phone, Mail, MapPin, Tractor,
  CheckCircle2, AlertTriangle, Link2, Link2Off,
  RefreshCw, Loader2, ClipboardList, Zap,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageSpinner } from '@/components/ui/spinner';
import { clientsApi, deereApi, machinesApi } from '@/lib/api';
import { getAccessToken } from '@/lib/auth';

function getTenantIdFromToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const token = getAccessToken();
    if (!token) return null;
    return JSON.parse(atob(token.split('.')[1])).tenant_id ?? null;
  } catch { return null; }
}

interface DeereStatus {
  connected: boolean;
  organization_id?: string;
  organization_name?: string;
}

interface DeereAlert {
  dtcCode?: string;
  alertType?: string;
  description?: string;
  severity?: string;
  triggeredAt?: string;
}

interface Machine {
  id: string;
  name?: string;
  modelYear?: string;
  serialNumber?: string;
}

export default function ClientDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: clientId } = use(params);
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();

  // Toast ao voltar do OAuth
  useEffect(() => {
    if (searchParams.get('deere') === 'connected' && searchParams.get('deere_client') === clientId) {
      toast.success('John Deere conectada com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['deere-status', clientId] });
    }
  }, [searchParams, clientId, queryClient]);

  // ── Dados do cliente ──────────────────────────────────────────────────────
  const { data: client, isLoading } = useQuery({
    queryKey: ['client', clientId],
    queryFn: async () => (await clientsApi.get(clientId)).data,
    staleTime: 60_000,
  });

  // ── Máquinas AutoMaster ───────────────────────────────────────────────────
  const { data: machinesData } = useQuery({
    queryKey: ['machines', clientId],
    queryFn: async () => (await machinesApi.list({ client_id: clientId })).data,
    enabled: !!clientId,
    staleTime: 60_000,
  });

  // ── JD Status ────────────────────────────────────────────────────────────
  const { data: deereStatus, isLoading: deereLoading } = useQuery<DeereStatus>({
    queryKey: ['deere-status', clientId],
    queryFn: async () => (await deereApi.clientStatus(clientId)).data,
    staleTime: 60_000,
    retry: false,
  });

  // ── JD Alertas ───────────────────────────────────────────────────────────
  const { data: alertsData, isLoading: alertsLoading, refetch: refetchAlerts } = useQuery({
    queryKey: ['deere-alerts', clientId],
    queryFn: async () => (await deereApi.clientAlerts(clientId)).data,
    enabled: deereStatus?.connected === true,
    staleTime: 120_000,
    retry: false,
  });

  // ── JD Máquinas ──────────────────────────────────────────────────────────
  const { data: deereMachinesData } = useQuery({
    queryKey: ['deere-machines', clientId],
    queryFn: async () => (await deereApi.clientMachines(clientId)).data,
    enabled: deereStatus?.connected === true,
    staleTime: 120_000,
    retry: false,
  });

  const disconnectMutation = useMutation({
    mutationFn: () => deereApi.clientDisconnect(clientId),
    onSuccess: () => {
      toast.success('John Deere desconectada.');
      queryClient.invalidateQueries({ queryKey: ['deere-status', clientId] });
      queryClient.invalidateQueries({ queryKey: ['deere-alerts', clientId] });
    },
    onError: () => toast.error('Erro ao desconectar'),
  });

  const syncMutation = useMutation({
    mutationFn: () => deereApi.clientSync(clientId),
    onSuccess: (res) => {
      const d = res.data as { alerts_found: number };
      toast.success(`${d.alerts_found} alerta(s) sincronizado(s).`);
      queryClient.invalidateQueries({ queryKey: ['deere-alerts', clientId] });
    },
    onError: () => toast.error('Erro ao sincronizar'),
  });

  const handleConnect = async () => {
    try {
      // Chamada autenticada via axios para obter a URL OAuth
      const res = await deereApi.getConnectUrl(clientId);
      const { url } = res.data as { url: string };
      // Redireciona o browser para a página de autorização da John Deere
      window.location.href = url;
    } catch {
      toast.error('Erro ao gerar link de autorização John Deere');
    }
  };

  if (isLoading) return <div><Header title="Cliente" /><PageSpinner /></div>;
  if (!client) return <div><Header title="Cliente" /><p className="p-6 text-gray-500">Cliente não encontrado.</p></div>;

  const machines = machinesData?.items ?? machinesData ?? [];
  const alerts: DeereAlert[] = alertsData?.alerts ?? [];
  const deereMachines: Machine[] = deereMachinesData?.machines ?? [];

  const severityColor = (s?: string) => {
    if (!s) return 'bg-gray-100 text-gray-700';
    if (s.toUpperCase() === 'HIGH' || s.toUpperCase() === 'CRITICAL') return 'bg-red-100 text-red-700';
    if (s.toUpperCase() === 'MEDIUM') return 'bg-yellow-100 text-yellow-700';
    return 'bg-blue-100 text-blue-700';
  };

  return (
    <div>
      <Header title={client.name} />
      <div className="p-6 space-y-6 max-w-4xl">

        {/* Voltar */}
        <Link href="/clients" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft className="w-4 h-4" />
          Voltar para Clientes
        </Link>

        {/* ── Info do Cliente ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <User className="w-4 h-4 text-gray-400" />
              Dados do Cliente
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Nome</p>
                <p className="font-medium text-gray-900">{client.name}</p>
              </div>
              {client.document && (
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">CPF/CNPJ</p>
                  <p className="font-mono text-gray-700">{client.document}</p>
                </div>
              )}
              {client.email && (
                <div className="flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-gray-700">{client.email}</span>
                </div>
              )}
              {client.phone && (
                <div className="flex items-center gap-1.5">
                  <Phone className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-gray-700">{client.phone}</span>
                </div>
              )}
              {(client.city || client.state) && (
                <div className="flex items-center gap-1.5 col-span-2">
                  <MapPin className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-gray-700">{[client.city, client.state].filter(Boolean).join(' / ')}</span>
                </div>
              )}
            </div>

            <div className="mt-4 pt-4 border-t flex gap-3">
              <Link href={`/service-orders?client_id=${clientId}`}>
                <Button variant="outline" size="sm" className="flex items-center gap-1.5">
                  <ClipboardList className="w-3.5 h-3.5" />
                  Ver OS do cliente
                </Button>
              </Link>
              <Link href={`/machines?client_id=${clientId}`}>
                <Button variant="outline" size="sm" className="flex items-center gap-1.5">
                  <Tractor className="w-3.5 h-3.5" />
                  Ver máquinas ({Array.isArray(machines) ? machines.length : 0})
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* ── John Deere Card ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Tractor className="w-5 h-5 text-green-700" />
              John Deere Operations Center
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              Conecte a conta JD deste cliente para receber alertas e DTCs das máquinas automaticamente.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">

            {deereLoading ? (
              <div className="flex items-center gap-2 text-gray-400 text-sm">
                <Loader2 className="w-4 h-4 animate-spin" />
                Verificando conexão...
              </div>
            ) : deereStatus?.connected ? (
              <>
                {/* Status conectado */}
                <div className="flex items-center gap-3 px-4 py-3 bg-green-50 border border-green-200 rounded-lg">
                  <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-green-800">Conta conectada</p>
                    {deereStatus.organization_name && (
                      <p className="text-xs text-green-700">Org: {deereStatus.organization_name}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline" size="sm"
                      className="flex items-center gap-1.5"
                      onClick={() => syncMutation.mutate()}
                      disabled={syncMutation.isPending}
                    >
                      {syncMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                      Sincronizar
                    </Button>
                    <Button
                      variant="outline" size="sm"
                      className="flex items-center gap-1.5 text-red-600 border-red-200 hover:bg-red-50"
                      onClick={() => disconnectMutation.mutate()}
                      disabled={disconnectMutation.isPending}
                    >
                      {disconnectMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Link2Off className="w-3.5 h-3.5" />}
                      Desconectar
                    </Button>
                  </div>
                </div>

                {/* Máquinas JD */}
                {deereMachines.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                      Máquinas JD ({deereMachines.length})
                    </p>
                    <div className="space-y-2">
                      {deereMachines.map((m) => (
                        <div key={m.id} className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded-lg text-sm">
                          <Tractor className="w-4 h-4 text-green-700 flex-shrink-0" />
                          <div className="flex-1">
                            <p className="font-medium text-gray-800">{m.name || 'Máquina sem nome'}</p>
                            {m.serialNumber && <p className="text-xs text-gray-400">S/N: {m.serialNumber}</p>}
                          </div>
                          {m.modelYear && <span className="text-xs text-gray-400">{m.modelYear}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Alertas / DTCs */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 text-yellow-500" />
                      Alertas / DTCs ativos
                    </p>
                    <button onClick={() => refetchAlerts()} className="text-xs text-blue-500 hover:underline">
                      Atualizar
                    </button>
                  </div>

                  {alertsLoading ? (
                    <div className="flex items-center gap-2 text-gray-400 text-xs py-2">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Buscando alertas...
                    </div>
                  ) : alerts.length === 0 ? (
                    <div className="flex items-center gap-2 px-3 py-3 bg-green-50 rounded-lg text-sm text-green-700">
                      <CheckCircle2 className="w-4 h-4" />
                      Nenhum alerta ativo — máquinas OK!
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {alerts.map((a, i) => (
                        <div key={i} className="flex items-start gap-3 px-3 py-2.5 border border-orange-200 bg-orange-50 rounded-lg">
                          <AlertTriangle className="w-4 h-4 text-orange-500 flex-shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-gray-800">
                              {a.dtcCode || a.alertType || 'Alerta'}
                            </p>
                            {a.description && (
                              <p className="text-xs text-gray-600 mt-0.5">{a.description}</p>
                            )}
                          </div>
                          {a.severity && (
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${severityColor(a.severity)}`}>
                              {a.severity}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              /* Desconectado */
              <div className="space-y-3">
                <div className="flex items-start gap-3 px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
                  <AlertTriangle className="w-4 h-4 text-yellow-600 flex-shrink-0 mt-0.5" />
                  <p>
                    Este cliente ainda não conectou a conta John Deere.
                    Clique em conectar — o cliente precisará fazer login na conta JD dele para autorizar.
                  </p>
                </div>
                <Button
                  className="flex items-center gap-2 bg-green-700 hover:bg-green-800 text-white"
                  onClick={handleConnect}
                >
                  <Link2 className="w-4 h-4" />
                  Conectar John Deere deste cliente
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

      </div>
    </div>
  );
}
