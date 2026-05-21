'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  Plus,
  X,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Loader2,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { PageSpinner } from '@/components/ui/spinner';
import { financialApi } from '@/lib/api';
import { formatCurrency, formatDateOnly } from '@/lib/utils';
import type { FinancialEntry, FinancialEntryListResponse, FinancialSummary, EntryType } from '@/types';
import type { AxiosError } from 'axios';

const expenseSchema = z.object({
  description: z.string().min(2, 'Descrição deve ter ao menos 2 caracteres'),
  amount: z.coerce.number().min(0.01, 'Valor deve ser maior que 0'),
  category: z.string().optional(),
  reference_date: z.string().min(1, 'Data de referência é obrigatória'),
  notes: z.string().optional(),
});

type ExpenseForm = z.infer<typeof expenseSchema>;

function EntryTypeBadge({ type }: { type: EntryType }) {
  switch (type) {
    case 'RECEITA':
      return <Badge className="bg-green-100 text-green-800 border-green-300">RECEITA</Badge>;
    case 'DESPESA':
      return <Badge className="bg-red-100 text-red-800 border-red-300">DESPESA</Badge>;
    case 'ESTORNO':
      return <Badge variant="secondary">ESTORNO</Badge>;
    default:
      return <Badge variant="secondary">{type}</Badge>;
  }
}

function SummaryCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  icon: React.ElementType;
  color: 'green' | 'red';
}) {
  const formatted = formatCurrency(parseFloat(value || '0'));
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-500">{title}</p>
            <p className={`text-2xl font-bold mt-1 ${color === 'green' ? 'text-green-700' : 'text-red-600'}`}>
              {formatted}
            </p>
          </div>
          <div className={`p-3 rounded-full ${color === 'green' ? 'bg-green-50' : 'bg-red-50'}`}>
            <Icon className={`w-6 h-6 ${color === 'green' ? 'text-green-600' : 'text-red-500'}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function FinancialPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [entryTypeFilter, setEntryTypeFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const pageSize = 15;

  const summaryParams = {
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };

  const { data: summary } = useQuery<FinancialSummary>({
    queryKey: ['financial-summary', dateFrom, dateTo],
    queryFn: async () => {
      const res = await financialApi.summary(summaryParams);
      return res.data;
    },
  });

  const { data, isLoading } = useQuery<FinancialEntryListResponse>({
    queryKey: ['financial', entryTypeFilter, dateFrom, dateTo, page],
    queryFn: async () => {
      const res = await financialApi.list({
        entry_type: entryTypeFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
        page_size: pageSize,
      });
      return res.data;
    },
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ExpenseForm>({
    resolver: zodResolver(expenseSchema),
    defaultValues: {
      reference_date: new Date().toISOString().slice(0, 10),
    },
  });

  const createExpenseMutation = useMutation({
    mutationFn: async (data: ExpenseForm) => {
      const res = await financialApi.createExpense({
        ...data,
        category: data.category || null,
        notes: data.notes || null,
      });
      return res.data;
    },
    onSuccess: () => {
      toast.success('Despesa lançada com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['financial'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      reset({ reference_date: new Date().toISOString().slice(0, 10) });
      setShowExpenseForm(false);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao lançar despesa');
    },
  });

  const handleExport = async () => {
    try {
      const res = await financialApi.exportExcel({
        entry_type: entryTypeFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      });
      const url = URL.createObjectURL(
        new Blob([res.data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }),
      );
      const a = document.createElement('a');
      a.href = url;
      a.download = `financeiro_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Erro ao exportar relatório');
    }
  };

  const saldo = parseFloat(summary?.saldo || '0');
  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;

  return (
    <div>
      <Header title="Financeiro" />
      <div className="p-6 space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SummaryCard
            title="Total Receitas"
            value={summary?.total_receitas || '0'}
            icon={TrendingUp}
            color="green"
          />
          <SummaryCard
            title="Total Despesas"
            value={summary?.total_despesas || '0'}
            icon={TrendingDown}
            color="red"
          />
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500">Saldo</p>
                  <p className={`text-2xl font-bold mt-1 ${saldo >= 0 ? 'text-green-700' : 'text-red-600'}`}>
                    {formatCurrency(saldo)}
                  </p>
                </div>
                <div className={`p-3 rounded-full ${saldo >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
                  <DollarSign className={`w-6 h-6 ${saldo >= 0 ? 'text-green-600' : 'text-red-500'}`} />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filter bar + Actions */}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="entry_type_filter" className="text-xs text-gray-500 mb-1 block">Tipo</Label>
            <Select
              id="entry_type_filter"
              value={entryTypeFilter}
              onChange={(e) => { setEntryTypeFilter(e.target.value); setPage(1); }}
              className="w-36"
            >
              <option value="">Todas</option>
              <option value="RECEITA">Receitas</option>
              <option value="DESPESA">Despesas</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="date_from" className="text-xs text-gray-500 mb-1 block">De</Label>
            <Input
              id="date_from"
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
              className="w-40"
            />
          </div>
          <div>
            <Label htmlFor="date_to" className="text-xs text-gray-500 mb-1 block">Até</Label>
            <Input
              id="date_to"
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
              className="w-40"
            />
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" onClick={handleExport}>
              <Download className="w-4 h-4" />
              Exportar Excel
            </Button>
            <Button
              onClick={() => setShowExpenseForm((v) => !v)}
              variant={showExpenseForm ? 'outline' : 'default'}
            >
              {showExpenseForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
              {showExpenseForm ? 'Cancelar' : 'Nova Despesa'}
            </Button>
          </div>
        </div>

        {/* Inline Expense Form */}
        {showExpenseForm && (
          <Card className="border-dashed border-2 border-red-200 bg-red-50">
            <CardHeader>
              <CardTitle className="text-base text-red-800">Nova Despesa</CardTitle>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={handleSubmit((data) => createExpenseMutation.mutate(data))}
                className="space-y-4"
              >
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="md:col-span-2">
                    <Label htmlFor="description">Descrição *</Label>
                    <Input
                      id="description"
                      placeholder="Ex: Compra de peças"
                      {...register('description')}
                      className="mt-1.5"
                    />
                    {errors.description && (
                      <p className="mt-1 text-xs text-red-600">{errors.description.message}</p>
                    )}
                  </div>
                  <div>
                    <Label htmlFor="amount">Valor (R$) *</Label>
                    <Input
                      id="amount"
                      type="number"
                      step="0.01"
                      min="0.01"
                      placeholder="0,00"
                      {...register('amount')}
                      className="mt-1.5"
                    />
                    {errors.amount && (
                      <p className="mt-1 text-xs text-red-600">{errors.amount.message}</p>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <Label htmlFor="category">Categoria (opcional)</Label>
                    <Input
                      id="category"
                      placeholder="Ex: Peças, Aluguel..."
                      {...register('category')}
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <Label htmlFor="reference_date">Data de Referência *</Label>
                    <Input
                      id="reference_date"
                      type="date"
                      {...register('reference_date')}
                      className="mt-1.5"
                    />
                    {errors.reference_date && (
                      <p className="mt-1 text-xs text-red-600">{errors.reference_date.message}</p>
                    )}
                  </div>
                  <div>
                    <Label htmlFor="notes">Notas (opcional)</Label>
                    <Textarea
                      id="notes"
                      placeholder="Observações adicionais..."
                      {...register('notes')}
                      className="mt-1.5 h-10 resize-none text-sm"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setShowExpenseForm(false)}>
                    Cancelar
                  </Button>
                  <Button type="submit" disabled={createExpenseMutation.isPending}>
                    {createExpenseMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                    {createExpenseMutation.isPending ? 'Salvando...' : 'Lançar Despesa'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Table */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : data?.items?.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <AlertCircle className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhum lançamento encontrado</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Descrição</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead>Data Referência</TableHead>
                  <TableHead>OS Vinculada</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items?.map((entry: FinancialEntry) => (
                  <TableRow key={entry.id}>
                    <TableCell>
                      <EntryTypeBadge type={entry.entry_type} />
                    </TableCell>
                    <TableCell className="text-sm font-medium text-gray-900">{entry.description}</TableCell>
                    <TableCell className="text-sm text-gray-500">{entry.category || '—'}</TableCell>
                    <TableCell className={`text-right font-semibold text-sm ${entry.entry_type === 'RECEITA' ? 'text-green-700' : entry.entry_type === 'DESPESA' ? 'text-red-600' : 'text-gray-700'}`}>
                      {entry.entry_type === 'DESPESA' ? '−' : '+'}{formatCurrency(parseFloat(entry.amount))}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {formatDateOnly(entry.reference_date)}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {entry.service_order_id ? (
                        <span className="font-mono text-xs">{entry.service_order_id.slice(0, 8)}...</span>
                      ) : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>{data.total} lançamento{data.total !== 1 ? 's' : ''}</span>
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
