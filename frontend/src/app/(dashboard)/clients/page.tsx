'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Plus,
  Search,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  UserX,
  UserCheck,
  Eye,
  EyeOff,
  Pencil,
} from 'lucide-react';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
import { clientsApi } from '@/lib/api';
import { formatDocument } from '@/lib/utils';
import type { Client, PaginatedResponse } from '@/types';
import type { AxiosError } from 'axios';

// ── Schemas ───────────────────────────────────────────────────────────────────

const baseClientFields = {
  name: z.string().min(2, 'Nome deve ter ao menos 2 caracteres'),
  email: z.string().email('E-mail inválido').optional().or(z.literal('')),
  phone: z.string().optional().or(z.literal('')),
  phone_secondary: z.string().optional().or(z.literal('')),
  fazenda: z.string().optional().or(z.literal('')),
  logradouro: z.string().optional().or(z.literal('')),
  numero: z.string().optional().or(z.literal('')),
  complemento: z.string().optional().or(z.literal('')),
  bairro: z.string().optional().or(z.literal('')),
  municipio: z.string().optional().or(z.literal('')),
  uf: z.string().max(2).optional().or(z.literal('')),
  cep: z.string().optional().or(z.literal('')),
  inscricao_estadual: z.string().optional().or(z.literal('')),
};

const createClientSchema = z.object({
  ...baseClientFields,
  document_type: z.enum(['CPF', 'CNPJ']),
  document: z.string().min(11, 'Documento inválido').max(18, 'Documento inválido'),
});

const editClientSchema = z.object(baseClientFields);

type CreateClientForm = z.infer<typeof createClientSchema>;
type EditClientForm = z.infer<typeof editClientSchema>;

// ── Component ─────────────────────────────────────────────────────────────────

export default function ClientsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [showInactive, setShowInactive] = useState(false);

  // Debounce: dispara busca 350ms após parar de digitar
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => { setPage(1); }, [debouncedSearch]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<Client | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState<Client | null>(null);
  const pageSize = 10;

  // ── List query ───────────────────────────────────────────────────────────
  const { data, isLoading } = useQuery<PaginatedResponse<Client>>({
    queryKey: ['clients', debouncedSearch, page, showInactive],
    queryFn: async () => {
      const res = await clientsApi.list({
        name: debouncedSearch || undefined,
        page,
        page_size: pageSize,
        active_only: !showInactive,
      });
      return res.data;
    },
  });

  // ── Create form ───────────────────────────────────────────────────────────
  const {
    register: registerCreate,
    handleSubmit: handleCreate,
    reset: resetCreate,
    formState: { errors: createErrors },
  } = useForm<CreateClientForm>({
    resolver: zodResolver(createClientSchema),
    defaultValues: { document_type: 'CPF' },
  });

  const createMutation = useMutation({
    mutationFn: async (data: CreateClientForm) => {
      const res = await clientsApi.create({
        ...data,
        email: data.email || undefined,
        phone: data.phone || undefined,
        phone_secondary: data.phone_secondary || undefined,
        fazenda: data.fazenda || undefined,
        logradouro: data.logradouro || undefined,
        numero: data.numero || undefined,
        complemento: data.complemento || undefined,
        bairro: data.bairro || undefined,
        municipio: data.municipio || undefined,
        uf: data.uf || undefined,
        cep: data.cep || undefined,
        inscricao_estadual: data.inscricao_estadual || undefined,
      });
      return res.data;
    },
    onSuccess: () => {
      toast.success('Cliente criado com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      resetCreate();
      setCreateOpen(false);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao criar cliente');
    },
  });

  // ── Edit form ─────────────────────────────────────────────────────────────
  const {
    register: registerEdit,
    handleSubmit: handleEdit,
    reset: resetEdit,
    formState: { errors: editErrors },
  } = useForm<EditClientForm>({
    resolver: zodResolver(editClientSchema),
  });

  const openEdit = (client: Client) => {
    resetEdit({
      name: client.name,
      email: client.email ?? '',
      phone: client.phone ?? '',
      phone_secondary: client.phone_secondary ?? '',
      fazenda: client.fazenda ?? '',
      logradouro: client.logradouro ?? '',
      numero: client.numero ?? '',
      complemento: client.complemento ?? '',
      bairro: client.bairro ?? '',
      municipio: client.municipio ?? '',
      uf: client.uf ?? '',
      cep: client.cep ?? '',
      inscricao_estadual: client.inscricao_estadual ?? '',
    });
    setEditingClient(client);
  };

  const editMutation = useMutation({
    mutationFn: async (data: EditClientForm) => {
      const payload: Record<string, string | undefined> = {};
      Object.entries(data).forEach(([k, v]) => {
        payload[k] = (v as string) || undefined;
      });
      const res = await clientsApi.update(editingClient!.id, payload);
      return res.data;
    },
    onSuccess: () => {
      toast.success('Cliente atualizado!');
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      setEditingClient(null);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar cliente');
    },
  });

  // ── Deactivate ────────────────────────────────────────────────────────────
  const deactivateMutation = useMutation({
    mutationFn: (id: string) => clientsApi.deactivate(id),
    onSuccess: () => {
      toast.success('Cliente desativado.');
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      setConfirmDeactivate(null);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao desativar cliente');
      setConfirmDeactivate(null);
    },
  });

  // ── Reactivate ────────────────────────────────────────────────────────────
  const reactivateMutation = useMutation({
    mutationFn: (id: string) => clientsApi.update(id, { active: true }),
    onSuccess: () => {
      toast.success('Cliente reativado!');
      queryClient.invalidateQueries({ queryKey: ['clients'] });
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao reativar cliente');
    },
  });

  return (
    <div>
      <Header title="Clientes" />
      <div className="p-6 space-y-4">
        {/* ── Toolbar ─────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1">
            <div className="relative max-w-xs flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                placeholder="Buscar por nome ou CPF/CNPJ..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            {/* Toggle inativos */}
            <Button
              variant={showInactive ? 'default' : 'outline'}
              size="sm"
              onClick={() => { setShowInactive((v) => !v); setPage(1); }}
              className={showInactive ? 'bg-gray-700 hover:bg-gray-800' : ''}
            >
              {showInactive ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              {showInactive ? 'Mostrando inativos' : 'Ocultar inativos'}
            </Button>
          </div>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4" />
            Novo Cliente
          </Button>
        </div>

        {/* ── Table ───────────────────────────────────────────────────── */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : data?.items?.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <AlertCircle className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhum cliente encontrado</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Documento</TableHead>
                  <TableHead>E-mail</TableHead>
                  <TableHead>Telefone</TableHead>
                  <TableHead>Cidade/UF</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-32">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items?.map((client) => (
                  <TableRow
                    key={client.id}
                    className={!client.active ? 'opacity-60 bg-gray-50' : undefined}
                  >
                    <TableCell className="font-medium text-gray-900">
                      {client.name}
                      {client.fazenda && (
                        <p className="text-xs text-gray-400 font-normal">{client.fazenda}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <div>
                        <span className="text-xs text-gray-500 mr-1">{client.document_type}</span>
                        <span className="font-mono text-sm">{formatDocument(client.document)}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">{client.email || '—'}</TableCell>
                    <TableCell className="text-sm text-gray-500">{client.phone || '—'}</TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {client.municipio
                        ? `${client.municipio}${client.uf ? `/${client.uf}` : ''}`
                        : '—'}
                    </TableCell>
                    <TableCell>
                      {client.active ? (
                        <Badge variant="default">Ativo</Badge>
                      ) : (
                        <Badge variant="secondary">Inativo</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {/* Ver máquinas */}
                        <Link href={`/machines?client_id=${client.id}`}>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Ver máquinas">
                            <span className="text-xs">🔧</span>
                          </Button>
                        </Link>

                        {/* Editar */}
                        {client.active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title="Editar cliente"
                            onClick={() => openEdit(client)}
                          >
                            <Pencil className="w-4 h-4 text-gray-500" />
                          </Button>
                        )}

                        {client.active ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title="Desativar cliente"
                            onClick={() => setConfirmDeactivate(client)}
                          >
                            <UserX className="w-4 h-4 text-red-400" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title="Reativar cliente"
                            onClick={() => reactivateMutation.mutate(client.id)}
                            disabled={reactivateMutation.isPending}
                          >
                            {reactivateMutation.isPending ? (
                              <Loader2 className="w-4 h-4 animate-spin text-green-500" />
                            ) : (
                              <UserCheck className="w-4 h-4 text-green-500" />
                            )}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* ── Pagination ──────────────────────────────────────────────── */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              {data.total} cliente{data.total !== 1 ? 's' : ''}
              {showInactive && <span className="ml-1 text-gray-400">(incl. inativos)</span>}
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
              <span className="px-2">{page} / {data.total_pages}</span>
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

      {/* ── Create Dialog ─────────────────────────────────────────────── */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} className="max-w-2xl">
        <DialogHeader title="Novo Cliente" onClose={() => setCreateOpen(false)} />
        <form onSubmit={handleCreate((data) => createMutation.mutate(data))}>
          <DialogBody className="space-y-5">
            {/* Dados básicos */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Dados Básicos</p>
              <div className="space-y-4">
                <div>
                  <Label htmlFor="c-name">Nome *</Label>
                  <Input
                    id="c-name"
                    placeholder="Nome completo ou razão social"
                    {...registerCreate('name')}
                    className="mt-1.5"
                  />
                  {createErrors.name && (
                    <p className="mt-1 text-xs text-red-600">{createErrors.name.message}</p>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <Label htmlFor="c-document_type">Tipo Doc. *</Label>
                    <Select id="c-document_type" {...registerCreate('document_type')} className="mt-1.5">
                      <option value="CPF">CPF</option>
                      <option value="CNPJ">CNPJ</option>
                    </Select>
                  </div>
                  <div className="col-span-2">
                    <Label htmlFor="c-document">Documento *</Label>
                    <Input
                      id="c-document"
                      placeholder="000.000.000-00"
                      {...registerCreate('document')}
                      className="mt-1.5"
                    />
                    {createErrors.document && (
                      <p className="mt-1 text-xs text-red-600">{createErrors.document.message}</p>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="c-email">E-mail</Label>
                    <Input
                      id="c-email"
                      type="email"
                      placeholder="email@exemplo.com"
                      {...registerCreate('email')}
                      className="mt-1.5"
                    />
                    {createErrors.email && (
                      <p className="mt-1 text-xs text-red-600">{createErrors.email.message}</p>
                    )}
                  </div>
                  <div>
                    <Label htmlFor="c-phone">Telefone</Label>
                    <Input
                      id="c-phone"
                      placeholder="(00) 00000-0000"
                      {...registerCreate('phone')}
                      className="mt-1.5"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="c-phone_secondary">Telefone Secundário</Label>
                    <Input
                      id="c-phone_secondary"
                      placeholder="(00) 00000-0000"
                      {...registerCreate('phone_secondary')}
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <Label htmlFor="c-fazenda">Fazenda / Propriedade</Label>
                    <Input
                      id="c-fazenda"
                      placeholder="Nome da fazenda"
                      {...registerCreate('fazenda')}
                      className="mt-1.5"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Endereço */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Endereço</p>
              <div className="space-y-4">
                <div className="grid grid-cols-4 gap-3">
                  <div className="col-span-3">
                    <Label htmlFor="c-logradouro">Logradouro</Label>
                    <Input
                      id="c-logradouro"
                      placeholder="Rua, Av., Estrada..."
                      {...registerCreate('logradouro')}
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <Label htmlFor="c-numero">Número</Label>
                    <Input
                      id="c-numero"
                      placeholder="S/N"
                      {...registerCreate('numero')}
                      className="mt-1.5"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="c-complemento">Complemento</Label>
                    <Input
                      id="c-complemento"
                      placeholder="Apto, Sala, Bloco..."
                      {...registerCreate('complemento')}
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <Label htmlFor="c-bairro">Bairro</Label>
                    <Input
                      id="c-bairro"
                      placeholder="Bairro"
                      {...registerCreate('bairro')}
                      className="mt-1.5"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-5 gap-3">
                  <div className="col-span-2">
                    <Label htmlFor="c-municipio">Município</Label>
                    <Input
                      id="c-municipio"
                      placeholder="Cidade"
                      {...registerCreate('municipio')}
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <Label htmlFor="c-uf">UF</Label>
                    <Input
                      id="c-uf"
                      placeholder="SP"
                      maxLength={2}
                      {...registerCreate('uf')}
                      className="mt-1.5 uppercase"
                    />
                  </div>
                  <div className="col-span-2">
                    <Label htmlFor="c-cep">CEP</Label>
                    <Input
                      id="c-cep"
                      placeholder="00000-000"
                      {...registerCreate('cep')}
                      className="mt-1.5"
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="c-inscricao_estadual">Inscrição Estadual</Label>
                  <Input
                    id="c-inscricao_estadual"
                    placeholder="Inscrição estadual (opcional)"
                    {...registerCreate('inscricao_estadual')}
                    className="mt-1.5"
                  />
                </div>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {createMutation.isPending ? 'Salvando...' : 'Salvar Cliente'}
            </Button>
          </DialogFooter>
        </form>
      </Dialog>

      {/* ── Edit Dialog ───────────────────────────────────────────────── */}
      {editingClient && (
        <Dialog open onClose={() => setEditingClient(null)} className="max-w-2xl">
          <DialogHeader title={`Editar: ${editingClient.name}`} onClose={() => setEditingClient(null)} />
          <form onSubmit={handleEdit((data) => editMutation.mutate(data))}>
            <DialogBody className="space-y-5">
              {/* Dados básicos */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Dados Básicos</p>
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="e-name">Nome *</Label>
                    <Input
                      id="e-name"
                      {...registerEdit('name')}
                      className="mt-1.5"
                    />
                    {editErrors.name && (
                      <p className="mt-1 text-xs text-red-600">{editErrors.name.message}</p>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="e-email">E-mail</Label>
                      <Input
                        id="e-email"
                        type="email"
                        {...registerEdit('email')}
                        className="mt-1.5"
                      />
                      {editErrors.email && (
                        <p className="mt-1 text-xs text-red-600">{editErrors.email.message}</p>
                      )}
                    </div>
                    <div>
                      <Label htmlFor="e-phone">Telefone</Label>
                      <Input
                        id="e-phone"
                        {...registerEdit('phone')}
                        className="mt-1.5"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="e-phone_secondary">Telefone Secundário</Label>
                      <Input
                        id="e-phone_secondary"
                        {...registerEdit('phone_secondary')}
                        className="mt-1.5"
                      />
                    </div>
                    <div>
                      <Label htmlFor="e-fazenda">Fazenda / Propriedade</Label>
                      <Input
                        id="e-fazenda"
                        {...registerEdit('fazenda')}
                        className="mt-1.5"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Endereço */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Endereço</p>
                <div className="space-y-4">
                  <div className="grid grid-cols-4 gap-3">
                    <div className="col-span-3">
                      <Label htmlFor="e-logradouro">Logradouro</Label>
                      <Input
                        id="e-logradouro"
                        {...registerEdit('logradouro')}
                        className="mt-1.5"
                      />
                    </div>
                    <div>
                      <Label htmlFor="e-numero">Número</Label>
                      <Input
                        id="e-numero"
                        {...registerEdit('numero')}
                        className="mt-1.5"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="e-complemento">Complemento</Label>
                      <Input
                        id="e-complemento"
                        {...registerEdit('complemento')}
                        className="mt-1.5"
                      />
                    </div>
                    <div>
                      <Label htmlFor="e-bairro">Bairro</Label>
                      <Input
                        id="e-bairro"
                        {...registerEdit('bairro')}
                        className="mt-1.5"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-5 gap-3">
                    <div className="col-span-2">
                      <Label htmlFor="e-municipio">Município</Label>
                      <Input
                        id="e-municipio"
                        {...registerEdit('municipio')}
                        className="mt-1.5"
                      />
                    </div>
                    <div>
                      <Label htmlFor="e-uf">UF</Label>
                      <Input
                        id="e-uf"
                        maxLength={2}
                        {...registerEdit('uf')}
                        className="mt-1.5 uppercase"
                      />
                    </div>
                    <div className="col-span-2">
                      <Label htmlFor="e-cep">CEP</Label>
                      <Input
                        id="e-cep"
                        {...registerEdit('cep')}
                        className="mt-1.5"
                      />
                    </div>
                  </div>

                  <div>
                    <Label htmlFor="e-inscricao_estadual">Inscrição Estadual</Label>
                    <Input
                      id="e-inscricao_estadual"
                      {...registerEdit('inscricao_estadual')}
                      className="mt-1.5"
                    />
                  </div>
                </div>
              </div>
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditingClient(null)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={editMutation.isPending}>
                {editMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                {editMutation.isPending ? 'Salvando...' : 'Salvar Alterações'}
              </Button>
            </DialogFooter>
          </form>
        </Dialog>
      )}

      {/* ── Confirm Deactivate Dialog ─────────────────────────────────── */}
      {confirmDeactivate && (
        <Dialog open onClose={() => setConfirmDeactivate(null)} className="max-w-md">
          <DialogHeader title="Desativar Cliente" onClose={() => setConfirmDeactivate(null)} />
          <DialogBody>
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-gray-700">
                  Deseja desativar <strong>{confirmDeactivate.name}</strong>?
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Clientes inativos não podem abrir novas ordens de serviço.
                  Você pode reativá-lo a qualquer momento.
                </p>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDeactivate(null)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => deactivateMutation.mutate(confirmDeactivate.id)}
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
