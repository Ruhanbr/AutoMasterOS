'use client';

import { useRouter } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { ArrowLeft, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { stockApi } from '@/lib/api';
import type { AxiosError } from 'axios';

const stockItemSchema = z.object({
  sku: z.string().min(1, 'SKU é obrigatório'),
  description: z.string().min(2, 'Descrição deve ter ao menos 2 caracteres'),
  ncm_code: z.string().optional(),
  unit: z.enum(['UN', 'KG', 'LT', 'MT', 'CX', 'PC']),
  quantity: z.coerce.number().min(0, 'Quantidade inicial deve ser >= 0'),
  min_quantity: z.coerce.number().min(0, 'Quantidade mínima deve ser >= 0'),
  cost_price: z.coerce.number().min(0, 'Preço de custo deve ser >= 0'),
  sale_price: z.coerce.number().min(0, 'Preço de venda deve ser >= 0'),
});

type StockItemForm = z.infer<typeof stockItemSchema>;

export default function StockNewPage() {
  const router = useRouter();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<StockItemForm>({
    resolver: zodResolver(stockItemSchema),
    defaultValues: {
      unit: 'UN',
      quantity: 0,
      min_quantity: 0,
      cost_price: 0,
      sale_price: 0,
    },
  });

  const createMutation = useMutation({
    mutationFn: async (data: StockItemForm) => {
      const res = await stockApi.create({
        ...data,
        ncm_code: data.ncm_code || null,
      });
      return res.data;
    },
    onSuccess: () => {
      toast.success('Item criado no estoque!');
      router.push('/stock');
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao criar item');
    },
  });

  return (
    <div>
      <Header title="Novo Item de Estoque" />
      <div className="p-6 max-w-2xl mx-auto space-y-6">
        <Link href="/stock">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="w-4 h-4" />
            Voltar ao Estoque
          </Button>
        </Link>

        <Card>
          <CardHeader>
            <CardTitle>Dados do Item</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit((data) => createMutation.mutate(data))} className="space-y-5">
              {/* SKU + Unidade */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="sku">SKU *</Label>
                  <Input
                    id="sku"
                    placeholder="Ex: FILTRO-001"
                    {...register('sku')}
                    className="mt-1.5"
                  />
                  {errors.sku && (
                    <p className="mt-1 text-xs text-red-600">{errors.sku.message}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="unit">Unidade *</Label>
                  <Select id="unit" {...register('unit')} className="mt-1.5">
                    <option value="UN">UN — Unidade</option>
                    <option value="KG">KG — Quilograma</option>
                    <option value="LT">LT — Litro</option>
                    <option value="MT">MT — Metro</option>
                    <option value="CX">CX — Caixa</option>
                    <option value="PC">PC — Peça</option>
                  </Select>
                  {errors.unit && (
                    <p className="mt-1 text-xs text-red-600">{errors.unit.message}</p>
                  )}
                </div>
              </div>

              {/* Descrição */}
              <div>
                <Label htmlFor="description">Descrição *</Label>
                <Input
                  id="description"
                  placeholder="Descrição completa do item"
                  {...register('description')}
                  className="mt-1.5"
                />
                {errors.description && (
                  <p className="mt-1 text-xs text-red-600">{errors.description.message}</p>
                )}
              </div>

              {/* NCM */}
              <div>
                <Label htmlFor="ncm_code">Código NCM (opcional)</Label>
                <Input
                  id="ncm_code"
                  placeholder="00000000"
                  {...register('ncm_code')}
                  className="mt-1.5"
                />
              </div>

              {/* Quantities */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="quantity">Quantidade Inicial *</Label>
                  <Input
                    id="quantity"
                    type="number"
                    step="0.001"
                    min="0"
                    {...register('quantity')}
                    className="mt-1.5"
                  />
                  {errors.quantity && (
                    <p className="mt-1 text-xs text-red-600">{errors.quantity.message}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="min_quantity">Quantidade Mínima *</Label>
                  <Input
                    id="min_quantity"
                    type="number"
                    step="0.001"
                    min="0"
                    {...register('min_quantity')}
                    className="mt-1.5"
                  />
                  {errors.min_quantity && (
                    <p className="mt-1 text-xs text-red-600">{errors.min_quantity.message}</p>
                  )}
                </div>
              </div>

              {/* Prices */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="cost_price">Preço de Custo (R$) *</Label>
                  <Input
                    id="cost_price"
                    type="number"
                    step="0.01"
                    min="0"
                    {...register('cost_price')}
                    className="mt-1.5"
                  />
                  {errors.cost_price && (
                    <p className="mt-1 text-xs text-red-600">{errors.cost_price.message}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="sale_price">Preço de Venda (R$) *</Label>
                  <Input
                    id="sale_price"
                    type="number"
                    step="0.01"
                    min="0"
                    {...register('sale_price')}
                    className="mt-1.5"
                  />
                  {errors.sale_price && (
                    <p className="mt-1 text-xs text-red-600">{errors.sale_price.message}</p>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <Link href="/stock">
                  <Button type="button" variant="outline">Cancelar</Button>
                </Link>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                  {createMutation.isPending ? 'Salvando...' : 'Salvar Item'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
