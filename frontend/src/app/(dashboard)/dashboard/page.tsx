'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  TrendingUp, TrendingDown, DollarSign, ClipboardList,
  Clock, CheckCircle, AlertTriangle, Users, ArrowUpRight, ArrowDownRight,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { PageSpinner } from '@/components/ui/spinner';
import { dashboardApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';

// ── Types ─────────────────────────────────────────────────────────────────────
interface MonthlyRevenue { month: string; year: number; receitas: number; despesas: number; }
interface OsStatusCount  { status: string; count: number; }
interface TopClient      { name: string; total: number; os_count: number; }
interface LowStockItem   { id: string; name: string; sku: string; quantity: number; min_quantity: number; }
interface DashboardData  {
  receita_mes_atual: number;
  receita_mes_anterior: number;
  despesa_mes_atual: number;
  saldo_mes_atual: number;
  ticket_medio: number;
  os_abertas: number;
  os_em_andamento: number;
  os_finalizadas: number;
  receita_mensal: MonthlyRevenue[];
  os_por_status: OsStatusCount[];
  top_clientes: TopClient[];
  estoque_critico: LowStockItem[];
}

// ── Cores dos gráficos ────────────────────────────────────────────────────────
const PIE_COLORS = ['#3B82F6', '#F59E0B', '#22C55E', '#EF4444'];
const BAR_RECEITA = '#22C55E';
const BAR_DESPESA = '#EF4444';

// ── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({
  title, value, sub, icon: Icon, iconBg, iconColor, trend,
}: {
  title: string; value: string; sub?: string;
  icon: React.ElementType; iconBg: string; iconColor: string;
  trend?: 'up' | 'down' | 'neutral';
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 px-3 sm:pt-5 sm:pb-4 sm:px-6">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-tight sm:tracking-wider leading-tight">{title}</p>
            <p className="text-xl sm:text-2xl font-bold text-gray-900 mt-1 truncate">{value}</p>
            {sub && (
              <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
                {trend === 'up'      && <ArrowUpRight   className="w-3 h-3 text-green-500" />}
                {trend === 'down'    && <ArrowDownRight className="w-3 h-3 text-red-500" />}
                {sub}
              </p>
            )}
          </div>
          <div className={`flex-shrink-0 w-9 h-9 sm:w-11 sm:h-11 rounded-xl flex items-center justify-center ${iconBg}`}>
            <Icon className={`w-4 h-4 sm:w-5 sm:h-5 ${iconColor}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Custom Tooltip do BarChart ────────────────────────────────────────────────
function BarTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm">
      <p className="font-semibold text-gray-700 mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.name === 'receitas' ? BAR_RECEITA : BAR_DESPESA }}>
          {p.name === 'receitas' ? 'Receitas' : 'Despesas'}: {formatCurrency(p.value)}
        </p>
      ))}
    </div>
  );
}

// ── Pie Custom Label ──────────────────────────────────────────────────────────
function PieLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }: {
  cx: number; cy: number; midAngle: number;
  innerRadius: number; outerRadius: number; percent: number;
}) {
  if (percent < 0.05) return null;
  const RADIAN = Math.PI / 180;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central"
      fontSize={11} fontWeight="bold">
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: async () => (await dashboardApi.get()).data,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return (
    <div><Header title="Dashboard" /><PageSpinner /></div>
  );

  if (!data) return (
    <div><Header title="Dashboard" />
      <div className="p-6 text-sm text-gray-500">Erro ao carregar dashboard.</div>
    </div>
  );

  // Variação receita mês atual vs anterior
  const varReceita = data.receita_mes_anterior > 0
    ? ((data.receita_mes_atual - data.receita_mes_anterior) / data.receita_mes_anterior) * 100
    : null;
  const varText = varReceita !== null
    ? `${varReceita >= 0 ? '+' : ''}${varReceita.toFixed(1)}% vs mês anterior`
    : 'Primeiro mês de dados';

  // Filtra status com count > 0 para o Pie
  const pieData = data.os_por_status.filter((s) => s.count > 0);
  const totalOS = data.os_abertas + data.os_em_andamento + data.os_finalizadas;

  return (
    <div>
      <Header title="Dashboard" />
      <div className="p-3 sm:p-6 space-y-4 sm:space-y-6">

        {/* ── KPI Row 1: Financeiro ── */}
        <div>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Financeiro — mês atual</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-4">
            <KpiCard
              title="Receita"
              value={formatCurrency(data.receita_mes_atual)}
              sub={varText}
              trend={varReceita !== null ? (varReceita >= 0 ? 'up' : 'down') : 'neutral'}
              icon={TrendingUp}
              iconBg="bg-green-50"
              iconColor="text-green-600"
            />
            <KpiCard
              title="Despesas"
              value={formatCurrency(data.despesa_mes_atual)}
              icon={TrendingDown}
              iconBg="bg-red-50"
              iconColor="text-red-500"
            />
            <KpiCard
              title="Saldo"
              value={formatCurrency(data.saldo_mes_atual)}
              icon={DollarSign}
              iconBg={data.saldo_mes_atual >= 0 ? 'bg-green-50' : 'bg-red-50'}
              iconColor={data.saldo_mes_atual >= 0 ? 'text-green-600' : 'text-red-500'}
            />
            <KpiCard
              title="Ticket Médio"
              value={data.ticket_medio > 0 ? formatCurrency(data.ticket_medio) : '—'}
              sub="OS finalizadas"
              icon={DollarSign}
              iconBg="bg-blue-50"
              iconColor="text-blue-600"
            />
          </div>
        </div>

        {/* ── KPI Row 2: OS ── */}
        <div>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Ordens de Serviço — total</h2>
          <div className="grid grid-cols-3 gap-2 sm:gap-4">
            <KpiCard
              title="Abertas"
              value={String(data.os_abertas)}
              icon={ClipboardList}
              iconBg="bg-blue-50"
              iconColor="text-blue-600"
            />
            <KpiCard
              title="Em Andamento"
              value={String(data.os_em_andamento)}
              icon={Clock}
              iconBg="bg-yellow-50"
              iconColor="text-yellow-600"
            />
            <KpiCard
              title="Finalizadas"
              value={String(data.os_finalizadas)}
              icon={CheckCircle}
              iconBg="bg-green-50"
              iconColor="text-green-600"
            />
          </div>
        </div>

        {/* ── Gráficos ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* Bar Chart — Receita vs Despesa */}
          <Card className="lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-700">Receita × Despesa — últimos 6 meses</CardTitle>
            </CardHeader>
            <CardContent>
              {data.receita_mensal.every((m) => m.receitas === 0 && m.despesas === 0) ? (
                <div className="flex items-center justify-center h-48 text-sm text-gray-400">
                  Nenhum lançamento financeiro ainda
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.receita_mensal} margin={{ top: 4, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
                    <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                    <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#6B7280' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} axisLine={false} tickLine={false}
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} width={38} />
                    <Tooltip content={<BarTooltip />} />
                    <Bar dataKey="receitas" name="receitas" fill={BAR_RECEITA} radius={[3,3,0,0]} />
                    <Bar dataKey="despesas" name="despesas" fill={BAR_DESPESA} radius={[3,3,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
              <div className="flex items-center gap-4 mt-2 justify-center text-xs text-gray-500">
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{background:BAR_RECEITA}} />Receitas</span>
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{background:BAR_DESPESA}} />Despesas</span>
              </div>
            </CardContent>
          </Card>

          {/* Pie Chart — OS por status */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-700">OS por Status</CardTitle>
            </CardHeader>
            <CardContent>
              {totalOS === 0 ? (
                <div className="flex items-center justify-center h-48 text-sm text-gray-400">
                  Nenhuma OS cadastrada
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" outerRadius={75}
                      dataKey="count" nameKey="status"
                      labelLine={false} label={PieLabel as never}>
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Legend iconSize={10} iconType="circle"
                      formatter={(v) => <span className="text-xs text-gray-600">{v}</span>} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Bottom Row ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          {/* Top 5 clientes */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <Users className="w-4 h-4 text-gray-400" />
                  Top 5 Clientes
                </CardTitle>
                <Link href="/clients" className="text-xs text-green-600 hover:text-green-700 font-medium">
                  Ver todos →
                </Link>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {data.top_clientes.length === 0 ? (
                <p className="text-sm text-gray-400 py-6 text-center">Nenhum dado ainda</p>
              ) : (
                <div className="space-y-2">
                  {data.top_clientes.map((c, i) => (
                    <div key={c.name} className="flex items-center gap-3">
                      <span className="w-5 h-5 rounded-full bg-gray-100 text-gray-500 text-xs flex items-center justify-center font-bold flex-shrink-0">
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">{c.name}</p>
                        <p className="text-xs text-gray-400">{c.os_count} OS finalizada{c.os_count !== 1 ? 's' : ''}</p>
                      </div>
                      <span className="text-sm font-semibold text-green-700 flex-shrink-0">
                        {formatCurrency(c.total)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Estoque crítico */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-orange-400" />
                  Estoque Crítico
                </CardTitle>
                <Link href="/stock" className="text-xs text-green-600 hover:text-green-700 font-medium">
                  Ver estoque →
                </Link>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {data.estoque_critico.length === 0 ? (
                <div className="flex flex-col items-center py-6 text-center">
                  <CheckCircle className="w-8 h-8 text-green-400 mb-2" />
                  <p className="text-sm text-gray-400">Estoque em dia!</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {data.estoque_critico.map((item) => (
                    <Link key={item.id} href={`/stock/${item.id}`}
                      className="flex items-center gap-3 hover:bg-gray-50 rounded-lg p-1 -mx-1 transition">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">{item.name}</p>
                        <p className="text-xs text-gray-400">SKU: {item.sku}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-sm font-bold text-red-600">{item.quantity.toFixed(2)}</p>
                        <p className="text-xs text-gray-400">mín: {item.min_quantity.toFixed(2)}</p>
                      </div>
                      <Badge className="bg-orange-100 text-orange-700 border-orange-200 text-xs">Baixo</Badge>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

      </div>
    </div>
  );
}
