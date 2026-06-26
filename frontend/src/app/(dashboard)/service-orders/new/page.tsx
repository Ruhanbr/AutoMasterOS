'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2, ArrowLeft, Loader2, Wrench, Search, Package } from 'lucide-react';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { serviceOrdersApi, clientsApi, machinesApi, stockApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import type { Client, Machine, PaginatedResponse, StockItem, StockItemListResponse } from '@/types';
import type { AxiosError } from 'axios';

const itemSchema = z.object({
  item_type: z.enum(['SERVICO', 'PECA', 'DESLOCAMENTO']),
  description: z.string().min(1, 'Obrigatório'),
  quantity: z.coerce.number().positive('Deve ser positivo'),
  unit_price: z.coerce.number().min(0, 'Deve ser >= 0'),
  stock_item_id: z.string().optional(),
});

const schema = z.object({
  client_id: z.string().min(1, 'Selecione um cliente'),
  machine_id: z.string().optional(),
  description: z.string().min(1, 'Descrição obrigatória'),
  technician_name: z.string().optional(),
  items: z.array(itemSchema).optional(),
});

type FormData = z.infer<typeof schema>;

export default function NewServiceOrderPage() {
  const router = useRouter();
  const [clientSearch, setClientSearch] = useState('');
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [showClientDropdown, setShowClientDropdown] = useState(false);
  const [openStockPicker, setOpenStockPicker] = useState<number | null>(null);
  const [stockSearch, setStockSearch] = useState<Record<number, string>>({});

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    control,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { items: [] },
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'items' });

  // ── Client search ──────────────────────────────────────────────────────────
  const { data: clientsData } = useQuery<PaginatedResponse<Client>>({
    queryKey: ['clients-search', clientSearch],
    queryFn: async () => {
      const res = await clientsApi.list({
        name: clientSearch || undefined,
        page_size: 8,
        active_only: true,
      });
      return res.data;
    },
    enabled: clientSearch.length >= 1 && !selectedClient,
  });

  // ── Stock items ───────────────────────────────────────────────────────────
  const { data: stockData } = useQuery<StockItemListResponse>({
    queryKey: ['stock-items'],
    queryFn: async () => (await stockApi.list({ page_size: 500 })).data,
    staleTime: 120_000,
  });
  const allStock: StockItem[] = stockData?.items?.filter((i) => i.active) ?? [];

  const filteredStock = (idx: number) => {
    const q = (stockSearch[idx] ?? '').toLowerCase().trim();
    const items = q
      ? allStock.filter((i) => i.description.toLowerCase().includes(q) || i.sku.toLowerCase().includes(q))
      : allStock;
    return items.slice(0, 10);
  };

  // ── Machine list for selected client ──────────────────────────────────────
  const { data: machinesData, isLoading: machinesLoading } = useQuery<PaginatedResponse<Machine>>({
    queryKey: ['machines-by-client', selectedClient?.id],
    queryFn: async () => {
      const res = await machinesApi.listByClient(selectedClient!.id, { page_size: 50 });
      return res.data;
    },
    enabled: !!selectedClient,
  });

  const clientMachines = machinesData?.items?.filter((m) => m.active) ?? [];

  // ── Submit ─────────────────────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: async (data: FormData) => {
      const res = await serviceOrdersApi.create({
        client_id: data.client_id,
        machine_id: data.machine_id || undefined,
        description: data.description,
        technician_name: data.technician_name || undefined,
        items: data.items?.length
          ? data.items.map((it) => ({
              item_type: it.item_type,
              description: it.description,
              quantity: it.quantity,
              unit_price: it.unit_price,
              stock_item_id: it.stock_item_id || undefined,
            }))
          : undefined,
      });
      return res.data;
    },
    onSuccess: (data) => {
      toast.success('Ordem de serviço criada com sucesso!');
      router.push(`/service-orders/${data.id}`);
    },
    onError: (error: AxiosError<{ detail: { message: string } | string }>) => {
      const detail = error.response?.data?.detail;
      const msg = typeof detail === 'object' ? detail.message : detail;
      toast.error(msg || 'Erro ao criar ordem de serviço');
    },
  });

  const watchedItems = watch('items') || [];
  const total = watchedItems.reduce(
    (sum, item) => sum + (Number(item.quantity) || 0) * (Number(item.unit_price) || 0),
    0,
  );

  return (
    <div>
      <Header title="Nova Ordem de Serviço" />
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <Link href="/service-orders">
          <Button variant="ghost" size="sm" className="gap-2 text-gray-500">
            <ArrowLeft className="w-4 h-4" />
            Voltar
          </Button>
        </Link>

        <form onSubmit={handleSubmit((data) => createMutation.mutate(data))} className="space-y-6">
          {/* ── Cliente + Máquina ─────────────────────────────────────────── */}
          <Card>
            <CardHeader>
              <CardTitle>Cliente e Máquina</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Client selector */}
              <div>
                <Label>Cliente *</Label>
                {selectedClient ? (
                  <div className="mt-1.5 flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
                    <div>
                      <p className="font-medium text-gray-900 text-sm">{selectedClient.name}</p>
                      <p className="text-xs text-gray-500">{selectedClient.document}</p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-gray-400 hover:text-gray-600"
                      onClick={() => {
                        setSelectedClient(null);
                        setClientSearch('');
                        setValue('client_id', '');
                        setValue('machine_id', '');
                      }}
                    >
                      Trocar
                    </Button>
                  </div>
                ) : (
                  <div className="mt-1.5 relative">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <Input
                        placeholder="Digite o nome do cliente..."
                        value={clientSearch}
                        onChange={(e) => {
                          setClientSearch(e.target.value);
                          setShowClientDropdown(true);
                        }}
                        onFocus={() => setShowClientDropdown(true)}
                        className="pl-9"
                      />
                    </div>
                    {showClientDropdown && clientsData?.items && clientsData.items.length > 0 && clientSearch && (
                      <div className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg divide-y divide-gray-100 max-h-52 overflow-y-auto">
                        {clientsData.items.map((c) => (
                          <button
                            key={c.id}
                            type="button"
                            className="w-full text-left px-4 py-2.5 hover:bg-gray-50 transition-colors"
                            onClick={() => {
                              setSelectedClient(c);
                              setValue('client_id', c.id);
                              setValue('machine_id', '');
                              setShowClientDropdown(false);
                              setClientSearch('');
                            }}
                          >
                            <p className="text-sm font-medium text-gray-900">{c.name}</p>
                            <p className="text-xs text-gray-500">{c.document}</p>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {errors.client_id && (
                  <p className="mt-1 text-xs text-red-600">{errors.client_id.message}</p>
                )}
              </div>

              {/* Machine selector — appears only when client is selected */}
              {selectedClient && (
                <div>
                  <Label htmlFor="machine_id" className="flex items-center gap-1.5">
                    <Wrench className="w-3.5 h-3.5 text-gray-400" />
                    Máquina
                    <span className="text-xs text-gray-400 font-normal">(opcional)</span>
                  </Label>
                  {machinesLoading ? (
                    <div className="mt-1.5 flex items-center gap-2 text-sm text-gray-400 py-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Carregando máquinas...
                    </div>
                  ) : clientMachines.length === 0 ? (
                    <div className="mt-1.5 flex items-center gap-2 text-sm text-gray-400 py-2">
                      <Wrench className="w-4 h-4" />
                      Nenhuma máquina ativa cadastrada para este cliente.
                      <Link
                        href="/machines/new"
                        className="text-green-600 hover:underline ml-1"
                      >
                        Cadastrar
                      </Link>
                    </div>
                  ) : (
                    <Select id="machine_id" {...register('machine_id')} className="mt-1.5">
                      <option value="">— Sem máquina —</option>
                      {clientMachines.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.brand} {m.model}
                          {m.year ? ` (${m.year})` : ''}
                          {m.placa ? ` · ${m.placa}` : ''}
                          {' · '}{m.serial_number}
                        </option>
                      ))}
                    </Select>
                  )}
                  {clientMachines.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {clientMachines.slice(0, 3).map((m) => (
                        <Badge
                          key={m.id}
                          variant="secondary"
                          className="text-xs cursor-pointer hover:bg-green-100"
                          onClick={() => setValue('machine_id', m.id)}
                        >
                          {m.brand} {m.model}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Description */}
              <div>
                <Label htmlFor="description">Descrição do Problema *</Label>
                <Textarea
                  id="description"
                  placeholder="Descreva o problema ou serviço solicitado..."
                  {...register('description')}
                  className="mt-1.5"
                />
                {errors.description && (
                  <p className="mt-1 text-xs text-red-600">{errors.description.message}</p>
                )}
              </div>

              {/* Technician */}
              <div>
                <Label htmlFor="technician_name">Técnico Responsável</Label>
                <Input
                  id="technician_name"
                  placeholder="Nome do técnico"
                  {...register('technician_name')}
                  className="mt-1.5"
                />
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
                  Nenhum item adicionado. Clique em &quot;Adicionar Item&quot; para começar.
                </p>
              ) : (
                <div className="space-y-3">
                  {fields.map((field, index) => (
                    <div
                      key={field.id}
                      className="grid grid-cols-12 gap-3 items-start border border-gray-200 rounded-lg p-3 bg-gray-50"
                    >
                      <div className="col-span-2">
                        <Label className="text-xs">Tipo</Label>
                        <Select
                          {...register(`items.${index}.item_type`)}
                          className="mt-1"
                          onChange={(e) => {
                            setValue(`items.${index}.item_type`, e.target.value as 'SERVICO' | 'PECA' | 'DESLOCAMENTO');
                            setValue(`items.${index}.stock_item_id`, undefined);
                          }}
                        >
                          <option value="SERVICO">Serviço</option>
                          <option value="PECA">Peça</option>
                          <option value="DESLOCAMENTO">Deslocamento</option>
                        </Select>
                      </div>

                      <div className="col-span-5">
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

                      <div className="col-span-2">
                        <Label className="text-xs">Qtd</Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0.01"
                          {...register(`items.${index}.quantity`)}
                          className="mt-1"
                        />
                      </div>

                      <div className="col-span-2">
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

                      {/* Stock picker — only for PECA */}
                      {watchedItems[index]?.item_type === 'PECA' && (
                        <div className="col-span-12 -mt-1">
                          {openStockPicker === index ? (
                            <div className="border border-blue-200 rounded-lg p-2 bg-blue-50">
                              <input
                                type="text"
                                autoFocus
                                placeholder="Buscar por nome ou SKU..."
                                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5 mb-2 bg-white outline-none focus:ring-2 focus:ring-blue-400"
                                value={stockSearch[index] ?? ''}
                                onChange={(e) => setStockSearch((p) => ({ ...p, [index]: e.target.value }))}
                              />
                              <div className="max-h-44 overflow-y-auto space-y-0.5">
                                {filteredStock(index).length === 0 ? (
                                  <p className="text-xs text-gray-400 text-center py-3">Nenhuma peça encontrada no estoque</p>
                                ) : filteredStock(index).map((item) => (
                                  <button
                                    key={item.id}
                                    type="button"
                                    className="w-full text-left px-3 py-2 hover:bg-white rounded-lg flex items-center justify-between gap-2 transition-colors"
                                    onClick={() => {
                                      setValue(`items.${index}.description`, item.description);
                                      setValue(`items.${index}.unit_price`, Number(item.sale_price));
                                      setValue(`items.${index}.stock_item_id`, item.id);
                                      setOpenStockPicker(null);
                                      setStockSearch((p) => ({ ...p, [index]: '' }));
                                    }}
                                  >
                                    <div className="min-w-0">
                                      <p className="text-sm font-medium text-gray-800 truncate">{item.description}</p>
                                      <p className="text-xs text-gray-400">SKU: {item.sku} · Estoque: {Number(item.quantity).toFixed(2)} {item.unit}</p>
                                    </div>
                                    <span className="text-sm font-semibold text-green-700 flex-shrink-0">
                                      {formatCurrency(Number(item.sale_price))}
                                    </span>
                                  </button>
                                ))}
                              </div>
                              <button
                                type="button"
                                className="mt-1.5 text-xs text-gray-400 hover:text-gray-600"
                                onClick={() => setOpenStockPicker(null)}
                              >
                                Fechar
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 ml-0.5"
                              onClick={() => setOpenStockPicker(index)}
                            >
                              <Package className="w-3 h-3" />
                              Selecionar do estoque
                            </button>
                          )}
                        </div>
                      )}
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

          {/* ── Actions ───────────────────────────────────────────────────── */}
          <div className="flex justify-end gap-3">
            <Link href="/service-orders">
              <Button type="button" variant="outline">
                Cancelar
              </Button>
            </Link>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {createMutation.isPending ? 'Criando...' : 'Criar Ordem de Serviço'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
