'use client';

import { useParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import Link from 'next/link';
import { ArrowLeft, AlertCircle, Loader2 } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { formatCurrency, formatDate } from '@/lib/utils';
import type { StockItem, StockMovement, MovementType } from '@/types';
import type { AxiosError } from 'axios';

interface MovementsResponse {
  items: StockMovement[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

const movementSchema = z.object({
  movement_type: z.enum(['ENTRADA', 'SAIDA', 'AJUSTE']),
  quantity: z.coerce.number().min(0.001, 'Quantidade deve ser maior que 0'),
  unit_cost: z.coerce.number().min(0).optional(),
  reason: z.string().optional(),
});

type MovementForm = z.infer<typeof movementSchema>;

function MovementTypeBadge({ type }: { type: MovementType }) {
  switch (type) {
    case 'ENTRADA':
      return <Badge variant="default" className="bg-green-100 text-green-800 border-green-300">ENTRADA</Badge>;
    case 'SAIDA':
      return <Badge variant="destructive" className="bg-red-100 text-red-800 border-red-300">SAÍDA</Badge>;
    case 'AJUSTE':
      return <Badge className="bg-blue-100 text-blue-800 border-blue-300">AJUSTE</Badge>;
    case 'BAIXA_OS':
      return <Badge className="bg-orange-100 text-orange-800 border-orange-300">BAIXA OS</Badge>;
    case 'RESERVA':
      return <Badge variant="secondary">RESERVA</Badge>;
    default:
      return <Badge variant="secondary">{type}</Badge>;
  }
}

function formatQty(value: string): string {
  return parseFloat(value).toLocaleString('pt-BR', { minimumFractionDigits: 3 });
}

export default function StockItemDetailPage() {
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const { data: item, isLoading, error } = useQuery<StockItem>({
    queryKey: ['stock-item', params.id],
    queryFn: async () => {
      const res = await stockApi.get(params.id);
      return res.data;
    },
  });

  const { data: movements } = useQuery<MovementsResponse>({
    queryKey: ['stock-movements', params.id],
    queryFn: async () => {
      const res = await stockApi.listMovements(params.id, { page: 1, page_size: 50 });
      // Backend returns a bare array, not a paginated envelope
      const raw = res.data;
      if (Array.isArray(raw)) {
        return { items: raw, total: raw.length, page: 1, page_size: raw.length, pages: 1 };
      }
      return raw as MovementsResponse;
    },
    enabled: !!item,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<MovementForm>({
    resolver: zodResolver(movementSchema),
    defaultValues: {
      movement_type: 'ENTRADA',
      quantity: undefined,
      unit_cost: undefined,
      reason: '',
    },
  });

  const movementMutation = useMutation({
    mutationFn: async (data: MovementForm) => {
      const res = await stockApi.addMovement(params.id, {
        movement_type: data.movement_type,
        quantity: data.quantity,
        unit_cost: data.unit_cost || null,
        reason: data.reason || null,
      });
      return res.data;
    },
    onSuccess: () => {
      toast.success('Movimentação registrada!');
      queryClient.invalidateQueries({ queryKey: ['stock-item', params.id] });
      queryClient.invalidateQueries({ queryKey: ['stock-movements', params.id] });
      queryClient.invalidateQueries({ queryKey: ['stock'] });
      reset();
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao registrar movimentação');
    },
  });

  if (isLoading) {
    return (
      <div>
        <Header title="Estoque" />
        <PageSpinner />
      </div>
    );
  }

  if (error || !item) {
    return (
      <div>
        <Header title="Estoque" />
        <div className="flex flex-col items-center py-20 text-gray-400">
          <AlertCircle className="w-12 h-12 mb-3" />
          <p>Item não encontrado</p>
          <Link href="/stock" className="mt-4">
            <Button variant="outline" size="sm">Voltar</Button>
          </Link>
        </div>
      </div>
    );
  }

  const isLowStock = parseFloat(item.quantity) <= parseFloat(item.min_quantity);

  return (
    <div>
      <Header title={`Estoque — ${item.sku}`} />
      <div className="p-6 max-w-5xl mx-auto space-y-6">
        {/* Back */}
        <Link href="/stock">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="w-4 h-4" />
            Voltar ao Estoque
          </Button>
        </Link>

        {/* Item Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>{item.description}</span>
              <div className="flex items-center gap-2">
                {isLowStock && (
                  <Badge className="bg-yellow-100 text-yellow-800 border-yellow-300">Estoque Baixo</Badge>
                )}
                {item.active ? (
                  <Badge variant="default">Ativo</Badge>
                ) : (
                  <Badge variant="secondary">Inativo</Badge>
                )}
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">SKU</p>
                <p className="text-sm font-mono font-semibold text-gray-900 mt-1">{item.sku}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Unidade</p>
                <p className="text-sm font-medium text-gray-900 mt-1">{item.unit}</p>
              </div>
              {item.ncm_code && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">NCM</p>
                  <p className="text-sm font-mono text-gray-900 mt-1">{item.ncm_code}</p>
                </div>
              )}
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Quantidade Atual</p>
                <p className={`text-lg font-bold mt-1 ${isLowStock ? 'text-yellow-700' : 'text-gray-900'}`}>
                  {formatQty(item.quantity)} {item.unit}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Quantidade Mínima</p>
                <p className="text-sm font-medium text-gray-700 mt-1">{formatQty(item.min_quantity)} {item.unit}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Preço de Custo</p>
                <p className="text-sm font-medium text-gray-900 mt-1">{formatCurrency(parseFloat(item.cost_price))}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Preço de Venda</p>
                <p className="text-sm font-semibold text-green-700 mt-1">{formatCurrency(parseFloat(item.sale_price))}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Cadastrado em</p>
                <p className="text-sm text-gray-700 mt-1">{formatDate(item.created_at)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Add Movement Card */}
        <Card>
          <CardHeader>
            <CardTitle>Adicionar Movimentação</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={handleSubmit((data) => movementMutation.mutate(data))}
              className="space-y-4"
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <Label htmlFor="movement_type">Tipo *</Label>
                  <Select id="movement_type" {...register('movement_type')} className="mt-1.5">
                    <option value="ENTRADA">ENTRADA</option>
                    <option value="SAIDA">SAÍDA</option>
                    <option value="AJUSTE">AJUSTE</option>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="quantity">Quantidade *</Label>
                  <Input
                    id="quantity"
                    type="number"
                    step="0.001"
                    min="0.001"
                    placeholder="0.000"
                    {...register('quantity')}
                    className="mt-1.5"
                  />
                  {errors.quantity && (
                    <p className="mt-1 text-xs text-red-600">{errors.quantity.message}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="unit_cost">Custo Unitário (opcional)</Label>
                  <Input
                    id="unit_cost"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0,00"
                    {...register('unit_cost')}
                    className="mt-1.5"
                  />
                </div>
                <div>
                  <Label htmlFor="reason">Motivo (opcional)</Label>
                  <Input
                    id="reason"
                    placeholder="Ex: Compra fornecedor"
                    {...register('reason')}
                    className="mt-1.5"
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <Button type="submit" disabled={movementMutation.isPending}>
                  {movementMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                  {movementMutation.isPending ? 'Registrando...' : 'Registrar Movimentação'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Movements History */}
        <Card>
          <CardHeader>
            <CardTitle>Histórico de Movimentações</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {!movements || movements.items.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">Nenhuma movimentação registrada</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Quantidade</TableHead>
                    <TableHead className="text-right">Antes</TableHead>
                    <TableHead className="text-right">Depois</TableHead>
                    <TableHead>Motivo</TableHead>
                    <TableHead>Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {movements.items.map((mov) => (
                    <TableRow key={mov.id}>
                      <TableCell>
                        <MovementTypeBadge type={mov.movement_type} />
                      </TableCell>
                      <TableCell className="text-right font-medium text-gray-900">
                        {formatQty(mov.quantity)}
                      </TableCell>
                      <TableCell className="text-right text-sm text-gray-500">
                        {formatQty(mov.quantity_before)}
                      </TableCell>
                      <TableCell className="text-right text-sm text-gray-700 font-medium">
                        {formatQty(mov.quantity_after)}
                      </TableCell>
                      <TableCell className="text-sm text-gray-500">{mov.reason || '—'}</TableCell>
                      <TableCell className="text-sm text-gray-500">{formatDate(mov.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
