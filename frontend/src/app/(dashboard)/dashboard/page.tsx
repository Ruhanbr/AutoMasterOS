'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import {
  ClipboardList,
  CheckCircle,
  Clock,
  FileText,
  AlertCircle,
  XCircle,
  TrendingUp,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { PageSpinner } from '@/components/ui/spinner';
import { serviceOrdersApi, invoicesApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import type { ServiceOrder, Invoice, PaginatedResponse } from '@/types';

function StatCard({
  title,
  value,
  icon: Icon,
  colorClass,
  bgClass,
}: {
  title: string;
  value: number | string;
  icon: React.ElementType;
  colorClass: string;
  bgClass: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-500">{title}</p>
            <p className="text-3xl font-bold text-gray-900 mt-1">{value}</p>
          </div>
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${bgClass}`}>
            <Icon className={`w-6 h-6 ${colorClass}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function statusBadge(status: string) {
  switch (status) {
    case 'ABERTA':
      return <Badge variant="info">Aberta</Badge>;
    case 'EM_ANDAMENTO':
      return <Badge variant="warning">Em Andamento</Badge>;
    case 'FINALIZADA':
      return <Badge variant="default">Finalizada</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export default function DashboardPage() {
  const { data: abertas, isLoading: loadingAbertas } = useQuery<PaginatedResponse<ServiceOrder>>({
    queryKey: ['service-orders', 'ABERTA'],
    queryFn: async () => {
      const res = await serviceOrdersApi.list({ status: 'ABERTA', page_size: 1 });
      return res.data;
    },
  });

  const { data: emAndamento, isLoading: loadingAndamento } = useQuery<PaginatedResponse<ServiceOrder>>({
    queryKey: ['service-orders', 'EM_ANDAMENTO'],
    queryFn: async () => {
      const res = await serviceOrdersApi.list({ status: 'EM_ANDAMENTO', page_size: 1 });
      return res.data;
    },
  });

  const { data: finalizadas, isLoading: loadingFinalizadas } = useQuery<PaginatedResponse<ServiceOrder>>({
    queryKey: ['service-orders', 'FINALIZADA'],
    queryFn: async () => {
      const res = await serviceOrdersApi.list({ status: 'FINALIZADA', page_size: 1 });
      return res.data;
    },
  });

  const { data: invoices, isLoading: loadingInvoices } = useQuery<PaginatedResponse<Invoice>>({
    queryKey: ['invoices', 'all'],
    queryFn: async () => {
      const res = await invoicesApi.list({ page_size: 1 });
      return res.data;
    },
  });

  const { data: invoicesAutorizadas } = useQuery<PaginatedResponse<Invoice>>({
    queryKey: ['invoices', 'AUTORIZADA'],
    queryFn: async () => {
      const res = await invoicesApi.list({ status: 'AUTORIZADA', page_size: 1 });
      return res.data;
    },
  });

  const { data: invoicesRejeitadas } = useQuery<PaginatedResponse<Invoice>>({
    queryKey: ['invoices', 'REJEITADA'],
    queryFn: async () => {
      const res = await invoicesApi.list({ status: 'REJEITADA', page_size: 1 });
      return res.data;
    },
  });

  const { data: recentOS, isLoading: loadingRecent } = useQuery<PaginatedResponse<ServiceOrder>>({
    queryKey: ['service-orders', 'recent'],
    queryFn: async () => {
      const res = await serviceOrdersApi.list({ page: 1, page_size: 5 });
      return res.data;
    },
  });

  const isLoading =
    loadingAbertas || loadingAndamento || loadingFinalizadas || loadingInvoices || loadingRecent;

  if (isLoading) return (
    <div>
      <Header title="Dashboard" />
      <PageSpinner />
    </div>
  );

  return (
    <div>
      <Header title="Dashboard" />
      <div className="p-6 space-y-6">
        {/* Stats — Service Orders */}
        <div>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Ordens de Serviço
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard
              title="Abertas"
              value={abertas?.total ?? 0}
              icon={ClipboardList}
              colorClass="text-blue-600"
              bgClass="bg-blue-50"
            />
            <StatCard
              title="Em Andamento"
              value={emAndamento?.total ?? 0}
              icon={Clock}
              colorClass="text-yellow-600"
              bgClass="bg-yellow-50"
            />
            <StatCard
              title="Finalizadas"
              value={finalizadas?.total ?? 0}
              icon={CheckCircle}
              colorClass="text-green-600"
              bgClass="bg-green-50"
            />
          </div>
        </div>

        {/* Stats — NF-e */}
        <div>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Notas Fiscais (NF-e)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard
              title="Total NF-e"
              value={invoices?.total ?? 0}
              icon={TrendingUp}
              colorClass="text-purple-600"
              bgClass="bg-purple-50"
            />
            <StatCard
              title="Autorizadas"
              value={invoicesAutorizadas?.total ?? 0}
              icon={FileText}
              colorClass="text-green-600"
              bgClass="bg-green-50"
            />
            <StatCard
              title="Rejeitadas"
              value={invoicesRejeitadas?.total ?? 0}
              icon={XCircle}
              colorClass="text-red-600"
              bgClass="bg-red-50"
            />
          </div>
        </div>

        {/* Recent Service Orders */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Ordens de Serviço Recentes</CardTitle>
              <Link
                href="/service-orders"
                className="text-sm text-green-600 hover:text-green-700 font-medium"
              >
                Ver todas
              </Link>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            {loadingRecent ? (
              <PageSpinner />
            ) : recentOS?.items?.length === 0 ? (
              <div className="flex flex-col items-center py-10 text-gray-400">
                <AlertCircle className="w-10 h-10 mb-2" />
                <p className="text-sm">Nenhuma ordem de serviço encontrada</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {recentOS?.items?.map((os) => (
                  <Link
                    key={os.id}
                    href={`/service-orders/${os.id}`}
                    className="flex items-center justify-between py-3 hover:bg-gray-50 px-2 rounded-lg transition -mx-2"
                  >
                    <div className="flex items-center gap-3">
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          #{os.number} — {os.client.name}
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5">{formatDate(os.opened_at)}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm font-semibold text-gray-900">
                        {formatCurrency(os.total_amount)}
                      </span>
                      {statusBadge(os.status)}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
