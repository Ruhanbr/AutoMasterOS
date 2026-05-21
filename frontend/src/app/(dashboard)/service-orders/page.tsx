'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Plus, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/table';
import { PageSpinner } from '@/components/ui/spinner';
import { serviceOrdersApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import type { ServiceOrder, PaginatedResponse, ServiceOrderStatus } from '@/types';

function StatusBadge({ status }: { status: ServiceOrderStatus }) {
  switch (status) {
    case 'ABERTA':
      return <Badge variant="info">Aberta</Badge>;
    case 'EM_ANDAMENTO':
      return <Badge variant="warning">Em Andamento</Badge>;
    case 'FINALIZADA':
      return <Badge variant="default">Finalizada</Badge>;
    case 'CANCELADA':
      return <Badge variant="destructive">Cancelada</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function BudgetBadge({ status }: { status?: string }) {
  switch (status) {
    case 'AGUARDANDO_APROVACAO':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-amber-600 font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 inline-block" />
          Aguardando cliente
        </span>
      );
    case 'APROVADO':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-emerald-600 font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
          Aprovado pelo cliente
        </span>
      );
    case 'RECUSADO':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-600 font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />
          Recusado pelo cliente
        </span>
      );
    default:
      return null; // RASCUNHO: não exibe nada
  }
}

export default function ServiceOrdersPage() {
  const [status, setStatus] = useState<string>('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const { data, isLoading } = useQuery<PaginatedResponse<ServiceOrder>>({
    queryKey: ['service-orders', status, page],
    queryFn: async () => {
      const res = await serviceOrdersApi.list({
        status: status || undefined,
        page,
        page_size: pageSize,
      });
      return res.data;
    },
  });

  return (
    <div>
      <Header title="Ordens de Serviço" />
      <div className="p-6 space-y-4">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4">
          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="w-48"
          >
            <option value="">Todos os status</option>
            <option value="ABERTA">Abertas</option>
            <option value="EM_ANDAMENTO">Em Andamento</option>
            <option value="FINALIZADA">Finalizadas</option>
          </Select>

          <Link href="/service-orders/new">
            <Button>
              <Plus className="w-4 h-4" />
              Nova OS
            </Button>
          </Link>
        </div>

        {/* Table */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : data?.items?.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <AlertCircle className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhuma ordem de serviço encontrada</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nº OS</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Total</TableHead>
                  <TableHead>Abertura</TableHead>
                  <TableHead>Técnico</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items?.map((os) => (
                  <TableRow key={os.id}>
                    <TableCell>
                      <Link
                        href={`/service-orders/${os.id}`}
                        className="font-semibold text-green-700 hover:text-green-800 hover:underline"
                      >
                        #{os.number}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <p className="font-medium text-gray-900">{os.client.name}</p>
                      <p className="text-xs text-gray-500">{os.client.document}</p>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1">
                        <StatusBadge status={os.status} />
                        <BudgetBadge status={os.budget_status} />
                      </div>
                    </TableCell>
                    <TableCell className="font-semibold text-gray-900">
                      {formatCurrency(os.total_amount)}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {formatDate(os.opened_at)}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {os.technician_name || '—'}
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
            <span>
              {data.total} resultado{data.total !== 1 ? 's' : ''}
            </span>
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
    </div>
  );
}
