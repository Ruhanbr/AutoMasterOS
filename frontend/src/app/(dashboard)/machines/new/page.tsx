'use client';

import { Suspense, useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import Link from 'next/link';
import { ArrowLeft, Loader2, Search } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { machinesApi, clientsApi } from '@/lib/api';
import { MACHINE_TYPES } from '@/types';
import type { Client, PaginatedResponse } from '@/types';
import type { AxiosError } from 'axios';

const machineSchema = z.object({
  client_id: z.string().uuid('Selecione um cliente válido'),
  machine_type: z.enum([
    'Tratores',
    'Colheitadeiras',
    'Plantadeiras',
    'Semeadoras',
    'Pulverizadores',
    'Outros',
  ]),
  brand: z.string().min(1, 'Marca é obrigatória'),
  model: z.string().min(1, 'Modelo é obrigatório'),
  serial_number: z.string().min(1, 'Número de série é obrigatório'),
  year: z.coerce.number().min(1900).max(2100).optional().or(z.literal('')),
  placa: z.string().max(20).optional().or(z.literal('')),
  proprietario: z.string().max(200).optional().or(z.literal('')),
  color: z.string().optional().or(z.literal('')),
  engine_number: z.string().optional().or(z.literal('')),
  horsepower: z.string().optional().or(z.literal('')),
  chassis_number: z.string().optional().or(z.literal('')),
  notes: z.string().optional().or(z.literal('')),
});

type MachineForm = z.infer<typeof machineSchema>;

function NewMachinePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const clientIdFromUrl = searchParams.get('client_id');

  const [clientSearch, setClientSearch] = useState('');
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);

  // Back/cancel destination — preserves client context if coming from a client's machine list
  const backHref = clientIdFromUrl
    ? `/machines?client_id=${clientIdFromUrl}`
    : '/machines';

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<MachineForm>({
    resolver: zodResolver(machineSchema),
    defaultValues: { machine_type: 'Tratores' },
  });

  // Auto-fetch and pre-select client when coming from /clients page
  const { data: preloadedClient } = useQuery({
    queryKey: ['client-detail', clientIdFromUrl],
    queryFn: async () => {
      if (!clientIdFromUrl) return null;
      const res = await clientsApi.get(clientIdFromUrl);
      return res.data as Client;
    },
    enabled: !!clientIdFromUrl && !selectedClient,
    staleTime: 60_000,
  });

  // Once preloaded client arrives, set it as selected
  useEffect(() => {
    if (preloadedClient && !selectedClient) {
      setSelectedClient(preloadedClient);
      setValue('client_id', preloadedClient.id);
    }
  }, [preloadedClient, selectedClient, setValue]);

  // Search clients (only active when not pre-filled)
  const { data: clientsData } = useQuery<PaginatedResponse<Client>>({
    queryKey: ['clients-search', clientSearch],
    queryFn: async () => {
      const res = await clientsApi.list({ name: clientSearch || undefined, page_size: 10 });
      return res.data;
    },
    enabled: clientSearch.length >= 1 && !selectedClient,
  });

  const createMutation = useMutation({
    mutationFn: async (data: MachineForm) => {
      const payload = {
        client_id: data.client_id,
        machine_type: data.machine_type,
        brand: data.brand,
        model: data.model,
        serial_number: data.serial_number,
        year: data.year || undefined,
        placa: data.placa || undefined,
        proprietario: data.proprietario || undefined,
        color: data.color || undefined,
        engine_number: data.engine_number || undefined,
        horsepower: data.horsepower || undefined,
        chassis_number: data.chassis_number || undefined,
        notes: data.notes || undefined,
      };
      const res = await machinesApi.create(payload);
      return res.data;
    },
    onSuccess: (machine) => {
      toast.success('Máquina cadastrada com sucesso!');
      router.push(`/machines/${machine.id}`);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao cadastrar máquina');
    },
  });

  return (
    <div>
      <Header title="Nova Máquina" />
      <div className="p-6 max-w-3xl mx-auto space-y-6">
        {/* Back */}
        <Link href={backHref}>
          <Button variant="ghost" size="sm" className="gap-2 text-gray-500">
            <ArrowLeft className="w-4 h-4" />
            Voltar para Máquinas
          </Button>
        </Link>

        <form onSubmit={handleSubmit((data) => createMutation.mutate(data))} className="space-y-6">
          {/* Client */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Cliente Proprietário *</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {selectedClient ? (
                <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900">{selectedClient.name}</p>
                    <p className="text-xs text-gray-500">{selectedClient.document}</p>
                  </div>
                  {/* Only allow changing the client if we didn't come from a specific client page */}
                  {!clientIdFromUrl && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-gray-400"
                      onClick={() => {
                        setSelectedClient(null);
                        setClientSearch('');
                        setValue('client_id', '' as never);
                      }}
                    >
                      Trocar
                    </Button>
                  )}
                </div>
              ) : (
                <div>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <Input
                      placeholder="Digite o nome do cliente..."
                      value={clientSearch}
                      onChange={(e) => setClientSearch(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                  {clientsData?.items && clientsData.items.length > 0 && clientSearch && (
                    <div className="mt-1 border border-gray-200 rounded-lg shadow-sm bg-white divide-y divide-gray-100 max-h-48 overflow-y-auto">
                      {clientsData.items.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          className="w-full text-left px-4 py-2.5 hover:bg-gray-50 transition-colors"
                          onClick={() => {
                            setSelectedClient(c);
                            setValue('client_id', c.id);
                            setClientSearch('');
                          }}
                        >
                          <p className="text-sm font-medium text-gray-900">{c.name}</p>
                          <p className="text-xs text-gray-500">{c.document}</p>
                        </button>
                      ))}
                    </div>
                  )}
                  {errors.client_id && (
                    <p className="mt-1 text-xs text-red-600">{errors.client_id.message}</p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Machine data */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Dados da Máquina</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Type */}
              <div>
                <Label htmlFor="machine_type">Tipo *</Label>
                <Select id="machine_type" {...register('machine_type')} className="mt-1.5">
                  {MACHINE_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </Select>
                {errors.machine_type && (
                  <p className="mt-1 text-xs text-red-600">{errors.machine_type.message}</p>
                )}
              </div>

              {/* Brand + Model */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="brand">Marca *</Label>
                  <Input
                    id="brand"
                    placeholder="Ex: John Deere"
                    {...register('brand')}
                    className="mt-1.5"
                  />
                  {errors.brand && (
                    <p className="mt-1 text-xs text-red-600">{errors.brand.message}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="model">Modelo *</Label>
                  <Input
                    id="model"
                    placeholder="Ex: 7200"
                    {...register('model')}
                    className="mt-1.5"
                  />
                  {errors.model && (
                    <p className="mt-1 text-xs text-red-600">{errors.model.message}</p>
                  )}
                </div>
              </div>

              {/* Serial + Year */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="serial_number">Número de Série *</Label>
                  <Input
                    id="serial_number"
                    placeholder="Ex: JD-12345678"
                    {...register('serial_number')}
                    className="mt-1.5 uppercase"
                  />
                  {errors.serial_number && (
                    <p className="mt-1 text-xs text-red-600">{errors.serial_number.message}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="year">Ano de Fabricação</Label>
                  <Input
                    id="year"
                    type="number"
                    placeholder="Ex: 2022"
                    min={1900}
                    max={2100}
                    {...register('year')}
                    className="mt-1.5"
                  />
                  {errors.year && (
                    <p className="mt-1 text-xs text-red-600">{String(errors.year.message)}</p>
                  )}
                </div>
              </div>

              {/* Placa + Proprietario */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="placa">Placa</Label>
                  <Input
                    id="placa"
                    placeholder="Ex: ABC1D23"
                    {...register('placa')}
                    className="mt-1.5 uppercase"
                  />
                </div>
                <div>
                  <Label htmlFor="proprietario">Proprietário</Label>
                  <Input
                    id="proprietario"
                    placeholder="Nome do proprietário"
                    {...register('proprietario')}
                    className="mt-1.5"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Technical details */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Dados Técnicos (opcional)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="color">Cor</Label>
                  <Input
                    id="color"
                    placeholder="Ex: Verde"
                    {...register('color')}
                    className="mt-1.5"
                  />
                </div>
                <div>
                  <Label htmlFor="horsepower">Potência (CV)</Label>
                  <Input
                    id="horsepower"
                    placeholder="Ex: 150 CV"
                    {...register('horsepower')}
                    className="mt-1.5"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="engine_number">N° do Motor</Label>
                  <Input
                    id="engine_number"
                    placeholder="Ex: MOT-12345"
                    {...register('engine_number')}
                    className="mt-1.5"
                  />
                </div>
                <div>
                  <Label htmlFor="chassis_number">N° do Chassi</Label>
                  <Input
                    id="chassis_number"
                    placeholder="Ex: 9BM123456AB789012"
                    {...register('chassis_number')}
                    className="mt-1.5 uppercase"
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="notes">Observações</Label>
                <textarea
                  id="notes"
                  rows={3}
                  placeholder="Informações adicionais sobre a máquina..."
                  {...register('notes')}
                  className="mt-1.5 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500 resize-none"
                />
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex justify-end gap-3 pb-6">
            <Link href={backHref}>
              <Button type="button" variant="outline">
                Cancelar
              </Button>
            </Link>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {createMutation.isPending ? 'Salvando...' : 'Cadastrar Máquina'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function NewMachinePage() {
  return (
    <Suspense>
      <NewMachinePageContent />
    </Suspense>
  );
}
