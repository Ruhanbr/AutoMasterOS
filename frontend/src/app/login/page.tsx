'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { Tractor, Eye, EyeOff, Loader2, CheckCircle } from 'lucide-react';
import { authApi } from '@/lib/api';
import { setTokens } from '@/lib/auth';
import type { LoginResponse } from '@/types';
import type { AxiosError } from 'axios';

const loginSchema = z.object({
  email: z.string().email('E-mail inválido'),
  password: z.string().min(1, 'Senha obrigatória'),
  tenant_id: z.string().uuid('Código da oficina inválido (deve ser um UUID)'),
});

type LoginForm = z.infer<typeof loginSchema>;

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const from = searchParams.get('from') || '/dashboard';

  // Se ?tenant=<uuid> vier na URL, pré-preenche e trava o campo
  const tenantFromUrl = searchParams.get('tenant') || '';
  const tenantLocked = tenantFromUrl.length === 36;

  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { tenant_id: tenantFromUrl },
  });

  const onSubmit = async (data: LoginForm) => {
    try {
      const response = await authApi.login(data.email, data.password, data.tenant_id);
      const { access_token, refresh_token } = response.data as LoginResponse;
      setTokens(access_token, refresh_token);
      toast.success('Login realizado com sucesso!');
      router.push(from);
      router.refresh();
    } catch (error) {
      const axiosError = error as AxiosError<{ detail: string }>;
      const message =
        axiosError.response?.data?.detail ||
        'Credenciais inválidas. Verifique e-mail, senha e código da oficina.';
      toast.error(message);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-green-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-green-600 shadow-lg mb-4">
            <Tractor className="w-9 h-9 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900">AutoMaster</h1>
          <p className="text-gray-600 mt-1">Gestão de Oficinas Agrícolas</p>
        </div>

        {/* Banner quando o link já vem com tenant */}
        {tenantLocked && (
          <div className="mb-4 flex items-center gap-2 px-4 py-3 bg-green-600 text-white rounded-xl text-sm font-medium shadow">
            <CheckCircle className="w-4 h-4 flex-shrink-0" />
            Código da oficina preenchido automaticamente.
          </div>
        )}

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">Entrar na sua conta</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
                E-mail
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="seuemail@oficina.com"
                {...register('email')}
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition placeholder-gray-400 text-sm"
              />
              {errors.email && (
                <p className="mt-1.5 text-xs text-red-600">{errors.email.message}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
                Senha
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  {...register('password')}
                  className="w-full px-4 py-2.5 pr-10 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition placeholder-gray-400 text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.password && (
                <p className="mt-1.5 text-xs text-red-600">{errors.password.message}</p>
              )}
            </div>

            {/* Tenant ID — oculto quando vem da URL */}
            {!tenantLocked && (
              <div>
                <label htmlFor="tenant_id" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Código da Oficina
                </label>
                <input
                  id="tenant_id"
                  type="text"
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  {...register('tenant_id')}
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition placeholder-gray-400 text-sm font-mono"
                />
                {errors.tenant_id && (
                  <p className="mt-1.5 text-xs text-red-600">{errors.tenant_id.message}</p>
                )}
              </div>
            )}

            {/* Campo hidden quando tenant está travado */}
            {tenantLocked && (
              <input type="hidden" {...register('tenant_id')} />
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 px-4 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white font-semibold rounded-lg transition focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 flex items-center justify-center gap-2 mt-2"
            >
              {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
              {isSubmitting ? 'Entrando...' : 'Entrar'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-gray-500 mt-6">
          AutoMaster &copy; {new Date().getFullYear()} — Todos os direitos reservados
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPageContent />
    </Suspense>
  );
}
