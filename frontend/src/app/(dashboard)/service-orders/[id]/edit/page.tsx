'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2, ArrowLeft, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageSpinner } from '@/components/ui/spinner';
import { serviceOrdersApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import type { ServiceOrder } from '@/types';
import type { AxiosError } from 'axios';

const itemSchema = z.object({
  item_type: z.enum(['SERVICO', 'PECA', 'DESLOCAMENTO']),
  description: z.string().min(1, 'Obrigatório'),
  quantity: z.coerce.number().positive('Deve ser positivo'),
  unit_price: z.coerce.number().min(0, 'Deve ser >= 0'),
});

const schema = z.object({
  description: z.string().min(1, 'Descrição obrigatória'),
  diagnosis: z.string().optional(),
  solution: z.string().optional(),
  technician_notes: z.string().optional(),
  technician_name: z.string().optional(),
  expected_delivery_at: z.string().optional(),
  items: z.array(itemSchema).optional(),
});

type FormData = z.infer<typeof schema>;

function toLocalDatetimeValue(iso?: string | null): string {
  if (!iso) return '';
  return iso.slice(0, 16); // "YYYY-MM-DDTHH:MM"
}

export default function EditServiceOrderPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: os, isLoading } = useQuery<ServiceOrder>({
    queryKey: ['service-order', params.id],
    queryFn: async () => (await serviceOrdersApi.get(params.id)).data,
  });

  const {
    register,
    handleSubmit,
    watch,
    reset,
    control,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { items: [] },
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'items' });

  // Pre-fill form once OS data loads
  useEffect(() => {
    if (!os) return;
    reset({
      description: os.description ?? '',
      diagnosis: os.diagnosis ?? '',
      solution: os.solution ?? '',
      technician_notes: os.technician_notes ?? '',
      technician_name: os.technician_name ?? '',
      expected_delivery_at: toLocalDatetimeValue(os.expected_delivery_at),
      items: os.items?.map((item) => ({
        item_type: item.item_type as 'SERVICO' | 'PECA' | 'DESLOCAMENTO',
        description: item.description,
        quantity: Number(item.quantity),
        unit_price: Number(item.unit_price),
      })) ?? [],
    });
  }, [os, reset]);

  const updateMutation = useMutation({
    mutationFn: async (data: FormData) => {
      const payload = {
        description: data.description || undefined,
        diagnosis: data.diagnosis || undefined,
        solution: data.solution || undefined,
        technician_notes: data.technician_notes || undefined,
        technician_name: data.technician_name || undefined,
        expected_delivery_at: data.expected_delivery_at
          ? new Date(data.expected_delivery_at).toISOString()
          : undefined,
        items: data.items?.length
          ? data.items.map((i) => ({
              item_type: i.item_type,
              description: i.description,
              quantity: i.quantity,
              unit_price: i.unit_price,
            }))
          : undefined,
      };
      return serviceOrdersApi.update(params.id, payload);
    },
    onSuccess: () => {
      toast.success('Ordem de serviço atualizada!');
      queryClient.invalidateQueries({ queryKey: ['service-order', params.id] });
      router.push(`/service-orders/${params.id}`);
    },
    onError: (error: AxiosError<{ detail: { message: string } | string }>) => {
      const detail = error.response?.data?.detail;
      const msg = typeof detail === 'object' ? detail.message : detail;
      toast.error(msg || 'Erro ao atualizar ordem de serviço');
    },
  });

  const watchedItems = watch('items') || [];
  const total = watchedItems.reduce(
    (sum, item) => sum + (Number(item.quantity) || 0) * (Number(item.unit_price) || 0),
    0,
  );

  if (isLoading) {
    return (
      <div>
        <Header title="Editar OS" />
        <PageSpinner />
      </div>
    );
  }

  if (!os) {
    return (
      <div>
        <Header title="Editar OS" />
        <div className="p-6 text-sm text-gray-500">OS não encontrada.</div>
      </div>
    );
  }

  return (
    <div>
      <Header title={`Editar OS #${os.number}`} />
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <Link href={`/service-orders/${params.id}`}>
          <Button variant="ghost" size="sm" className="gap-2 text-gray-500">
            <ArrowLeft className="w-4 h-4" />
            Voltar
          </Button>
        </Link>

        <form onSubmit={handleSubmit((data) => updateMutation.mutate(data))} className="space-y-6">

          {/* ── Informações do Cliente (read-only) ─────────────────────── */}
          {os.client && (
            <Card className="border-gray-200 bg-gray-50">
              <CardContent className="pt-4 pb-3 flex flex-wrap gap-6 text-sm">
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-0.5">Cliente</p>
                  <p className="font-medium text-gray-800">{os.client.name}</p>
                </div>
                {os.machine && (
                  <div>
                    <p className="text-xs text-gray-400 uppercase tracking-wider mb-0.5">Máquina</p>
                    <p className="font-medium text-gray-800">
                      {os.machine.brand} {os.machine.model}
                      {os.machine.year ? ` (${os.machine.year})` : ''}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* ── Campos principais ───────────────────────────────────────── */}
          <Card>
            <CardHeader>
              <CardTitle>Informações da OS</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <Label htmlFor="description">Descrição do Problema *</Label>
                <Textarea
                  id="description"
                  placeholder="Descreva o problema ou serviço solicitado..."
                  {...register('description')}
                  className="mt-1.5"
                  rows={3}
                />
                {errors.description && (
                  <p className="mt-1 text-xs text-red-600">{errors.description.message}</p>
                )}
              </div>

              <div>
                <Label htmlFor="diagnosis">Diagnóstico</Label>
                <Textarea
                  id="diagnosis"
                  placeholder="Diagnóstico técnico identificado..."
                  {...register('diagnosis')}
                  className="mt-1.5"
                  rows={3}
                />
              </div>

              <div>
                <Label htmlFor="solution">Solução Aplicada</Label>
                <Textarea
                  id="solution"
                  placeholder="Descreva a solução aplicada..."
                  {...register('solution')}
                  className="mt-1.5"
                  rows={3}
                />
              </div>

              <div>
                <Label htmlFor="technician_notes">Observações do Técnico</Label>
                <Textarea
                  id="technician_notes"
                  placeholder="Observações internas do técnico..."
                  {...register('technician_notes')}
                  className="mt-1.5"
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="technician_name">Técnico Responsável</Label>
                  <Input
                    id="technician_name"
                    placeholder="Nome do técnico"
                    {...register('technician_name')}
                    className="mt-1.5"
                  />
                </div>
                <div>
                  <Label htmlFor="expected_delivery_at">Previsão de Entrega</Label>
                  <Input
                    id="expected_delivery_at"
                    type="datetime-local"
                    {...register('expected_delivery_at')}
                    className="mt-1.5"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ── Itens ─────────────────────────────────────────────────────── */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Itens da OS</CardTitle>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    append({ item_type: 'SERVICO', description: '', quantity: 1, unit_price: 0 })
                  }
                >
                  <Plus className="w-4 h-4" />
                  Adicionar Item
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {fields.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-6">
                  Nenhum item. Clique em &quot;Adicionar Item&quot; para incluir serviços ou peças.
                </p>
              ) : (
                <div className="space-y-3">
                  {fields.map((field, index) => (
                    <div
                      key={field.id}
                      className="grid grid-cols-12 gap-3 items-start border border-gray-200 rounded-lg p-3 bg-gray-50"
                    >
                      <div className="col-span-12 sm:col-span-2">
                        <Label className="text-xs">Tipo</Label>
                        <Select {...register(`items.${index}.item_type`)} className="mt-1">
                          <option value="SERVICO">Serviço</option>
                          <option value="PECA">Peça</option>
                          <option value="DESLOCAMENTO">Deslocamento</option>
                        </Select>
                      </div>

                      <div className="col-span-12 sm:col-span-5">
                        <Label className="text-xs">Descrição</Label>
                        <Input
                          placeholder="Descrição do item"
                          {...register(`items.${index}.description`)}
                          className="mt-1"
                        />
                        {errors.items?.[index]?.description && (
                          <p className="mt-0.5 text-xs text-red-600">
                            {errors.items[index]?.description?.message}
                          </p>
                        )}
                      </div>

                      <div className="col-span-5 sm:col-span-2">
                        <Label className="text-xs">Qtd</Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0.01"
                          {...register(`items.${index}.quantity`)}
                          className="mt-1"
                        />
                      </div>

                      <div className="col-span-6 sm:col-span-2">
                        <Label className="text-xs">Preço Unit.</Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="0,00"
                          {...register(`items.${index}.unit_price`)}
                          className="mt-1"
                        />
                      </div>

                      <div className="col-span-1 flex items-end pb-0.5">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => remove(index)}
                          className="text-red-500 hover:text-red-700 hover:bg-red-50 mt-4"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  ))}

                  <div className="flex justify-end pt-2 border-t border-gray-200">
                    <div className="text-right">
                      <span className="text-sm text-gray-500">Total estimado:</span>
                      <p className="text-xl font-bold text-gray-900">{formatCurrency(total)}</p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── Actions ─────────────────────────────────────────────────── */}
          <div className="flex justify-end gap-3 pb-6">
            <Link href={`/service-orders/${params.id}`}>
              <Button type="button" variant="outline">
                Cancelar
              </Button>
            </Link>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {updateMutation.isPending ? 'Salvando...' : 'Salvar Alterações'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
