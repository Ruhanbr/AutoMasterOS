'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Select } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
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
import { PageSpinner } from '@/components/ui/spinner';
import { invoicesApi } from '@/lib/api';
import { formatCurrency, formatDate, truncate } from '@/lib/utils';
import type { Invoice, PaginatedResponse, InvoiceStatus } from '@/types';

function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  switch (status) {
    case 'AUTORIZADA':
      return <Badge variant="default">Autorizada</Badge>;
    case 'REJEITADA':
      return <Badge variant="destructive">Rejeitada</Badge>;
    case 'PROCESSANDO':
      return <Badge variant="warning">Processando</Badge>;
    case 'PENDENTE':
      return <Badge variant="secondary">Pendente</Badge>;
    case 'ERRO':
      return <Badge variant="destructive">Erro</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export default function InvoicesPage() {
  const [status, setStatus] = useState<string>('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const { data, isLoading } = useQuery<PaginatedResponse<Invoice>>({
    queryKey: ['invoices', status, page],
    queryFn: async () => {
      const res = await invoicesApi.list({
        status: status || undefined,
        page,
        page_size: pageSize,
      });
      return res.data;
    },
  });

  return (
    <div>
      <Header title="Notas Fiscais (NF-e)" />
      <div className="p-6 space-y-4">
        {/* Filter */}
        <div className="flex items-center gap-4">
          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="w-48"
          >
            <option value="">Todos os status</option>
            <option value="PENDENTE">Pendentes</option>
            <option value="PROCESSANDO">Processando</option>
            <option value="AUTORIZADA">Autorizadas</option>
            <option value="REJEITADA">Rejeitadas</option>
            <option value="ERRO">Com Erro</option>
          </Select>
        </div>

        {/* Table */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : data?.items?.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <AlertCircle className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhuma nota fiscal encontrada</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Número NF-e</TableHead>
                  <TableHead>Chave de Acesso</TableHead>
                  <TableHead>Valor Total</TableHead>
                  <TableHead>Emissão</TableHead>
                  <TableHead>Autorização</TableHead>
                  <TableHead>Tentativas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items?.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell>
                      <InvoiceStatusBadge status={invoice.status} />
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {invoice.number || '—'}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-gray-500">
                      {invoice.access_key ? truncate(invoice.access_key, 20) : '—'}
                    </TableCell>
                    <TableCell className="font-semibold text-gray-900">
                      {formatCurrency(invoice.total_amount)}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {formatDate(invoice.issued_at)}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {formatDate(invoice.authorized_at)}
                    </TableCell>
                    <TableCell className="text-sm text-center">
                      {invoice.retry_count}
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
              {data.total} nota{data.total !== 1 ? 's' : ''} fiscal{data.total !== 1 ? 'is' : ''}
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
