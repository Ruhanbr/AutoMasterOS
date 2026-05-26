'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { ArrowLeft, FileBarChart, TrendingUp, Wrench, Package, ClipboardList } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { PageSpinner } from '@/components/ui/spinner';
import { serviceOrdersApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import type { PaginatedResponse, ServiceOrder, ServiceOrderStatus } from '@/types';

function StatusBadge({ status }: { status: ServiceOrderStatus }) {
  const map: Record<ServiceOrderStatus, { label: string; cls: string }> = {
    ABERTA:       { label: 'Aberta',       cls: 'bg-blue-100 text-blue-800' },
    EM_ANDAMENTO: { label: 'Em Andamento', cls: 'bg-yellow-100 text-yellow-800' },
    FINALIZADA:   { label: 'Finalizada',   cls: 'bg-green-100 text-green-800' },
    CANCELADA:    { label: 'Cancelada',    cls: 'bg-red-100 text-red-800' },
  };
  const s = map[status] ?? { label: status, cls: '' };
  return <Badge className={s.cls}>{s.label}</Badge>;
}

function SummaryCard({ title, value, icon: Icon, color }: {
  title: string; value: string; icon: React.ElementType; color: string;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
            <p className={`mt-1 text-2xl font-bold ${color}`}>{value}</p>
          </div>
          <div className={`p-3 rounded-xl bg-gray-50`}>
            <Icon className={`w-5 h-5 ${color}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ServiceOrdersReportPage() {
  const today = new Date().toISOString().slice(0, 10);
  const firstDay = today.slice(0, 8) + '01';

  const [dateFrom, setDateFrom] = useState(firstDay);
  const [dateTo, setDateTo]     = useState(today);
  const [status, setStatus]     = useState('');
  const [page, setPage]         = useState(1);
  const pageSize = 20;

  const params = {
    date_from: dateFrom || undefined,
    date_to:   dateTo   || undefined,
    status:    status   || undefined,
    page,
    page_size: pageSize,
  };

  const { data, isLoading } = useQuery<PaginatedResponse<ServiceOrder>>({
    queryKey: ['os-report', dateFrom, dateTo, status, page],
    queryFn: async () => (await serviceOrdersApi.list(params)).data,
  });

  const { data: summary } = useQuery<{
    total_os: number;
    total_faturamento: number;
    total_servicos: number;
    total_pecas: number;
  }>({
    queryKey: ['os-summary', dateFrom, dateTo, status],
    queryFn: async () => (await serviceOrdersApi.summary({
      date_from: dateFrom || undefined,
      date_to:   dateTo   || undefined,
      status:    status   || undefined,
    })).data,
  });

  return (
    <div>
      <Header title="Relatório de OS" />
      <div className="p-6 space-y-5 max-w-6xl mx-auto">

        {/* Voltar */}
        <Link href="/service-orders">
          <Button variant="ghost" size="sm" className="gap-2 text-gray-500">
            <ArrowLeft className="w-4 h-4" />
            Ordens de Serviço
          </Button>
        </Link>

        {/* Filtros */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <FileBarChart className="w-4 h-4" />
              Filtros do Relatório
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Data inicial</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Data final</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Status</label>
                <Select
                  value={status}
                  onChange={(e) => { setStatus(e.target.value); setPage(1); }}
                  className="w-44"
                >
                  <option value="">Todos</option>
                  <option value="ABERTA">Abertas</option>
                  <option value="EM_ANDAMENTO">Em Andamento</option>
                  <option value="FINALIZADA">Finalizadas</option>
                  <option value="CANCELADA">Canceladas</option>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Cards de totais */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <SummaryCard
              title="Total de OS"
              value={String(summary.total_os)}
              icon={ClipboardList}
              color="text-blue-600"
            />
            <SummaryCard
              title="Faturamento"
              value={formatCurrency(summary.total_faturamento)}
              icon={TrendingUp}
              color="text-green-600"
            />
            <SummaryCard
              title="Serviços"
              value={formatCurrency(summary.total_servicos)}
              icon={Wrench}
              color="text-purple-600"
            />
            <SummaryCard
              title="Peças"
              value={formatCurrency(summary.total_pecas)}
              icon={Package}
              color="text-orange-600"
            />
          </div>
        )}

        {/* Tabela */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : data?.items?.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <FileBarChart className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhuma OS encontrada no período</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nº OS</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Técnico</TableHead>
                  <TableHead>Abertura</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items?.map((os) => (
                  <TableRow key={os.id}>
                    <TableCell>
                      <Link
                        href={`/service-orders/${os.id}`}
                        className="font-semibold text-green-700 hover:underline"
                      >
                        #{os.number}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <p className="font-medium text-gray-900">{os.client.name}</p>
                      <p className="text-xs text-gray-500">{os.client.document}</p>
                    </TableCell>
                    <TableCell><StatusBadge status={os.status} /></TableCell>
                    <TableCell className="text-sm text-gray-500">{os.technician_name || '—'}</TableCell>
                    <TableCell className="text-sm text-gray-500">{formatDate(os.opened_at)}</TableCell>
                    <TableCell className="text-right font-semibold text-gray-900">
                      {formatCurrency(os.total_amount)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Paginação */}
          {data && data.total_pages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t text-sm text-gray-500">
              <span>{data.total} resultado{data.total !== 1 ? 's' : ''}</span>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
                  Anterior
                </Button>
                <span>{page} / {data.total_pages}</span>
                <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))} disabled={page === data.total_pages}>
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
