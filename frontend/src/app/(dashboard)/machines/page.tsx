'use client';

import { Suspense, useState, useEffect } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Search,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Wrench,
  Trash2,
  Eye,
  X,
  Filter,
  RotateCcw,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Dialog, DialogHeader, DialogBody, DialogFooter } from '@/components/ui/dialog';
import { PageSpinner } from '@/components/ui/spinner';
import { machinesApi, clientsApi } from '@/lib/api';
import type { Machine, PaginatedResponse } from '@/types';
import type { AxiosError } from 'axios';

type MachineApiError = { detail: string };

const PAGE_SIZE = 15;

function MachineTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    Tratores: 'bg-green-100 text-green-800 border-green-200',
    Colheitadeiras: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    Plantadeiras: 'bg-blue-100 text-blue-800 border-blue-200',
    Semeadoras: 'bg-purple-100 text-purple-800 border-purple-200',
    Pulverizadores: 'bg-orange-100 text-orange-800 border-orange-200',
    Outros: 'bg-gray-100 text-gray-700 border-gray-200',
  };
  return (
    <Badge className={colors[type] ?? colors['Outros']}>
      {type}
    </Badge>
  );
}

function MachinesPageContent() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const clientIdFromUrl = searchParams.get('client_id') ?? undefined;

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [showInactive, setShowInactive] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Machine | null>(null);

  // Debounce: só dispara query após 350ms sem digitar
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  // Volta pra página 1 quando o texto muda
  useEffect(() => { setPage(1); }, [debouncedSearch]);

  // When filtering by client, fetch client name for the banner
  const { data: clientData } = useQuery({
    queryKey: ['client-detail', clientIdFromUrl],
    queryFn: async () => {
      if (!clientIdFromUrl) return null;
      const res = await clientsApi.get(clientIdFromUrl);
      return res.data;
    },
    enabled: !!clientIdFromUrl,
    staleTime: 60_000,
  });

  // Main machines query — server-side search, client filter e showInactive
  const { data, isLoading } = useQuery<PaginatedResponse<Machine>>({
    queryKey: ['machines', page, clientIdFromUrl, showInactive, debouncedSearch],
    queryFn: async () => {
      const res = await machinesApi.list({
        page,
        page_size: PAGE_SIZE,
        active_only: !showInactive,
        client_id: clientIdFromUrl,
        search: debouncedSearch || undefined,
      });
      return res.data;
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => machinesApi.deactivate(id),
    onSuccess: () => {
      toast.success('Máquina desativada com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['machines'] });
      setConfirmDelete(null);
    },
    onError: (error: AxiosError<MachineApiError>) => {
      toast.error(error.response?.data?.detail || 'Erro ao desativar máquina');
      setConfirmDelete(null);
    },
  });

  const reactivateMutation = useMutation({
    mutationFn: (id: string) => machinesApi.reactivate(id),
    onSuccess: () => {
      toast.success('Máquina reativada com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['machines'] });
    },
    onError: (error: AxiosError<MachineApiError>) => {
      toast.error(error.response?.data?.detail || 'Erro ao reativar máquina');
    },
  });

  // Dados já filtrados pelo servidor
  const filtered = data?.items ?? [];

  // "Nova Máquina" link preserves the client_id param so the form can pre-fill it
  const newMachineHref = clientIdFromUrl
    ? `/machines/new?client_id=${clientIdFromUrl}`
    : '/machines/new';

  return (
    <div>
      <Header title="Máquinas" />
      <div className="p-6 space-y-4">

        {/* Client filter banner */}
        {clientIdFromUrl && (
          <div className="flex items-center gap-3 px-4 py-2.5 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
            <Filter className="w-4 h-4 flex-shrink-0" />
            <span>
              Filtrando por cliente:{' '}
              <strong>{clientData?.name ?? 'Carregando...'}</strong>
            </span>
            <Link
              href="/machines"
              className="ml-auto flex items-center gap-1 text-green-600 hover:text-green-800 font-medium"
            >
              <X className="w-3.5 h-3.5" />
              Ver todas
            </Link>
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Buscar por marca, modelo, série ou placa..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="pl-9"
            />
          </div>

          {/* Toggle: mostrar desativadas */}
          <button
            type="button"
            onClick={() => { setShowInactive((v) => !v); setPage(1); }}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
              showInactive
                ? 'bg-gray-100 border-gray-300 text-gray-700'
                : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-50'
            }`}
          >
            {/* Switch visual */}
            <span
              className={`relative inline-flex h-5 w-9 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ${
                showInactive ? 'bg-gray-500' : 'bg-gray-200'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                  showInactive ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </span>
            Mostrar desativadas
          </button>

          <Link href={newMachineHref}>
            <Button>
              <Plus className="w-4 h-4" />
              Nova Máquina
            </Button>
          </Link>
        </div>

        {/* Table */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <Wrench className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhuma máquina encontrada</p>
              <Link href={newMachineHref} className="mt-4">
                <Button variant="outline" size="sm">
                  <Plus className="w-4 h-4" />
                  Cadastrar primeira máquina
                </Button>
              </Link>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Nº de Série</TableHead>
                  <TableHead>Marca / Modelo</TableHead>
                  <TableHead>Placa</TableHead>
                  <TableHead>Ano</TableHead>
                  {!clientIdFromUrl && <TableHead>Cliente</TableHead>}
                  <TableHead>Status</TableHead>
                  <TableHead className="w-28">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((machine) => (
                  <TableRow
                    key={machine.id}
                    className={!machine.active ? 'opacity-50 bg-gray-50' : undefined}
                  >
                    <TableCell>
                      <MachineTypeBadge type={machine.machine_type} />
                    </TableCell>
                    <TableCell className="font-mono text-sm font-semibold text-gray-800">
                      {machine.serial_number}
                    </TableCell>
                    <TableCell>
                      <p className="font-medium text-gray-900">{machine.brand}</p>
                      <p className="text-sm text-gray-500">{machine.model}</p>
                    </TableCell>
                    <TableCell className="text-sm text-gray-600">
                      {machine.placa || '—'}
                    </TableCell>
                    <TableCell className="text-sm text-gray-600">
                      {machine.year || '—'}
                    </TableCell>
                    {!clientIdFromUrl && (
                      <TableCell className="text-sm text-gray-600">
                        {machine.client?.name || '—'}
                      </TableCell>
                    )}
                    <TableCell>
                      {machine.active ? (
                        <Badge variant="default">Ativa</Badge>
                      ) : (
                        <Badge variant="secondary">Inativa</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Link href={`/machines/${machine.id}`}>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Ver detalhes">
                            <Eye className="w-4 h-4 text-gray-500" />
                          </Button>
                        </Link>
                        {machine.active ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title="Desativar"
                            onClick={() => setConfirmDelete(machine)}
                          >
                            <Trash2 className="w-4 h-4 text-red-400" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title="Reativar máquina"
                            onClick={() => reactivateMutation.mutate(machine.id)}
                            disabled={reactivateMutation.isPending}
                          >
                            {reactivateMutation.isPending ? (
                              <Loader2 className="w-4 h-4 animate-spin text-green-500" />
                            ) : (
                              <RotateCcw className="w-4 h-4 text-green-600" />
                            )}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>{data.total} máquina{data.total !== 1 ? 's' : ''}</span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="w-4 h-4" />
                Anterior
              </Button>
              <span className="px-2">
                {page} / {data.total_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
                disabled={page === data.total_pages}
              >
                Próxima
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Confirm deactivate dialog */}
      {confirmDelete && (
        <Dialog open onClose={() => setConfirmDelete(null)} className="max-w-md">
          <DialogHeader title="Desativar Máquina" onClose={() => setConfirmDelete(null)} />
          <DialogBody>
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-gray-700">
                  Deseja desativar a máquina{' '}
                  <strong>{confirmDelete.brand} {confirmDelete.model}</strong>?
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Série: {confirmDelete.serial_number}. Esta ação pode ser revertida pelo suporte.
                </p>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => deactivateMutation.mutate(confirmDelete.id)}
              disabled={deactivateMutation.isPending}
            >
              {deactivateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              Desativar
            </Button>
          </DialogFooter>
        </Dialog>
      )}
    </div>
  );
}

export default function MachinesPage() {
  return (
    <Suspense>
      <MachinesPageContent />
    </Suspense>
  );
}
