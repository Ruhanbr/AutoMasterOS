'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Building2,
  Plus,
  Pencil,
  LogOut,
  Users,
  ShieldCheck,
  Loader2,
  X,
  Check,
  Copy,
  Mail,
  Trash2,
  AlertTriangle,
  MapPin,
  ImagePlus,
  Trash,
} from 'lucide-react';
import { tenantsApi } from '@/lib/api';
import { clearTokens, getAccessToken } from '@/lib/auth';
import { copyToClipboard } from '@/lib/utils';
import type { Tenant, UpdateTenantPayload } from '@/types';
import type { AxiosError } from 'axios'; // usado no extractError helper

// ── Error helper ──────────────────────────────────────────────────────────────

function extractError(err: unknown, fallback: string): string {
  const e = err as AxiosError<{ detail: unknown }>;
  const detail = e?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string; loc?: string[] }) => {
        const field = d.loc ? d.loc.filter((l) => l !== 'body').join(' → ') : '';
        const msg = (d.msg ?? '').replace(/^Value error,\s*/i, '');
        return field ? `${field}: ${msg}` : msg;
      })
      .join('\n');
  }
  // objeto com { code, message } — padrão AutoMaster
  if (typeof detail === 'object' && detail !== null) {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === 'string') return obj.message;
  }
  return fallback;
}

// ── CEP lookup ────────────────────────────────────────────────────────────────

interface ViaCepResult {
  logradouro: string;
  bairro: string;
  localidade: string;
  uf: string;
  erro?: boolean;
}

async function lookupCep(raw: string): Promise<ViaCepResult | null> {
  const digits = raw.replace(/\D/g, '');
  if (digits.length !== 8) return null;
  try {
    const res = await fetch(`https://viacep.com.br/ws/${digits}/json/`);
    if (!res.ok) return null;
    const data: ViaCepResult = await res.json();
    return data.erro ? null : data;
  } catch {
    return null;
  }
}

// ── Document validation (CPF ou CNPJ) ────────────────────────────────────────

const documentSchema = z
  .string()
  .min(1, 'Documento obrigatório')
  .refine(
    (v) => {
      const d = v.replace(/\D/g, '');
      return d.length === 11 || d.length === 14;
    },
    { message: 'Informe um CPF (11 dígitos) ou CNPJ (14 dígitos)' },
  );

// ── Schemas ───────────────────────────────────────────────────────────────────

const setupSchema = z.object({
  // Oficina
  name: z.string().min(1, 'Nome obrigatório'),
  razao_social: z.string().min(1, 'Razão social obrigatória'),
  document: documentSchema,
  email: z.string().email('E-mail inválido'),
  phone: z.string().optional().or(z.literal('')),
  municipio: z.string().optional().or(z.literal('')),
  uf: z.string().max(2).optional().or(z.literal('')),
  cep: z.string().optional().or(z.literal('')),
  logradouro: z.string().optional().or(z.literal('')),
  numero: z.string().optional().or(z.literal('')),
  bairro: z.string().optional().or(z.literal('')),
  inscricao_estadual: z.string().optional().or(z.literal('')),
  limite_tecnicos: z.coerce.number().int().min(1, 'Mínimo 1 técnico').max(999),
  // Administrador da oficina
  admin_nome: z.string().min(1, 'Nome do responsável obrigatório'),
  admin_email: z.string().email('E-mail do responsável inválido'),
});

const editSchema = z.object({
  name: z.string().min(1, 'Nome obrigatório'),
  razao_social: z.string().min(1, 'Razão social obrigatória'),
  nome_fantasia: z.string().optional().or(z.literal('')),
  document: documentSchema,
  email: z.string().email('E-mail inválido'),
  phone: z.string().optional().or(z.literal('')),
  municipio: z.string().optional().or(z.literal('')),
  uf: z.string().max(2).optional().or(z.literal('')),
  cep: z.string().optional().or(z.literal('')),
  logradouro: z.string().optional().or(z.literal('')),
  numero: z.string().optional().or(z.literal('')),
  complemento: z.string().optional().or(z.literal('')),
  bairro: z.string().optional().or(z.literal('')),
  inscricao_estadual: z.string().optional().or(z.literal('')),
  inscricao_municipal: z.string().optional().or(z.literal('')),
  limite_tecnicos: z.coerce.number().int().min(1, 'Mínimo 1 técnico').max(999),
});

type SetupForm = z.infer<typeof setupSchema>;
type EditForm = z.infer<typeof editSchema>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function isSuperAdmin(): boolean {
  try {
    const token = getAccessToken();
    if (!token) return false;
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.role === 'SUPER_ADMIN';
  } catch {
    return false;
  }
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {children}
    </div>
  );
}

function InputClass(error?: boolean) {
  return `w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
    error ? 'border-red-400' : 'border-gray-300'
  }`;
}

function SectionLabel({ children }: { children: string }) {
  return (
    <div className="pt-1 pb-2 border-b border-gray-100">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{children}</p>
    </div>
  );
}

function LoginLinkButton({ tenantId }: { tenantId: string }) {
  const [copied, setCopied] = useState(false);
  const link =
    typeof window !== 'undefined'
      ? `${window.location.origin}/login?tenant=${tenantId}`
      : `/login?tenant=${tenantId}`;

  const copy = async () => {
    await copyToClipboard(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={copy}
      title="Copiar link de login da oficina"
      className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 transition"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copiado!' : 'Copiar link de acesso'}
    </button>
  );
}

// ── Modal de confirmação de exclusão ──────────────────────────────────────────

function DeleteModal({
  tenant,
  onClose,
  onDeleted,
}: {
  tenant: Tenant;
  onClose: () => void;
  onDeleted: (id: string) => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleDelete = async () => {
    setLoading(true);
    try {
      await tenantsApi.delete(tenant.id);
      toast.success(`Oficina "${tenant.name}" desativada com sucesso.`);
      onDeleted(tenant.id);
    } catch (err) {
      toast.error(extractError(err, 'Erro ao excluir oficina.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex items-center justify-center w-10 h-10 rounded-full bg-red-100 flex-shrink-0">
              <AlertTriangle className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Excluir oficina</h2>
              <p className="text-sm text-gray-500">Esta ação não pode ser desfeita facilmente.</p>
            </div>
          </div>

          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-sm text-red-800">
              Você está prestes a <strong>desativar</strong> a oficina:
            </p>
            <p className="text-base font-bold text-red-900 mt-1">{tenant.name}</p>
            <p className="text-xs text-red-700 mt-0.5">{tenant.razao_social} — {tenant.document}</p>
            <p className="text-xs text-red-600 mt-3">
              Os dados históricos (ordens de serviço, clientes, financeiro) serão preservados,
              mas a oficina e seus usuários não poderão mais acessar o sistema.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="flex-1 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={loading}
              className="flex-1 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Excluindo...
                </>
              ) : (
                <>
                  <Trash2 className="w-4 h-4" />
                  Sim, excluir oficina
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Modal de logo da oficina ──────────────────────────────────────────────────

function LogoModal({
  tenant,
  onClose,
  onUpdated,
}: {
  tenant: Tenant;
  onClose: () => void;
  onUpdated: (t: Tenant) => void;
}) {
  const [preview, setPreview] = useState<string | null>(tenant.logo_url ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [removing, setRemoving] = useState(false);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 3 * 1024 * 1024) {
      toast.error('Arquivo muito grande. Máximo: 3 MB.');
      return;
    }
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const res = await tenantsApi.uploadLogo(tenant.id, file);
      toast.success('Logo enviada com sucesso!');
      onUpdated(res.data as Tenant);
      onClose();
    } catch (err) {
      toast.error(extractError(err, 'Erro ao enviar logo.'));
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async () => {
    setRemoving(true);
    try {
      const res = await tenantsApi.deleteLogo(tenant.id);
      toast.success('Logo removida.');
      onUpdated(res.data as Tenant);
      onClose();
    } catch (err) {
      toast.error(extractError(err, 'Erro ao remover logo.'));
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">Logo da Oficina</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Preview */}
          <div className="flex flex-col items-center gap-3">
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={preview}
                alt="Logo da oficina"
                className="w-32 h-32 object-contain rounded-xl border border-gray-200 bg-gray-50 p-2"
              />
            ) : (
              <div className="w-32 h-32 rounded-xl border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-gray-400 bg-gray-50">
                <ImagePlus className="w-8 h-8 mb-1" />
                <span className="text-xs">Sem logo</span>
              </div>
            )}
            <p className="text-xs text-gray-400 text-center">
              PNG, JPG ou WebP · Máx. 3 MB<br />Recomendado: 200×200 px ou maior
            </p>
          </div>

          {/* Input de arquivo */}
          <label className="flex items-center justify-center gap-2 w-full px-4 py-2.5 border-2 border-dashed border-indigo-300 text-indigo-600 rounded-lg text-sm font-medium cursor-pointer hover:bg-indigo-50 transition">
            <ImagePlus className="w-4 h-4" />
            {file ? file.name : 'Escolher imagem'}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={handleFile}
            />
          </label>

          {/* Botões */}
          <div className="flex gap-3">
            {tenant.logo_url && (
              <button
                type="button"
                onClick={handleRemove}
                disabled={removing || loading}
                className="flex items-center gap-1.5 px-3 py-2 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition disabled:opacity-50"
              >
                {removing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash className="w-4 h-4" />}
                Remover
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={loading || removing}
              className="flex-1 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={!file || loading || removing}
              className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ImagePlus className="w-4 h-4" />}
              Salvar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Modal de criação (Oficina + Admin) ────────────────────────────────────────

interface SetupResponse {
  tenant: Tenant;
  admin_email: string;
  message: string;
}

function CreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (t: Tenant) => void;
}) {
  const [cepLoading, setCepLoading] = useState(false);
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<SetupForm>({
    resolver: zodResolver(setupSchema),
    defaultValues: { limite_tecnicos: 5 },
  });

  const handleCepBlur = useCallback(async (e: React.FocusEvent<HTMLInputElement>) => {
    setCepLoading(true);
    const data = await lookupCep(e.target.value);
    if (data) {
      setValue('logradouro', data.logradouro, { shouldValidate: false });
      setValue('bairro', data.bairro, { shouldValidate: false });
      setValue('municipio', data.localidade, { shouldValidate: false });
      setValue('uf', data.uf, { shouldValidate: false });
    }
    setCepLoading(false);
  }, [setValue]);

  const onSubmit = async (data: SetupForm) => {
    try {
      const res = await tenantsApi.setup({
        ...data,
        crt: '1',
        regime_tributario: 1,
      });
      const result = res.data as SetupResponse;
      toast.success(result.message, { duration: 6000 });
      onCreated(result.tenant);
    } catch (err) {
      toast.error(extractError(err, 'Erro ao criar oficina.'));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">Nova Oficina</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-5">

          <SectionLabel>Dados da Oficina</SectionLabel>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Field label="Nome fantasia *">
                <input {...register('name')} placeholder="Ex: Oficina Silva" className={InputClass(!!errors.name)} />
                {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Razão social *">
                <input {...register('razao_social')} placeholder="Ex: SILVA OFICINAS LTDA" className={InputClass(!!errors.razao_social)} />
                {errors.razao_social && <p className="text-xs text-red-600 mt-1">{errors.razao_social.message}</p>}
              </Field>
            </div>

            <div>
              <Field label="CPF / CNPJ *">
                <input {...register('document')} placeholder="000.000.000-00 ou 00.000.000/0001-00" className={`${InputClass(!!errors.document)} font-mono`} />
                {errors.document && <p className="text-xs text-red-600 mt-1">{errors.document.message}</p>}
              </Field>
            </div>

            <div>
              <Field label="Limite de técnicos *">
                <input type="number" min={1} max={999} {...register('limite_tecnicos')} className={InputClass(!!errors.limite_tecnicos)} />
                {errors.limite_tecnicos && <p className="text-xs text-red-600 mt-1">{errors.limite_tecnicos.message}</p>}
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="E-mail da oficina *">
                <input type="email" {...register('email')} placeholder="contato@oficina.com" className={InputClass(!!errors.email)} />
                {errors.email && <p className="text-xs text-red-600 mt-1">{errors.email.message}</p>}
              </Field>
            </div>

            <div>
              <Field label="Telefone">
                <input {...register('phone')} placeholder="(11) 99999-0000" className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="Inscrição estadual">
                <input {...register('inscricao_estadual')} placeholder="Ex: 123.456.789.000" className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="CEP">
                <div className="relative">
                  <input
                    {...register('cep')}
                    placeholder="00000-000"
                    className={`${InputClass()} font-mono pr-8`}
                    onBlur={handleCepBlur}
                  />
                  {cepLoading && (
                    <MapPin className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-indigo-400 animate-pulse" />
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-0.5">Preenche endereço automaticamente</p>
              </Field>
            </div>

            <div>
              <Field label="UF">
                <input {...register('uf')} placeholder="SP" maxLength={2} className={`${InputClass()} uppercase`} />
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Município">
                <input {...register('municipio')} placeholder="São Paulo" className={InputClass()} />
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Logradouro">
                <input {...register('logradouro')} placeholder="Av. Paulista" className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="Número">
                <input {...register('numero')} placeholder="1000" className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="Bairro">
                <input {...register('bairro')} placeholder="Centro" className={InputClass()} />
              </Field>
            </div>
          </div>

          <SectionLabel>Acesso do Administrador</SectionLabel>

          <p className="text-xs text-gray-500 -mt-2 flex items-center gap-1">
            <Mail className="w-3.5 h-3.5 text-indigo-500" />
            A senha de acesso será enviada automaticamente para o e-mail abaixo
          </p>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Field label="Nome do responsável *">
                <input {...register('admin_nome')} placeholder="Ex: João Silva" className={InputClass(!!errors.admin_nome)} />
                {errors.admin_nome && <p className="text-xs text-red-600 mt-1">{errors.admin_nome.message}</p>}
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="E-mail do responsável *">
                <input type="email" {...register('admin_email')} placeholder="joao@oficina.com" className={InputClass(!!errors.admin_email)} />
                {errors.admin_email && <p className="text-xs text-red-600 mt-1">{errors.admin_email.message}</p>}
              </Field>
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Criando e enviando email...
                </>
              ) : (
                'Criar Oficina e Enviar Acesso'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal de edição completa ──────────────────────────────────────────────────

function EditModal({
  tenant,
  onClose,
  onUpdated,
}: {
  tenant: Tenant;
  onClose: () => void;
  onUpdated: (t: Tenant) => void;
}) {
  const [cepLoading, setCepLoading] = useState(false);
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<EditForm>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      name: tenant.name,
      razao_social: tenant.razao_social,
      nome_fantasia: tenant.nome_fantasia ?? '',
      document: tenant.document,
      email: tenant.email,
      phone: tenant.phone ?? '',
      municipio: tenant.municipio ?? '',
      uf: tenant.uf ?? '',
      cep: tenant.cep ?? '',
      logradouro: tenant.logradouro ?? '',
      numero: tenant.numero ?? '',
      complemento: tenant.complemento ?? '',
      bairro: tenant.bairro ?? '',
      inscricao_estadual: tenant.inscricao_estadual ?? '',
      inscricao_municipal: tenant.inscricao_municipal ?? '',
      limite_tecnicos: tenant.limite_tecnicos,
    },
  });

  const handleCepBlur = useCallback(async (e: React.FocusEvent<HTMLInputElement>) => {
    setCepLoading(true);
    const data = await lookupCep(e.target.value);
    if (data) {
      setValue('logradouro', data.logradouro, { shouldValidate: false });
      setValue('bairro', data.bairro, { shouldValidate: false });
      setValue('municipio', data.localidade, { shouldValidate: false });
      setValue('uf', data.uf, { shouldValidate: false });
    }
    setCepLoading(false);
  }, [setValue]);

  const onSubmit = async (data: EditForm) => {
    try {
      const payload: UpdateTenantPayload = {
        ...data,
        nome_fantasia: data.nome_fantasia || undefined,
        phone: data.phone || undefined,
        municipio: data.municipio || undefined,
        uf: data.uf || undefined,
        cep: data.cep || undefined,
        logradouro: data.logradouro || undefined,
        numero: data.numero || undefined,
        complemento: data.complemento || undefined,
        bairro: data.bairro || undefined,
        inscricao_estadual: data.inscricao_estadual || undefined,
        inscricao_municipal: data.inscricao_municipal || undefined,
      };
      const res = await tenantsApi.update(tenant.id, payload);
      toast.success('Oficina atualizada com sucesso!');
      onUpdated(res.data as Tenant);
    } catch (err) {
      toast.error(extractError(err, 'Erro ao atualizar oficina.'));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">Editar Oficina</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-5">

          <SectionLabel>Identificação</SectionLabel>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Field label="Nome fantasia *">
                <input {...register('name')} className={InputClass(!!errors.name)} />
                {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Razão social *">
                <input {...register('razao_social')} className={InputClass(!!errors.razao_social)} />
                {errors.razao_social && <p className="text-xs text-red-600 mt-1">{errors.razao_social.message}</p>}
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Nome fantasia (alternativo)">
                <input {...register('nome_fantasia')} placeholder="Opcional" className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="CPF / CNPJ *">
                <input {...register('document')} className={`${InputClass(!!errors.document)} font-mono`} />
                {errors.document && <p className="text-xs text-red-600 mt-1">{errors.document.message}</p>}
              </Field>
            </div>

            <div>
              <Field label="Limite de técnicos *">
                <input type="number" min={1} max={999} {...register('limite_tecnicos')} className={InputClass(!!errors.limite_tecnicos)} />
                {errors.limite_tecnicos && <p className="text-xs text-red-600 mt-1">{errors.limite_tecnicos.message}</p>}
              </Field>
            </div>

            <div>
              <Field label="Inscrição estadual">
                <input {...register('inscricao_estadual')} className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="Inscrição municipal">
                <input {...register('inscricao_municipal')} className={InputClass()} />
              </Field>
            </div>
          </div>

          <SectionLabel>Contato</SectionLabel>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Field label="E-mail *">
                <input type="email" {...register('email')} className={InputClass(!!errors.email)} />
                {errors.email && <p className="text-xs text-red-600 mt-1">{errors.email.message}</p>}
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Telefone">
                <input {...register('phone')} placeholder="(11) 99999-0000" className={InputClass()} />
              </Field>
            </div>
          </div>

          <SectionLabel>Endereço</SectionLabel>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Field label="CEP">
                <div className="relative">
                  <input
                    {...register('cep')}
                    placeholder="00000-000"
                    className={`${InputClass()} font-mono pr-8`}
                    onBlur={handleCepBlur}
                  />
                  {cepLoading && (
                    <MapPin className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-indigo-400 animate-pulse" />
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-0.5">Preenche endereço automaticamente</p>
              </Field>
            </div>

            <div>
              <Field label="UF">
                <input {...register('uf')} maxLength={2} className={`${InputClass()} uppercase`} />
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Município">
                <input {...register('municipio')} className={InputClass()} />
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Logradouro">
                <input {...register('logradouro')} placeholder="Av. Paulista" className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="Número">
                <input {...register('numero')} className={InputClass()} />
              </Field>
            </div>

            <div>
              <Field label="Complemento">
                <input {...register('complemento')} placeholder="Sala 01" className={InputClass()} />
              </Field>
            </div>

            <div className="col-span-2">
              <Field label="Bairro">
                <input {...register('bairro')} className={InputClass()} />
              </Field>
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition"
            >
              {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Salvar Alterações
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function MasterOficinasPage() {
  const router = useRouter();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null);
  const [deletingTenant, setDeletingTenant] = useState<Tenant | null>(null);
  const [logoTenant, setLogoTenant] = useState<Tenant | null>(null);

  useEffect(() => {
    if (!isSuperAdmin()) {
      router.replace('/master/login');
    }
  }, [router]);

  const fetchTenants = async () => {
    try {
      const res = await tenantsApi.list();
      setTenants(res.data as Tenant[]);
    } catch {
      toast.error('Erro ao carregar oficinas.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenants();
  }, []);

  const handleLogout = () => {
    clearTokens();
    router.push('/master/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gray-900 text-white shadow">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-indigo-600">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="text-base font-bold leading-none">AutoMaster</p>
              <p className="text-xs text-gray-400 mt-0.5">Administrador Master</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-sm text-gray-300 hover:text-white transition"
          >
            <LogOut className="w-4 h-4" />
            Sair
          </button>
        </div>
      </header>

      {/* Conteúdo */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Building2 className="w-6 h-6 text-indigo-600" />
              Oficinas Cadastradas
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              {tenants.length} oficina{tenants.length !== 1 ? 's' : ''} ativa{tenants.length !== 1 ? 's' : ''}
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold transition"
          >
            <Plus className="w-4 h-4" />
            Nova Oficina
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
          </div>
        ) : tenants.length === 0 ? (
          <div className="text-center py-24 text-gray-400">
            <Building2 className="w-12 h-12 mx-auto mb-3 opacity-40" />
            <p className="text-lg font-medium">Nenhuma oficina cadastrada</p>
            <p className="text-sm mt-1">Clique em &quot;Nova Oficina&quot; para começar.</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Oficina</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">CNPJ</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Contato</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Cidade / UF</th>
                  <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    <span className="flex items-center justify-center gap-1">
                      <Users className="w-3.5 h-3.5" />
                      Técnicos
                    </span>
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Acesso</th>
                  <th className="px-6 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {tenants.map((t) => (
                  <tr key={t.id} className="hover:bg-gray-50 transition">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        {t.logo_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={t.logo_url}
                            alt={t.name}
                            className="w-9 h-9 object-contain rounded-lg border border-gray-200 bg-white flex-shrink-0"
                          />
                        ) : (
                          <div className="w-9 h-9 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
                            <Building2 className="w-4 h-4 text-indigo-500" />
                          </div>
                        )}
                        <div>
                          <p className="font-medium text-gray-900">{t.name}</p>
                          <p className="text-xs text-gray-400">{t.razao_social}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono text-gray-600 text-xs">{t.document}</td>
                    <td className="px-6 py-4">
                      <p className="text-xs text-gray-600">{t.email}</p>
                      {t.phone && <p className="text-xs text-gray-400">{t.phone}</p>}
                    </td>
                    <td className="px-6 py-4 text-gray-600">
                      {[t.municipio, t.uf].filter(Boolean).join(' / ') || '—'}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className="inline-flex items-center justify-center px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700">
                        {t.limite_tecnicos} vagas
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <LoginLinkButton tenantId={t.id} />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2 justify-end">
                        <button
                          onClick={() => setLogoTenant(t)}
                          title="Gerenciar logo"
                          className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-600 border border-gray-200 hover:border-indigo-300 px-2.5 py-1.5 rounded-lg transition"
                        >
                          <ImagePlus className="w-3.5 h-3.5" />
                          Logo
                        </button>
                        <button
                          onClick={() => setEditingTenant(t)}
                          title="Editar oficina"
                          className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-600 border border-gray-200 hover:border-indigo-300 px-2.5 py-1.5 rounded-lg transition"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                          Editar
                        </button>
                        <button
                          onClick={() => setDeletingTenant(t)}
                          title="Excluir oficina"
                          className="inline-flex items-center gap-1.5 text-xs text-red-500 hover:text-red-700 border border-red-200 hover:border-red-400 px-2.5 py-1.5 rounded-lg transition"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Excluir
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={(t) => {
            setTenants((prev) => [...prev, t].sort((a, b) => a.name.localeCompare(b.name)));
            setShowCreate(false);
          }}
        />
      )}

      {editingTenant && (
        <EditModal
          tenant={editingTenant}
          onClose={() => setEditingTenant(null)}
          onUpdated={(updated) => {
            setTenants((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
            setEditingTenant(null);
          }}
        />
      )}

      {deletingTenant && (
        <DeleteModal
          tenant={deletingTenant}
          onClose={() => setDeletingTenant(null)}
          onDeleted={(id) => {
            setTenants((prev) => prev.filter((t) => t.id !== id));
            setDeletingTenant(null);
          }}
        />
      )}

      {logoTenant && (
        <LogoModal
          tenant={logoTenant}
          onClose={() => setLogoTenant(null)}
          onUpdated={(updated) => {
            setTenants((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
            setLogoTenant(null);
          }}
        />
      )}
    </div>
  );
}
