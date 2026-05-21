'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import Link from 'next/link';
import {
  ArrowLeft,
  AlertCircle,
  Loader2,
  Pencil,
  Trash2,
  CheckCircle,
  Wrench,
  ClipboardList,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Dialog, DialogHeader, DialogBody, DialogFooter } from '@/components/ui/dialog';
import { PageSpinner } from '@/components/ui/spinner';
import { machinesApi } from '@/lib/api';
import { formatDate } from '@/lib/utils';
import { MACHINE_TYPES } from '@/types';
import type { Machine, PaginatedResponse, ServiceOrder } from '@/types';
import type { AxiosError } from 'axios';

const updateSchema = z.object({
  machine_type: z.enum([
    'Tratores', 'Colheitadeiras', 'Plantadeiras',
    'Semeadoras', 'Pulverizadores', 'Outros',
  ]).optional(),
  brand: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  year: z.coerce.number().min(1900).max(2100).optional().or(z.literal('')),
  placa: z.string().max(20).optional().or(z.literal('')),
  proprietario: z.string().max(200).optional().or(z.literal('')),
  color: z.string().optional().or(z.literal('')),
  engine_number: z.string().optional().or(z.literal('')),
  horsepower: z.string().optional().or(z.literal('')),
  chassis_number: z.string().optional().or(z.literal('')),
  notes: z.string().optional().or(z.literal('')),
});

type UpdateForm = z.infer<typeof updateSchema>;

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  ABERTA:       { label: 'Aberta',       cls: 'bg-blue-100 text-blue-800 border-blue-200' },
  EM_ANDAMENTO: { label: 'Em Andamento', cls: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
  FINALIZADA:   { label: 'Finalizada',   cls: 'bg-green-100 text-green-800 border-green-200' },
};

function Field({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-0.5 text-sm text-gray-900">{value || '—'}</p>
    </div>
  );
}

export default function MachineDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: machine, isLoading, error } = useQuery<Machine>({
    queryKey: ['machine', params.id],
    queryFn: async () => {
      const res = await machinesApi.get(params.id);
      return res.data;
    },
  });

  const [osPage, setOsPage] = useState(1);
  const OS_PAGE_SIZE = 10;

  // Usa o endpoint dedicado GET /machines/{id}/os (cache Redis 5 min no backend)
  const { data: ordersData, isLoading: osLoading } = useQuery<PaginatedResponse<ServiceOrder>>({
    queryKey: ['machine-orders', params.id, osPage],
    queryFn: async () => {
      const res = await machinesApi.listOS(params.id, { page: osPage, page_size: OS_PAGE_SIZE });
      return res.data;
    },
    enabled: !!machine,
  });

  const relatedOrders = ordersData?.items ?? [];

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UpdateForm>({
    resolver: zodResolver(updateSchema),
  });

  const updateMutation = useMutation({
    mutationFn: async (data: UpdateForm) => {
      const payload: Record<string, unknown> = {};
      Object.entries(data).forEach(([k, v]) => {
        if (v !== '' && v !== undefined) payload[k] = v;
      });
      const res = await machinesApi.update(params.id, payload);
      return res.data;
    },
    onSuccess: () => {
      toast.success('Máquina atualizada!');
      queryClient.invalidateQueries({ queryKey: ['machine', params.id] });
      queryClient.invalidateQueries({ queryKey: ['machines'] });
      setEditing(false);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar');
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: () => machinesApi.deactivate(params.id),
    onSuccess: () => {
      toast.success('Máquina desativada!');
      router.push('/machines');
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Não foi possível desativar');
      setConfirmDelete(false);
    },
  });

  const reactivateMutation = useMutation({
    mutationFn: () => machinesApi.reactivate(params.id),
    onSuccess: () => {
      toast.success('Máquina reativada!');
      queryClient.invalidateQueries({ queryKey: ['machine', params.id] });
      queryClient.invalidateQueries({ queryKey: ['machines'] });
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Não foi possível reativar');
    },
  });

  if (isLoading) return <PageSpinner />;

  if (error || !machine) {
    return (
      <div>
        <Header title="Máquina" />
        <div className="p-6 flex flex-col items-center py-20 text-gray-400">
          <AlertCircle className="w-12 h-12 mb-3" />
          <p className="text-sm">Máquina não encontrada</p>
          <Link href="/machines" className="mt-4">
            <Button variant="outline" size="sm">Voltar</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header title={`${machine.brand} ${machine.model}`} />
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        {/* Back + actions */}
        <div className="flex items-center justify-between">
          <Link href="/machines">
            <Button variant="ghost" size="sm" className="gap-2 text-gray-500">
              <ArrowLeft className="w-4 h-4" />
              Máquinas
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            {machine.active && !editing && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    reset({
                      machine_type: machine.machine_type,
                      brand: machine.brand,
                      model: machine.model,
                      year: machine.year ?? '',
                      placa: machine.placa ?? '',
                      proprietario: machine.proprietario ?? '',
                      color: machine.color ?? '',
                      engine_number: machine.engine_number ?? '',
                      horsepower: machine.horsepower ?? '',
                      chassis_number: machine.chassis_number ?? '',
                      notes: machine.notes ?? '',
                    });
                    setEditing(true);
                  }}
                >
                  <Pencil className="w-4 h-4" />
                  Editar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-500 border-red-200 hover:bg-red-50"
                  onClick={() => setConfirmDelete(true)}
                >
                  <Trash2 className="w-4 h-4" />
                  Desativar
                </Button>
              </>
            )}
            {!machine.active && !editing && (
              <>
                <Badge variant="secondary" className="text-sm">
                  Máquina Inativa
                </Badge>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-green-600 border-green-200 hover:bg-green-50"
                  onClick={() => reactivateMutation.mutate()}
                  disabled={reactivateMutation.isPending}
                >
                  {reactivateMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <RotateCcw className="w-4 h-4" />
                  )}
                  Reativar Máquina
                </Button>
              </>
            )}
          </div>
        </div>

        {/* View mode */}
        {!editing ? (
          <>
            {/* Header card */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-start gap-4">
                  <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-green-50 border border-green-100">
                    <Wrench className="w-7 h-7 text-green-600" />
                  </div>
                  <div className="flex-1">
                    <p className="text-xs font-mono font-semibold text-gray-500 tracking-wider uppercase mb-1">
                      {machine.serial_number}
                    </p>
                    <div className="flex items-center gap-3 flex-wrap">
                      <h2 className="text-xl font-bold text-gray-900">
                        {machine.brand} {machine.model}
                      </h2>
                      <Badge className={
                        machine.machine_type === 'Tratores' ? 'bg-green-100 text-green-800 border-green-200' :
                        machine.machine_type === 'Colheitadeiras' ? 'bg-yellow-100 text-yellow-800 border-yellow-200' :
                        'bg-blue-100 text-blue-800 border-blue-200'
                      }>
                        {machine.machine_type}
                      </Badge>
                      {machine.active ? (
                        <Badge variant="default" className="bg-emerald-100 text-emerald-700 border-emerald-200">
                          <CheckCircle className="w-3 h-3 mr-1" />
                          Ativa
                        </Badge>
                      ) : (
                        <Badge variant="secondary">Inativa</Badge>
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-6 border-t border-gray-100 pt-6">
                  <Field label="Placa" value={machine.placa} />
                  <Field label="Ano" value={machine.year} />
                  <Field label="Cor" value={machine.color} />
                  <Field label="Proprietário" value={machine.proprietario} />
                </div>
              </CardContent>
            </Card>

            {/* Client + Technical */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-semibold text-gray-700">Cliente</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Field label="Nome" value={machine.client?.name} />
                  <Field label="Documento" value={machine.client?.document} />
                  <Field label="Telefone" value={machine.client?.phone} />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-semibold text-gray-700">Dados Técnicos</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Field label="N° do Motor" value={machine.engine_number} />
                  <Field label="N° do Chassi" value={machine.chassis_number} />
                  <Field label="Potência" value={machine.horsepower} />
                  <Field label="Observações" value={machine.notes} />
                </CardContent>
              </Card>
            </div>
          </>
        ) : (
          /* Edit mode */
          <form onSubmit={handleSubmit((data) => updateMutation.mutate(data))}>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Editar Máquina</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="machine_type">Tipo</Label>
                  <Select id="machine_type" {...register('machine_type')} className="mt-1.5">
                    {MACHINE_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="brand">Marca</Label>
                    <Input id="brand" {...register('brand')} className="mt-1.5" />
                    {errors.brand && <p className="mt-1 text-xs text-red-600">{errors.brand.message}</p>}
                  </div>
                  <div>
                    <Label htmlFor="model">Modelo</Label>
                    <Input id="model" {...register('model')} className="mt-1.5" />
                    {errors.model && <p className="mt-1 text-xs text-red-600">{errors.model.message}</p>}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="year">Ano</Label>
                    <Input id="year" type="number" {...register('year')} className="mt-1.5" />
                  </div>
                  <div>
                    <Label htmlFor="color">Cor</Label>
                    <Input id="color" {...register('color')} className="mt-1.5" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="placa">Placa</Label>
                    <Input id="placa" {...register('placa')} className="mt-1.5 uppercase" />
                  </div>
                  <div>
                    <Label htmlFor="proprietario">Proprietário</Label>
                    <Input id="proprietario" {...register('proprietario')} className="mt-1.5" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="engine_number">N° do Motor</Label>
                    <Input id="engine_number" {...register('engine_number')} className="mt-1.5" />
                  </div>
                  <div>
                    <Label htmlFor="chassis_number">N° do Chassi</Label>
                    <Input id="chassis_number" {...register('chassis_number')} className="mt-1.5 uppercase" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="horsepower">Potência (CV)</Label>
                    <Input id="horsepower" {...register('horsepower')} className="mt-1.5" />
                  </div>
                </div>

                <div>
                  <Label htmlFor="notes">Observações</Label>
                  <textarea
                    id="notes"
                    rows={3}
                    {...register('notes')}
                    className="mt-1.5 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500 resize-none"
                  />
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <Button type="button" variant="outline" onClick={() => setEditing(false)}>
                    Cancelar
                  </Button>
                  <Button type="submit" disabled={updateMutation.isPending}>
                    {updateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                    {updateMutation.isPending ? 'Salvando...' : 'Salvar Alterações'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </form>
        )}

        {/* Service Orders */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <ClipboardList className="w-4 h-4" />
                Ordens de Serviço
                {ordersData && ordersData.total > 0 && (
                  <span className="ml-1 text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">
                    {ordersData.total}
                  </span>
                )}
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {osLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            ) : relatedOrders.length === 0 ? (
              <p className="text-sm text-gray-400 py-4 text-center">
                Nenhuma ordem de serviço vinculada a esta máquina
              </p>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>OS</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Abertura</TableHead>
                      <TableHead>Encerramento</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {relatedOrders.map((so) => {
                      const status = STATUS_LABELS[so.status] ?? { label: so.status, cls: '' };
                      return (
                        <TableRow key={so.id}>
                          <TableCell>
                            <Link
                              href={`/service-orders/${so.id}`}
                              className="font-mono text-sm text-green-700 hover:underline font-semibold"
                            >
                              #{so.number}
                            </Link>
                          </TableCell>
                          <TableCell>
                            <Badge className={status.cls}>{status.label}</Badge>
                          </TableCell>
                          <TableCell className="text-sm text-gray-500">
                            {formatDate(so.opened_at)}
                          </TableCell>
                          <TableCell className="text-sm text-gray-500">
                            {so.finished_at ? formatDate(so.finished_at) : '—'}
                          </TableCell>
                          <TableCell className="text-sm font-medium text-gray-900 text-right">
                            {new Intl.NumberFormat('pt-BR', {
                              style: 'currency',
                              currency: 'BRL',
                            }).format(so.total_amount)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>

                {/* Paginação das OS */}
                {ordersData && ordersData.total > OS_PAGE_SIZE && (
                  <div className="flex items-center justify-between pt-4 text-sm text-gray-500 border-t border-gray-100 mt-2">
                    <span>{ordersData.total} ordem{ordersData.total !== 1 ? 's' : ''} no total</span>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setOsPage((p) => Math.max(1, p - 1))}
                        disabled={osPage === 1}
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </Button>
                      <span className="px-1">{osPage}</span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setOsPage((p) => p + 1)}
                        disabled={relatedOrders.length < OS_PAGE_SIZE}
                      >
                        <ChevronRight className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Confirm deactivate */}
      {confirmDelete && (
        <Dialog open onClose={() => setConfirmDelete(false)} className="max-w-md">
          <DialogHeader title="Desativar Máquina" onClose={() => setConfirmDelete(false)} />
          <DialogBody>
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-gray-700">
                  Deseja desativar <strong>{machine.brand} {machine.model}</strong>?
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  A máquina não poderá ser desativada se houver ordens de serviço em aberto.
                </p>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => deactivateMutation.mutate()}
              disabled={deactivateMutation.isPending}
            >
              {deactivateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              Desativar
            </Button>
          </DialogFooter>
        </Dialog>
      )}
    </div>
  );
}
