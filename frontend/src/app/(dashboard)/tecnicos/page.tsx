'use client';

import { useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Plus,
  AlertCircle,
  Loader2,
  Pencil,
  UserX,
  UserCheck,
  Upload,
  Trash2,
  CheckCircle,
  ImageOff,
  Copy,
  Link2,
  KeyRound,
} from 'lucide-react';
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
import { usersApi } from '@/lib/api';
import { getAccessToken } from '@/lib/auth';
import type { User, UserRole } from '@/types';
import type { AxiosError } from 'axios';

/** Decodifica o tenant_id do JWT sem biblioteca externa */
function getTenantIdFromToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const token = getAccessToken();
    if (!token) return null;
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.tenant_id ?? null;
  } catch {
    return null;
  }
}

// ── Schemas ───────────────────────────────────────────────────────────────────

const EDITABLE_ROLES = ['ADMIN', 'TECNICO', 'VIEWER'] as const;
type EditableRole = typeof EDITABLE_ROLES[number];

const createSchema = z.object({
  full_name: z.string().min(2, 'Nome deve ter ao menos 2 caracteres'),
  email: z.string().email('E-mail inválido'),
  password: z.string().min(8, 'Senha deve ter ao menos 8 caracteres'),
  role: z.enum(EDITABLE_ROLES),
});

const editSchema = z.object({
  full_name: z.string().min(2, 'Nome deve ter ao menos 2 caracteres'),
  email: z.string().email('E-mail inválido'),
  role: z.enum(EDITABLE_ROLES),
});

type CreateForm = z.infer<typeof createSchema>;
type EditForm = z.infer<typeof editSchema>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<UserRole, { label: string; cls: string }> = {
  SUPER_ADMIN: { label: 'Super Admin', cls: 'bg-red-100 text-red-800 border-red-200' },
  ADMIN: { label: 'Administrador', cls: 'bg-purple-100 text-purple-800 border-purple-200' },
  TECNICO: { label: 'Técnico', cls: 'bg-blue-100 text-blue-800 border-blue-200' },
  VIEWER: { label: 'Visualizador', cls: 'bg-gray-100 text-gray-700 border-gray-200' },
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function TecnicosPage() {
  const queryClient = useQueryClient();
  const [showInactive, setShowInactive] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [sigUser, setSigUser] = useState<User | null>(null);
  const [sigPreview, setSigPreview] = useState<string | null>(null);
  const [sigFile, setSigFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── List ─────────────────────────────────────────────────────────────────
  const { data, isLoading } = useQuery<{ items: User[]; total: number }>({
    queryKey: ['users', showInactive],
    queryFn: async () => {
      const res = await usersApi.list({ active_only: !showInactive });
      return res.data;
    },
  });

  const users = data?.items ?? [];

  // ── Create ────────────────────────────────────────────────────────────────
  const {
    register: regCreate,
    handleSubmit: handleCreate,
    reset: resetCreate,
    formState: { errors: errCreate },
  } = useForm<CreateForm>({
    resolver: zodResolver(createSchema),
    defaultValues: { role: 'TECNICO' },
  });

  const createMutation = useMutation({
    mutationFn: (data: CreateForm) => usersApi.create(data),
    onSuccess: () => {
      toast.success('Técnico cadastrado com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      resetCreate();
      setCreateOpen(false);
    },
    onError: (e: AxiosError<{ detail: string }>) => {
      toast.error(e.response?.data?.detail || 'Erro ao cadastrar');
    },
  });

  // ── Edit ──────────────────────────────────────────────────────────────────
  const {
    register: regEdit,
    handleSubmit: handleEdit,
    reset: resetEdit,
    formState: { errors: errEdit },
  } = useForm<EditForm>({ resolver: zodResolver(editSchema) });

  const openEdit = (u: User) => {
    // SUPER_ADMIN não é editável nesta tela — trata como ADMIN para o formulário
    const editableRole: EditableRole = EDITABLE_ROLES.includes(u.role as EditableRole)
      ? (u.role as EditableRole)
      : 'ADMIN';
    resetEdit({ full_name: u.full_name, email: u.email, role: editableRole });
    setEditingUser(u);
  };

  const editMutation = useMutation({
    mutationFn: (data: EditForm) => usersApi.update(editingUser!.id, data),
    onSuccess: () => {
      toast.success('Dados atualizados!');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setEditingUser(null);
    },
    onError: (e: AxiosError<{ detail: string }>) => {
      toast.error(e.response?.data?.detail || 'Erro ao atualizar');
    },
  });

  // ── Toggle active ─────────────────────────────────────────────────────────
  const toggleActiveMutation = useMutation({
    mutationFn: (u: User) => usersApi.update(u.id, { active: !u.active }),
    onSuccess: (_, u) => {
      toast.success(u.active ? 'Usuário desativado.' : 'Usuário reativado!');
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e: AxiosError<{ detail: string }>) => {
      toast.error(e.response?.data?.detail || 'Erro ao alterar status');
    },
  });

  // ── Signature upload ───────────────────────────────────────────────────────
  const openSigDialog = (u: User) => {
    setSigUser(u);
    setSigPreview(null);
    setSigFile(null);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Arquivo muito grande (máx 2 MB)');
      return;
    }
    setSigFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setSigPreview(ev.target?.result as string);
    reader.readAsDataURL(file);
  };

  const uploadSigMutation = useMutation({
    mutationFn: () => usersApi.uploadSignature(sigUser!.id, sigFile!),
    onSuccess: () => {
      toast.success('Assinatura salva!');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setSigUser(null);
    },
    onError: (e: AxiosError<{ detail: string }>) => {
      toast.error(e.response?.data?.detail || 'Erro ao salvar assinatura');
    },
  });

  const removeSigMutation = useMutation({
    mutationFn: (id: string) => usersApi.removeSignature(id),
    onSuccess: () => {
      toast.success('Assinatura removida.');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setSigUser(null);
    },
    onError: (e: AxiosError<{ detail: string }>) => {
      toast.error(e.response?.data?.detail || 'Erro ao remover assinatura');
    },
  });

  // ── Acesso da oficina ─────────────────────────────────────────────────────
  const tenantId = getTenantIdFromToken();
  const appUrl = typeof window !== 'undefined' ? window.location.origin : '';
  const loginLink = tenantId ? `${appUrl}/login?tenant=${tenantId}` : null;

  const copyText = (text: string, label: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => toast.success(`${label} copiado!`)).catch(() => fallbackCopy(text, label));
    } else {
      fallbackCopy(text, label);
    }
  };

  const fallbackCopy = (text: string, label: string) => {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.focus();
    el.select();
    try {
      document.execCommand('copy');
      toast.success(`${label} copiado!`);
    } catch {
      toast.error('Não foi possível copiar. Selecione e copie manualmente.');
    }
    document.body.removeChild(el);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div>
      <Header title="Técnicos e Usuários" />
      <div className="p-6 space-y-4">

        {/* Card de acesso da oficina */}
        {tenantId && (
          <div className="bg-green-50 border border-green-200 rounded-xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-green-800 font-semibold text-sm">
              <KeyRound className="w-4 h-4" />
              Como os técnicos fazem login
            </div>
            <p className="text-xs text-green-700 leading-relaxed">
              Compartilhe o <strong>link de acesso</strong> abaixo com o técnico. Ele abrirá
              a tela de login já com o código da oficina preenchido — basta digitar
              o e-mail e a senha cadastrados aqui.
            </p>

            {/* Link de acesso */}
            <div>
              <p className="text-xs font-semibold text-green-800 mb-1 flex items-center gap-1">
                <Link2 className="w-3.5 h-3.5" />
                Link de acesso (envie para o técnico)
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-white border border-green-200 rounded-lg px-3 py-2 text-xs text-gray-700 truncate select-all">
                  {loginLink}
                </code>
                <button
                  onClick={() => copyText(loginLink!, 'Link')}
                  className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 bg-green-600 hover:bg-green-700 text-white text-xs font-medium rounded-lg transition"
                >
                  <Copy className="w-3.5 h-3.5" />
                  Copiar
                </button>
              </div>
            </div>

            {/* Código bruto */}
            <details className="text-xs">
              <summary className="cursor-pointer text-green-700 hover:text-green-800 font-medium select-none">
                Ver código da oficina (para login manual)
              </summary>
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 bg-white border border-green-200 rounded-lg px-3 py-2 font-mono text-gray-700 text-xs select-all">
                  {tenantId}
                </code>
                <button
                  onClick={() => copyText(tenantId, 'Código')}
                  className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 bg-white hover:bg-green-50 border border-green-300 text-green-700 text-xs font-medium rounded-lg transition"
                >
                  <Copy className="w-3.5 h-3.5" />
                  Copiar
                </button>
              </div>
            </details>
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {/* Toggle inativos */}
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <div
                onClick={() => setShowInactive((v) => !v)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  showInactive ? 'bg-gray-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    showInactive ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </div>
              <span className="text-sm text-gray-600">Mostrar inativos</span>
            </label>
          </div>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4" />
            Novo Usuário
          </Button>
        </div>

        {/* Table */}
        <Card>
          {isLoading ? (
            <PageSpinner />
          ) : users.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <AlertCircle className="w-12 h-12 mb-3" />
              <p className="text-sm">Nenhum usuário encontrado</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>E-mail</TableHead>
                  <TableHead>Perfil</TableHead>
                  <TableHead>Assinatura</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-36">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => {
                  const roleInfo = ROLE_LABELS[u.role] ?? { label: u.role, cls: '' };
                  return (
                    <TableRow
                      key={u.id}
                      className={!u.active ? 'opacity-60 bg-gray-50' : undefined}
                    >
                      <TableCell className="font-medium text-gray-900">{u.full_name}</TableCell>
                      <TableCell className="text-sm text-gray-500">{u.email}</TableCell>
                      <TableCell>
                        <Badge className={roleInfo.cls}>{roleInfo.label}</Badge>
                      </TableCell>
                      <TableCell>
                        {u.assinatura_url ? (
                          <span className="inline-flex items-center gap-1 text-xs text-green-700 font-medium">
                            <CheckCircle className="w-3.5 h-3.5" />
                            Cadastrada
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-gray-400">
                            <ImageOff className="w-3.5 h-3.5" />
                            Sem assinatura
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {u.active ? (
                          <Badge variant="default">Ativo</Badge>
                        ) : (
                          <Badge variant="secondary">Inativo</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          {/* Editar */}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title="Editar"
                            onClick={() => openEdit(u)}
                          >
                            <Pencil className="w-4 h-4 text-gray-500" />
                          </Button>

                          {/* Assinatura */}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title="Gerenciar assinatura"
                            onClick={() => openSigDialog(u)}
                          >
                            <Upload className="w-4 h-4 text-blue-500" />
                          </Button>

                          {/* Ativar / Desativar */}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title={u.active ? 'Desativar' : 'Reativar'}
                            onClick={() => toggleActiveMutation.mutate(u)}
                            disabled={toggleActiveMutation.isPending}
                          >
                            {u.active ? (
                              <UserX className="w-4 h-4 text-red-400" />
                            ) : (
                              <UserCheck className="w-4 h-4 text-green-500" />
                            )}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </Card>
      </div>

      {/* ── Create Dialog ─────────────────────────────────────────────────── */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} className="max-w-md">
        <DialogHeader title="Novo Usuário" onClose={() => setCreateOpen(false)} />
        <form onSubmit={handleCreate((d) => createMutation.mutate(d))}>
          <DialogBody className="space-y-4">
            <div>
              <Label htmlFor="c-full_name">Nome completo *</Label>
              <Input id="c-full_name" {...regCreate('full_name')} className="mt-1.5" />
              {errCreate.full_name && (
                <p className="mt-1 text-xs text-red-600">{errCreate.full_name.message}</p>
              )}
            </div>
            <div>
              <Label htmlFor="c-email">E-mail *</Label>
              <Input id="c-email" type="email" {...regCreate('email')} className="mt-1.5" />
              {errCreate.email && (
                <p className="mt-1 text-xs text-red-600">{errCreate.email.message}</p>
              )}
            </div>
            <div>
              <Label htmlFor="c-password">Senha *</Label>
              <Input id="c-password" type="password" placeholder="Mínimo 8 caracteres" {...regCreate('password')} className="mt-1.5" />
              {errCreate.password && (
                <p className="mt-1 text-xs text-red-600">{errCreate.password.message}</p>
              )}
            </div>
            <div>
              <Label htmlFor="c-role">Perfil *</Label>
              <Select id="c-role" {...regCreate('role')} className="mt-1.5">
                <option value="TECNICO">Técnico</option>
                <option value="ADMIN">Administrador</option>
                <option value="VIEWER">Visualizador</option>
              </Select>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {createMutation.isPending ? 'Salvando...' : 'Cadastrar'}
            </Button>
          </DialogFooter>
        </form>
      </Dialog>

      {/* ── Edit Dialog ───────────────────────────────────────────────────── */}
      {editingUser && (
        <Dialog open onClose={() => setEditingUser(null)} className="max-w-md">
          <DialogHeader title={`Editar: ${editingUser.full_name}`} onClose={() => setEditingUser(null)} />
          <form onSubmit={handleEdit((d) => editMutation.mutate(d))}>
            <DialogBody className="space-y-4">
              <div>
                <Label htmlFor="e-full_name">Nome completo *</Label>
                <Input id="e-full_name" {...regEdit('full_name')} className="mt-1.5" />
                {errEdit.full_name && (
                  <p className="mt-1 text-xs text-red-600">{errEdit.full_name.message}</p>
                )}
              </div>
              <div>
                <Label htmlFor="e-email">E-mail *</Label>
                <Input id="e-email" type="email" {...regEdit('email')} className="mt-1.5" />
                {errEdit.email && (
                  <p className="mt-1 text-xs text-red-600">{errEdit.email.message}</p>
                )}
              </div>
              <div>
                <Label htmlFor="e-role">Perfil *</Label>
                <Select id="e-role" {...regEdit('role')} className="mt-1.5">
                  <option value="TECNICO">Técnico</option>
                  <option value="ADMIN">Administrador</option>
                  <option value="VIEWER">Visualizador</option>
                </Select>
              </div>
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditingUser(null)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={editMutation.isPending}>
                {editMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                {editMutation.isPending ? 'Salvando...' : 'Salvar'}
              </Button>
            </DialogFooter>
          </form>
        </Dialog>
      )}

      {/* ── Signature Dialog ──────────────────────────────────────────────── */}
      {sigUser && (
        <Dialog open onClose={() => setSigUser(null)} className="max-w-md">
          <DialogHeader title={`Assinatura — ${sigUser.full_name}`} onClose={() => setSigUser(null)} />
          <DialogBody className="space-y-5">
            {/* Assinatura atual */}
            {sigUser.assinatura_url && !sigPreview && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Assinatura atual
                </p>
                <div className="border border-gray-200 rounded-lg p-4 bg-gray-50 flex items-center justify-center min-h-[80px]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`/api/signatures/${sigUser.id}`}
                    alt="Assinatura atual"
                    className="max-h-20 object-contain"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                  <p className="text-xs text-green-700 font-medium flex items-center gap-1">
                    <CheckCircle className="w-3.5 h-3.5" />
                    Assinatura cadastrada
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2 text-red-500 border-red-200 hover:bg-red-50 w-full"
                  onClick={() => removeSigMutation.mutate(sigUser.id)}
                  disabled={removeSigMutation.isPending}
                >
                  {removeSigMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                  Remover assinatura
                </Button>
              </div>
            )}

            {/* Preview da nova imagem */}
            {sigPreview && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Pré-visualização
                </p>
                <div className="border border-green-200 rounded-lg p-4 bg-green-50 flex items-center justify-center min-h-[80px]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={sigPreview} alt="Preview" className="max-h-24 object-contain" />
                </div>
              </div>
            )}

            {/* Upload */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                {sigUser.assinatura_url ? 'Substituir assinatura' : 'Adicionar assinatura'}
              </p>
              <p className="text-xs text-gray-500 mb-3">
                Envie uma imagem PNG ou JPEG com fundo branco ou transparente. Tamanho máximo: 2 MB.
                A assinatura será impressa automaticamente nos PDFs das OS deste técnico.
              </p>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg"
                className="hidden"
                onChange={onFileChange}
              />

              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="w-4 h-4" />
                {sigFile ? sigFile.name : 'Selecionar imagem…'}
              </Button>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSigUser(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={!sigFile || uploadSigMutation.isPending}
              onClick={() => uploadSigMutation.mutate()}
            >
              {uploadSigMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {uploadSigMutation.isPending ? 'Salvando...' : 'Salvar Assinatura'}
            </Button>
          </DialogFooter>
        </Dialog>
      )}
    </div>
  );
}
