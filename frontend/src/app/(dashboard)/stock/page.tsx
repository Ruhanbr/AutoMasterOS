'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  Plus,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  Trash2,
  AlertTriangle,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
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
import { stockApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import type { StockItemListResponse, StockItem } from '@/types';
import type { AxiosError } from 'axios';

function isLowStock(item: StockItem): boolean {
  return parseFloat(item.quantity) <= parseFloat(item.min_quantity);
}

function formatQty(value: string): string {
  return parseFloat(value).toLocaleString('pt-BR', { minimumFractionDigits: 3 });
}

export default function StockPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const pageSize = 15;

  const { data, isLoading } = useQuery<StockItemListResponse>({
    queryKey: ['stock', page],
    queryFn: async () => {
      const res = await stockApi.list({ page, page_size: pageSize });
      return res.data;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await stockApi.delete(id);
    },
    onSuccess: () => {
      toast.success('Item removido do estoque.');
      queryClient.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao remover item');
    },
  });

  const handleDelete = (item: StockItem) => {
    if (!window.confirm(`Remover "${item.description}" do estoque?`)) return;
    deleteMutation.mutate(item.id);
  };

  const handleExport = async () => {
    try {
      const res = await stockApi.exportExcel();
      const url = URL.createObjectURL(
        new Blob([res.data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }),
      );
      const a = document.createElement('a');
      a.href = url;
      a.download = `estoque_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Erro ao exportar estoque');
    }
  };

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;

  return (
    <div>
      <Header title="Estoque" />
      <div className="p-6 space-y-4">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4">
          <div />
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={handleExport}>
              <Download className="w-4 h-4" />
              Exportar Excel
            </Button>
            <Link href="/stock/new">
              <Button>
                <Plus className="w-4 h-4" />
                Novo Item
              </Button>
            </Link>
          </div>
        </div>

        {/* Table */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : data?.items?.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <AlertCircle className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhum item encontrado no estoque</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Descrição</TableHead>
                  <TableHead>Unidade</TableHead>
                  <TableHead className="text-right">Quantidade</TableHead>
                  <TableHead className="text-right">Mín.</TableHead>
                  <TableHead className="text-right">Custo</TableHead>
                  <TableHead className="text-right">Venda</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items?.map((item) => {
                  const low = isLowStock(item);
                  return (
                    <TableRow
                      key={item.id}
                      className={`cursor-pointer ${low ? 'bg-yellow-50 hover:bg-yellow-100' : 'hover:bg-gray-50'}`}
                      onClick={() => router.push(`/stock/${item.id}`)}
                    >
                      <TableCell className="font-mono text-sm font-medium text-gray-900">
                        {item.sku}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-900">{item.description}</span>
                          {low && (
                            <Badge className="bg-yellow-100 text-yellow-800 border-yellow-300 text-xs">
                              <AlertTriangle className="w-3 h-3 mr-1" />
                              Estoque Baixo
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-gray-500">{item.unit}</TableCell>
                      <TableCell className={`text-right font-semibold text-sm ${low ? 'text-yellow-700' : 'text-gray-900'}`}>
                        {formatQty(item.quantity)}
                      </TableCell>
                      <TableCell className="text-right text-sm text-gray-500">
                        {formatQty(item.min_quantity)}
                      </TableCell>
                      <TableCell className="text-right text-sm text-gray-700">
                        {formatCurrency(parseFloat(item.cost_price))}
                      </TableCell>
                      <TableCell className="text-right text-sm font-medium text-gray-900">
                        {formatCurrency(parseFloat(item.sale_price))}
                      </TableCell>
                      <TableCell>
                        {item.active ? (
                          <Badge variant="default">Ativo</Badge>
                        ) : (
                          <Badge variant="secondary">Inativo</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-500 hover:text-red-700 hover:bg-red-50"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(item);
                          }}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>{data.total} item{data.total !== 1 ? 's' : ''}</span>
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
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
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
