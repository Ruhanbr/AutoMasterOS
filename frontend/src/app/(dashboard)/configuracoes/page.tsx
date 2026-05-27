'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { useSearchParams } from 'next/navigation';
import {
  Settings, QrCode, Loader2, CheckCircle2, Trash2,
  Tractor, Link2, Link2Off, RefreshCw, AlertTriangle,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { tenantsApi, deereApi } from '@/lib/api';
import { getAccessToken } from '@/lib/auth';
import type { AxiosError } from 'axios';

// ── Helpers ──────────────────────────────────────────────────────────────────

function getTenantIdFromToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const token = getAccessToken();
    if (!token) return null;
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.tenant_id ?? null;
  } catch {
    return null;
  }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// ── Schema PIX ───────────────────────────────────────────────────────────────

const PIX_KEY_TYPES = ['CPF', 'CNPJ', 'EMAIL', 'TELEFONE', 'EVP'] as const;
type PixKeyType = typeof PIX_KEY_TYPES[number];

const pixSchema = z.object({
  pix_key_type: z.enum(PIX_KEY_TYPES),
  pix_key: z.string().min(1, 'Informe a chave PIX'),
});
type PixForm = z.infer<typeof pixSchema>;

const PIX_TYPE_LABELS: Record<PixKeyType, string> = {
  CPF: 'CPF', CNPJ: 'CNPJ', EMAIL: 'E-mail', TELEFONE: 'Telefone', EVP: 'Chave Aleatória (EVP)',
};
const PIX_TYPE_PLACEHOLDERS: Record<PixKeyType, string> = {
  CPF: '000.000.000-00', CNPJ: '00.000.000/0001-00',
  EMAIL: 'contato@oficina.com', TELEFONE: '+5511999999999',
  EVP: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
};

// ── John Deere Status types ───────────────────────────────────────────────────

interface DeereStatus {
  connected: boolean;
  organization_id?: string;
  organization_name?: string;
  token_expires_at?: string;
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ConfiguracoesPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const [tenantId, setTenantId] = useState<string | null>(null);

  useEffect(() => {
    setTenantId(getTenantIdFromToken());
  }, []);

  // Mostra toast se voltou do callback OAuth da JD
  useEffect(() => {
    if (searchParams.get('deere') === 'connected') {
      toast.success('John Deere conectada com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['deere-status'] });
    }
  }, [searchParams, queryClient]);

  // ── Tenant / PIX ──────────────────────────────────────────────────────────
  const { data: tenant, isLoading } = useQuery({
    queryKey: ['tenant-detail', tenantId],
    queryFn: async () => (await tenantsApi.get(tenantId!)).data,
    enabled: !!tenantId,
    staleTime: 30_000,
  });

  const { register, handleSubmit, watch, setValue, reset, formState: { errors, isDirty } } =
    useForm<PixForm>({
      resolver: zodResolver(pixSchema),
      defaultValues: { pix_key_type: 'CNPJ', pix_key: '' },
    });

  useEffect(() => {
    if (tenant?.pix_key) {
      reset({ pix_key_type: (tenant.pix_key_type as PixKeyType) || 'CNPJ', pix_key: tenant.pix_key });
    }
  }, [tenant, reset]);

  const keyType = watch('pix_key_type');
  const hasPixKey = !!tenant?.pix_key;

  const saveMutation = useMutation({
    mutationFn: (data: PixForm) =>
      tenantsApi.updatePix(tenantId!, { pix_key: data.pix_key, pix_key_type: data.pix_key_type }),
    onSuccess: () => {
      toast.success('Chave PIX salva!');
      queryClient.invalidateQueries({ queryKey: ['tenant-detail', tenantId] });
    },
    onError: (err: AxiosError<{ detail: string }>) => {
      toast.error(err.response?.data?.detail || 'Erro ao salvar chave PIX');
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => tenantsApi.updatePix(tenantId!, { pix_key: null, pix_key_type: null }),
    onSuccess: () => {
      toast.success('Chave PIX removida.');
      reset({ pix_key_type: 'CNPJ', pix_key: '' });
      queryClient.invalidateQueries({ queryKey: ['tenant-detail', tenantId] });
    },
    onError: (err: AxiosError<{ detail: string }>) => {
      toast.error(err.response?.data?.detail || 'Erro ao remover chave PIX');
    },
  });

  // ── John Deere ────────────────────────────────────────────────────────────
  const { data: deereStatus, isLoading: deereLoading } = useQuery<DeereStatus>({
    queryKey: ['deere-status'],
    queryFn: async () => (await deereApi.status()).data,
    staleTime: 60_000,
    retry: false,
  });

  const disconnectMutation = useMutation({
    mutationFn: () => deereApi.disconnect(),
    onSuccess: () => {
      toast.success('John Deere desconectada.');
      queryClient.invalidateQueries({ queryKey: ['deere-status'] });
    },
    onError: () => toast.error('Erro ao desconectar John Deere'),
  });

  const syncMutation = useMutation({
    mutationFn: () => deereApi.sync(),
    onSuccess: (res) => {
      const d = res.data as { alerts_found: number };
      toast.success(`Sincronizado! ${d.alerts_found} alerta(s) encontrado(s).`);
    },
    onError: () => toast.error('Erro ao sincronizar com John Deere'),
  });

  const handleConnectDeere = () => {
    const token = getAccessToken();
    // Redireciona para o backend que inicia o OAuth
    window.location.href = `${API_URL}/integrations/deere/connect`;
  };

  return (
    <div>
      <Header title="Configurações" />
      <div className="p-6 space-y-6 max-w-2xl">

        {/* ── PIX Card ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <QrCode className="w-5 h-5 text-green-600" />
              Chave PIX da Oficina
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              A chave PIX aparece automaticamente no PDF da OS enviado ao cliente,
              com QR Code e valor já preenchidos.
            </p>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center gap-2 text-gray-400 text-sm py-4">
                <Loader2 className="w-4 h-4 animate-spin" />
                Carregando configurações...
              </div>
            ) : (
              <>
                {hasPixKey && (
                  <div className="flex items-center gap-2 mb-4 px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
                    <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" />
                    <span>
                      Chave configurada: <strong>{tenant.pix_key_type}</strong>{' '}
                      — <span className="font-mono">{tenant.pix_key}</span>
                    </span>
                    <Button
                      variant="ghost" size="sm"
                      className="ml-auto h-7 w-7 p-0 text-red-400 hover:text-red-600"
                      onClick={() => removeMutation.mutate()}
                      disabled={removeMutation.isPending}
                    >
                      {removeMutation.isPending
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <Trash2 className="w-3.5 h-3.5" />}
                    </Button>
                  </div>
                )}

                <form onSubmit={handleSubmit((data) => saveMutation.mutate(data))} className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="pix_key_type">Tipo de Chave</Label>
                      <Select
                        id="pix_key_type"
                        {...register('pix_key_type')}
                        onChange={(e) => {
                          setValue('pix_key_type', e.target.value as PixKeyType, { shouldDirty: true });
                          setValue('pix_key', '');
                        }}
                        className="mt-1.5"
                      >
                        {PIX_KEY_TYPES.map((t) => (
                          <option key={t} value={t}>{PIX_TYPE_LABELS[t]}</option>
                        ))}
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="pix_key">Chave PIX</Label>
                      <Input
                        id="pix_key"
                        placeholder={PIX_TYPE_PLACEHOLDERS[keyType]}
                        {...register('pix_key')}
                        className="mt-1.5 font-mono text-sm"
                      />
                      {errors.pix_key && (
                        <p className="mt-1 text-xs text-red-600">{errors.pix_key.message}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex justify-end">
                    <Button type="submit" disabled={saveMutation.isPending || !isDirty}>
                      {saveMutation.isPending && <Loader2 className="w-4 h-4 animate-spin mr-1" />}
                      {hasPixKey ? 'Atualizar Chave PIX' : 'Salvar Chave PIX'}
                    </Button>
                  </div>
                </form>
              </>
            )}
          </CardContent>
        </Card>

        {/* ── John Deere Card ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Tractor className="w-5 h-5 text-green-700" />
              Integração John Deere
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              Conecte sua conta John Deere Operations Center para receber alertas
              e códigos de falha (DTCs) das máquinas automaticamente.
            </p>
          </CardHeader>
          <CardContent>
            {deereLoading ? (
              <div className="flex items-center gap-2 text-gray-400 text-sm py-4">
                <Loader2 className="w-4 h-4 animate-spin" />
                Verificando conexão...
              </div>
            ) : deereStatus?.connected ? (
              /* ── Conectado ── */
              <div className="space-y-4">
                <div className="flex items-center gap-3 px-4 py-3 bg-green-50 border border-green-200 rounded-lg">
                  <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-green-800">Conta conectada</p>
                    {deereStatus.organization_name && (
                      <p className="text-xs text-green-700 mt-0.5">
                        Organização: <strong>{deereStatus.organization_name}</strong>
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex items-center gap-2"
                    onClick={() => syncMutation.mutate()}
                    disabled={syncMutation.isPending}
                  >
                    {syncMutation.isPending
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <RefreshCw className="w-4 h-4" />}
                    Sincronizar agora
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    className="flex items-center gap-2 text-red-600 border-red-200 hover:bg-red-50"
                    onClick={() => disconnectMutation.mutate()}
                    disabled={disconnectMutation.isPending}
                  >
                    {disconnectMutation.isPending
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <Link2Off className="w-4 h-4" />}
                    Desconectar
                  </Button>
                </div>
              </div>
            ) : (
              /* ── Desconectado ── */
              <div className="space-y-4">
                <div className="flex items-start gap-3 px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
                  <AlertTriangle className="w-4 h-4 text-yellow-600 flex-shrink-0 mt-0.5" />
                  <p>
                    Nenhuma conta John Deere conectada. Clique em conectar para autorizar o
                    acesso às máquinas e alertas da sua conta Operations Center.
                  </p>
                </div>

                <Button
                  className="flex items-center gap-2 bg-green-700 hover:bg-green-800 text-white"
                  onClick={handleConnectDeere}
                >
                  <Link2 className="w-4 h-4" />
                  Conectar John Deere
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Info Card ── */}
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-start gap-3">
              <Settings className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-blue-800">
                <p className="font-semibold mb-1">Integração John Deere — como funciona</p>
                <ul className="space-y-1 text-blue-700 list-disc list-inside">
                  <li>O cliente autoriza o acesso via conta Operations Center</li>
                  <li>O AutoMaster recebe alertas e DTCs automaticamente</li>
                  <li>Cada alerta gera uma OS já com o código de erro e a máquina vinculada</li>
                  <li>Funciona com máquinas que possuem JDLink ativo</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>

      </div>
    </div>
  );
}
