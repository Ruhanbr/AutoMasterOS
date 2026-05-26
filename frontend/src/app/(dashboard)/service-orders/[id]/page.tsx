'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Play,
  CheckCircle,
  Loader2,
  AlertCircle,
  FileText,
  User,
  Wrench,
  Package,
  Download,
  FileDown,
  MessageCircle,
  Send,
  Copy,
  ExternalLink,
  Clock,
  CheckCircle2,
  XCircle,
  Ban,
  Navigation,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
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
import { PageSpinner } from '@/components/ui/spinner';
import { Textarea } from '@/components/ui/textarea';
import { serviceOrdersApi, invoicesApi, reportsApi } from '@/lib/api';
import { formatCurrency, formatDate, formatDocument } from '@/lib/utils';
import type { ServiceOrder, Invoice, ServiceOrderStatus } from '@/types';
import type { AxiosError } from 'axios';

function StatusBadge({ status }: { status: ServiceOrderStatus }) {
  switch (status) {
    case 'ABERTA':
      return <Badge variant="info" className="text-sm px-3 py-1">Aberta</Badge>;
    case 'EM_ANDAMENTO':
      return <Badge variant="warning" className="text-sm px-3 py-1">Em Andamento</Badge>;
    case 'FINALIZADA':
      return <Badge variant="default" className="text-sm px-3 py-1">Finalizada</Badge>;
    case 'CANCELADA':
      return <Badge variant="destructive" className="text-sm px-3 py-1">Cancelada</Badge>;
    default:
      return <Badge variant="secondary" className="text-sm px-3 py-1">{status}</Badge>;
  }
}

function InvoiceStatusBadge({ status }: { status: string }) {
  switch (status) {
    case 'AUTORIZADA':
      return <Badge variant="default">Autorizada</Badge>;
    case 'REJEITADA':
      return <Badge variant="destructive">Rejeitada</Badge>;
    case 'PROCESSANDO':
      return <Badge variant="warning">Processando</Badge>;
    case 'PENDENTE':
      return <Badge variant="secondary">Pendente</Badge>;
    case 'ERRO':
      return <Badge variant="destructive">Erro</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export default function ServiceOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState('');
  const [showNotesFor, setShowNotesFor] = useState<string | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [pdfLoading, setPdfLoading] = useState(false);
  const [waLoading, setWaLoading] = useState(false);
  const [budgetLoading, setBudgetLoading] = useState(false);

  const { data: os, isLoading, error } = useQuery<ServiceOrder>({
    queryKey: ['service-order', params.id],
    queryFn: async () => {
      const res = await serviceOrdersApi.get(params.id);
      return res.data;
    },
  });

  const { data: invoice } = useQuery<Invoice | null>({
    queryKey: ['invoice-for-os', params.id],
    queryFn: async () => {
      try {
        const res = await invoicesApi.getByServiceOrder(params.id);
        return res.data;
      } catch {
        return null;
      }
    },
    enabled: !!os,
  });

  const statusMutation = useMutation({
    mutationFn: async ({ status, notes }: { status: string; notes?: string }) => {
      const res = await serviceOrdersApi.updateStatus(params.id, status, notes);
      return res.data;
    },
    onSuccess: () => {
      toast.success('Status atualizado!');
      queryClient.invalidateQueries({ queryKey: ['service-order', params.id] });
      queryClient.invalidateQueries({ queryKey: ['service-orders'] });
      setNotes('');
      setShowNotesFor(null);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar status');
    },
  });

  const finalizeMutation = useMutation({
    mutationFn: async (notes?: string) => {
      const res = await serviceOrdersApi.finalize(params.id, notes);
      return res.data;
    },
    onSuccess: () => {
      toast.success('Ordem de serviço finalizada!');
      queryClient.invalidateQueries({ queryKey: ['service-order', params.id] });
      queryClient.invalidateQueries({ queryKey: ['service-orders'] });
      setNotes('');
      setShowNotesFor(null);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      toast.error(error.response?.data?.detail || 'Erro ao finalizar OS');
    },
  });

  if (isLoading) {
    return (
      <div>
        <Header title="Ordem de Serviço" />
        <PageSpinner />
      </div>
    );
  }

  if (error || !os) {
    return (
      <div>
        <Header title="Ordem de Serviço" />
        <div className="flex flex-col items-center py-20 text-gray-400">
          <AlertCircle className="w-12 h-12 mb-3" />
          <p>Ordem de serviço não encontrada</p>
          <Link href="/service-orders" className="mt-4">
            <Button variant="outline" size="sm">Voltar</Button>
          </Link>
        </div>
      </div>
    );
  }

  const handleDownloadPdf = async () => {
    setPdfLoading(true);
    try {
      const res = await reportsApi.downloadOsPdf(params.id);
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `OS-${os.number}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Erro ao gerar PDF');
    } finally {
      setPdfLoading(false);
    }
  };

  const handleWhatsApp = async () => {
    setWaLoading(true);
    try {
      const res = await reportsApi.getWhatsappLink(params.id);
      const link = res.data.link;
      // No mobile, window.open é bloqueado após await — usa location.href
      // que funciona tanto para abrir o app WhatsApp quanto o web.whatsapp.com
      window.location.href = link;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Erro ao gerar link WhatsApp');
    } finally {
      setWaLoading(false);
    }
  };

  const handleSendBudget = async () => {
    setBudgetLoading(true);
    try {
      await serviceOrdersApi.sendBudget(params.id);
      toast.success('Orçamento enviado para aprovação!');
      queryClient.invalidateQueries({ queryKey: ['service-order', params.id] });
    } catch {
      toast.error('Erro ao enviar orçamento');
    } finally {
      setBudgetLoading(false);
    }
  };

  const handleCopyPortalLink = () => {
    if (!os?.public_token) return;
    const baseUrl = window.location.origin;
    const link = `${baseUrl}/os/${os.public_token}`;
    navigator.clipboard.writeText(link);
    toast.success('Link copiado!');
  };

  const handleOpenPortal = () => {
    if (!os?.public_token) return;
    const baseUrl = window.location.origin;
    window.open(`${baseUrl}/os/${os.public_token}`, '_blank');
  };

  const isPending = statusMutation.isPending || finalizeMutation.isPending;

  return (
    <div>
      <Header title={`OS #${os.number}`} />
      <div className="p-6 max-w-5xl mx-auto space-y-6">
        {/* Back + Status */}
        <div className="flex items-center justify-between">
          <Link href="/service-orders">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4" />
              Voltar
            </Button>
          </Link>
          <StatusBadge status={os.status} />
        </div>

        {/* ── Portal do Cliente / Aprovação de Orçamento ── */}
        {os.items && os.items.length > 0 && (
          <Card className={`border-2 ${
            os.budget_status === 'APROVADO' ? 'border-emerald-200 bg-emerald-50' :
            os.budget_status === 'RECUSADO' ? 'border-red-200 bg-red-50' :
            os.budget_status === 'AGUARDANDO_APROVACAO' ? 'border-amber-200 bg-amber-50' :
            'border-indigo-200 bg-indigo-50'
          }`}>
            <CardContent className="pt-4">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <p className="text-sm font-semibold text-gray-800 mb-1 flex items-center gap-2">
                    {os.budget_status === 'APROVADO' && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
                    {os.budget_status === 'RECUSADO' && <XCircle className="w-4 h-4 text-red-600" />}
                    {os.budget_status === 'AGUARDANDO_APROVACAO' && <Clock className="w-4 h-4 text-amber-600" />}
                    {os.budget_status === 'RASCUNHO' && <Send className="w-4 h-4 text-indigo-600" />}
                    Portal do Cliente
                  </p>
                  <p className="text-xs text-gray-500">
                    {os.budget_status === 'RASCUNHO' && 'Envie o orçamento para o cliente aprovar pelo celular.'}
                    {os.budget_status === 'AGUARDANDO_APROVACAO' && `Aguardando aprovação do cliente.${os.client_viewed_at ? ' ✓ Cliente já visualizou.' : ' Ainda não visualizado.'}`}
                    {os.budget_status === 'APROVADO' && `Aprovado pelo cliente em ${os.budget_approved_at ? new Date(os.budget_approved_at).toLocaleDateString('pt-BR') : '—'}.`}
                    {os.budget_status === 'RECUSADO' && `Recusado em ${os.budget_rejected_at ? new Date(os.budget_rejected_at).toLocaleDateString('pt-BR') : '—'}.${os.budget_rejection_reason ? ` Motivo: "${os.budget_rejection_reason}"` : ''}`}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {/* Copiar link do portal */}
                  {os.public_token && (
                    <>
                      <Button size="sm" variant="outline" onClick={handleCopyPortalLink}>
                        <Copy className="w-3 h-3" /> Copiar link
                      </Button>
                      <Button size="sm" variant="outline" onClick={handleOpenPortal}>
                        <ExternalLink className="w-3 h-3" /> Ver portal
                      </Button>
                    </>
                  )}

                  {/* Enviar orçamento para aprovação */}
                  {(os.budget_status === 'RASCUNHO' || os.budget_status === 'RECUSADO') && os.status !== 'FINALIZADA' && (
                    <Button size="sm" onClick={handleSendBudget} disabled={budgetLoading}>
                      {budgetLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                      {os.budget_status === 'RECUSADO' ? 'Reenviar orçamento' : 'Enviar para aprovação'}
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Action Buttons + Cancel */}
        {os.status !== 'FINALIZADA' && os.status !== 'CANCELADA' && (
          <Card className="border-dashed border-2 border-green-200 bg-green-50">
            <CardContent className="pt-4">
              <p className="text-sm font-medium text-green-800 mb-3">Ações disponíveis</p>

              {/* Iniciar / Finalizar */}
              {!showCancelConfirm && !showNotesFor && (
                <div className="flex flex-wrap gap-3 mb-4">
                  {os.status === 'ABERTA' && (
                    <Button onClick={() => setShowNotesFor('EM_ANDAMENTO')} disabled={isPending}>
                      <Play className="w-4 h-4" /> Iniciar Atendimento
                    </Button>
                  )}
                  {os.status === 'EM_ANDAMENTO' && (
                    <Button onClick={() => setShowNotesFor('FINALIZADA')} disabled={isPending}>
                      <CheckCircle className="w-4 h-4" /> Finalizar OS
                    </Button>
                  )}
                </div>
              )}

              {/* Form: Iniciar */}
              {showNotesFor === 'EM_ANDAMENTO' && (
                <div className="space-y-2 mb-4">
                  <Textarea placeholder="Observações (opcional)..." value={notes} onChange={(e) => setNotes(e.target.value)} className="w-72 h-16 text-sm" />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => statusMutation.mutate({ status: 'EM_ANDAMENTO', notes: notes || undefined })} disabled={isPending}>
                      {isPending && <Loader2 className="w-3 h-3 animate-spin" />} Confirmar
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setShowNotesFor(null)}>Voltar</Button>
                  </div>
                </div>
              )}

              {/* Form: Finalizar */}
              {showNotesFor === 'FINALIZADA' && (
                <div className="space-y-2 mb-4">
                  <Textarea placeholder="Notas técnicas (opcional)..." value={notes} onChange={(e) => setNotes(e.target.value)} className="w-72 h-16 text-sm" />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => finalizeMutation.mutate(notes || undefined)} disabled={isPending}>
                      {isPending && <Loader2 className="w-3 h-3 animate-spin" />} Confirmar Finalização
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setShowNotesFor(null)}>Voltar</Button>
                  </div>
                </div>
              )}

              {/* Cancelar OS */}
              {!showNotesFor && (
                <div className="pt-3 border-t border-green-200">
                  {!showCancelConfirm ? (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => setShowCancelConfirm(true)}
                      disabled={isPending}
                    >
                      <Ban className="w-4 h-4" /> Cancelar OS
                    </Button>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm font-semibold text-red-700">Confirmar cancelamento da OS #{os.number}</p>
                      <Textarea
                        placeholder="Motivo (opcional)..."
                        value={cancelReason}
                        onChange={(e) => setCancelReason(e.target.value)}
                        className="w-full h-14 text-sm"
                      />
                      <div className="flex gap-2">
                        <Button size="sm" variant="destructive" disabled={isPending}
                          onClick={() => statusMutation.mutate(
                            { status: 'CANCELADA', notes: cancelReason || undefined },
                            { onSuccess: () => { setShowCancelConfirm(false); setCancelReason(''); } }
                          )}>
                          {isPending && <Loader2 className="w-3 h-3 animate-spin" />} Confirmar
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => { setShowCancelConfirm(false); setCancelReason(''); }}>
                          Voltar
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Banner OS cancelada */}
        {os.status === 'CANCELADA' && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-5 py-4">
            <Ban className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-red-800">Ordem de Serviço cancelada</p>
              {os.technician_notes && (
                <p className="text-sm text-red-600 mt-0.5">Motivo: {os.technician_notes}</p>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column */}
          <div className="lg:col-span-2 space-y-6">
            {/* Main info */}
            <Card>
              <CardHeader>
                <CardTitle>Informações da OS</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Descrição</p>
                  <p className="text-sm text-gray-900 mt-1">{os.description}</p>
                </div>
                {os.technician_name && (
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Técnico</p>
                    <p className="text-sm text-gray-900 mt-1">{os.technician_name}</p>
                  </div>
                )}
                {os.technician_notes && (
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Notas Técnicas</p>
                    <p className="text-sm text-gray-700 mt-1 whitespace-pre-wrap">{os.technician_notes}</p>
                  </div>
                )}
                <div className="grid grid-cols-3 gap-4 pt-2 border-t border-gray-100">
                  <div>
                    <p className="text-xs text-gray-500">Abertura</p>
                    <p className="text-sm font-medium text-gray-900 mt-0.5">{formatDate(os.opened_at)}</p>
                  </div>
                  {os.started_at && (
                    <div>
                      <p className="text-xs text-gray-500">Início</p>
                      <p className="text-sm font-medium text-gray-900 mt-0.5">{formatDate(os.started_at)}</p>
                    </div>
                  )}
                  {os.finished_at && (
                    <div>
                      <p className="text-xs text-gray-500">Finalização</p>
                      <p className="text-sm font-medium text-gray-900 mt-0.5">{formatDate(os.finished_at)}</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Items */}
            <Card>
              <CardHeader>
                <CardTitle>Itens</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                {os.items.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-6">Nenhum item registrado</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Tipo</TableHead>
                        <TableHead>Descrição</TableHead>
                        <TableHead className="text-right">Qtd</TableHead>
                        <TableHead className="text-right">Unit.</TableHead>
                        <TableHead className="text-right">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {os.items.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell>
                            {item.item_type === 'SERVICO' ? (
                              <div className="flex items-center gap-1 text-blue-700">
                                <Wrench className="w-3.5 h-3.5" />
                                <span className="text-xs font-medium">Serviço</span>
                              </div>
                            ) : item.item_type === 'DESLOCAMENTO' ? (
                              <div className="flex items-center gap-1 text-purple-700">
                                <Navigation className="w-3.5 h-3.5" />
                                <span className="text-xs font-medium">Deslocamento</span>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1 text-orange-700">
                                <Package className="w-3.5 h-3.5" />
                                <span className="text-xs font-medium">Peça</span>
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="font-medium">{item.description}</TableCell>
                          <TableCell className="text-right">{Number(item.quantity).toFixed(2)}</TableCell>
                          <TableCell className="text-right">{formatCurrency(item.unit_price)}</TableCell>
                          <TableCell className="text-right font-semibold">
                            {formatCurrency(item.total_price)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}

                {/* Totals */}
                <div className="mt-4 pt-4 border-t border-gray-200 space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Total Serviços</span>
                    <span className="font-medium">{formatCurrency(os.total_services)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Total Peças</span>
                    <span className="font-medium">{formatCurrency(os.total_parts)}</span>
                  </div>
                  {os.total_displacement > 0 && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Total Deslocamento</span>
                      <span className="font-medium">{formatCurrency(os.total_displacement)}</span>
                    </div>
                  )}
                  <div className="flex justify-between text-base font-bold border-t border-gray-200 pt-2 mt-2">
                    <span>Total Geral</span>
                    <span className="text-green-700">{formatCurrency(os.total_amount)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right column */}
          <div className="space-y-6">
            {/* Client */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <User className="w-4 h-4 text-gray-400" />
                  Cliente
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                <p className="font-semibold text-gray-900">{os.client.name}</p>
                <p className="text-sm text-gray-500">{formatDocument(os.client.document)}</p>
              </CardContent>
            </Card>

            {/* Machine */}
            {os.machine && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Wrench className="w-4 h-4 text-gray-400" />
                    Máquina
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0 space-y-2">
                  <p className="text-xs font-mono font-semibold text-gray-500 tracking-wider uppercase">
                    {os.machine.serial_number}
                  </p>
                  <div>
                    <p className="font-semibold text-gray-900">
                      {os.machine.brand} {os.machine.model}
                    </p>
                    {os.machine.machine_type && (
                      <p className="text-xs text-gray-500 mt-0.5">{os.machine.machine_type}{os.machine.year ? ` · ${os.machine.year}` : ''}</p>
                    )}
                  </div>
                  <Link
                    href={`/machines/${os.machine.id}`}
                    className="text-xs text-green-600 hover:underline"
                  >
                    Ver ficha da máquina →
                  </Link>
                </CardContent>
              </Card>
            )}

            {/* NF-e */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <FileText className="w-4 h-4 text-gray-400" />
                  Nota Fiscal (NF-e)
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                {invoice ? (
                  <div className="space-y-2">
                    <InvoiceStatusBadge status={invoice.status} />
                    {invoice.number && (
                      <div>
                        <p className="text-xs text-gray-500">Número</p>
                        <p className="text-sm font-medium">{invoice.number}</p>
                      </div>
                    )}
                    {invoice.access_key && (
                      <div>
                        <p className="text-xs text-gray-500">Chave de Acesso</p>
                        <p className="text-xs font-mono text-gray-700 break-all">{invoice.access_key}</p>
                      </div>
                    )}
                    {invoice.authorized_at && (
                      <div>
                        <p className="text-xs text-gray-500">Autorizada em</p>
                        <p className="text-sm">{formatDate(invoice.authorized_at)}</p>
                      </div>
                    )}
                    {invoice.rejection_message && (
                      <div className="mt-2 p-2 bg-red-50 rounded-lg">
                        <p className="text-xs text-red-600">{invoice.rejection_message}</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">
                    {os.status === 'FINALIZADA'
                      ? 'NF-e ainda não gerada'
                      : 'NF-e será gerada ao finalizar a OS'}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Relatórios */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Download className="w-4 h-4 text-gray-400" />
                  Relatórios
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 space-y-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={handleDownloadPdf}
                  disabled={pdfLoading}
                >
                  {pdfLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <FileDown className="w-4 h-4" />
                  )}
                  Baixar PDF da OS
                </Button>
                {os.client?.phone && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={handleWhatsApp}
                    disabled={waLoading}
                  >
                    {waLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <MessageCircle className="w-4 h-4" />
                    )}
                    Enviar WhatsApp
                  </Button>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
