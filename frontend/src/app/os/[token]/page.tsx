'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import axios from 'axios';
import {
  CheckCircle2, XCircle, Clock, Wrench, AlertTriangle,
  ChevronRight, Loader2, Phone, MapPin, Car,
} from 'lucide-react';

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface OSItem {
  id: string;
  item_type: 'SERVICO' | 'PECA' | 'DESLOCAMENTO';
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
  total_price: string;
}

interface PublicOS {
  number: number;
  status: string;
  budget_status: string;
  description: string | null;
  diagnosis: string | null;
  technician_name: string | null;
  opened_at: string;
  expected_delivery_at: string | null;
  budget_sent_at: string | null;
  budget_approved_at: string | null;
  budget_rejected_at: string | null;
  budget_rejection_reason: string | null;
  client_viewed_at: string | null;
  total_services: string;
  total_parts: string;
  total_displacement: string;
  total_discount: string;
  total_amount: string;
  items: OSItem[];
  client_name: string | null;
  machine_info: string | null;
  workshop_name: string | null;
  workshop_phone: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';

const fmt = (val: string | number) =>
  Number(val).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const fmtDate = (d: string | null) =>
  d ? new Date(d).toLocaleDateString('pt-BR') : '—';

const statusLabel: Record<string, string> = {
  ABERTA: 'Aberta',
  EM_ANDAMENTO: 'Em andamento',
  FINALIZADA: 'Finalizada',
};

const budgetLabel: Record<string, { label: string; color: string }> = {
  RASCUNHO: { label: 'Orçamento não enviado', color: 'text-gray-500' },
  AGUARDANDO_APROVACAO: { label: 'Aguardando sua aprovação', color: 'text-amber-600' },
  APROVADO: { label: 'Orçamento aprovado', color: 'text-emerald-600' },
  RECUSADO: { label: 'Orçamento recusado', color: 'text-red-600' },
};

const itemTypeLabel: Record<string, string> = {
  SERVICO: 'Serviço',
  PECA: 'Peça',
  DESLOCAMENTO: 'Deslocamento',
};

// ── Componente principal ──────────────────────────────────────────────────────

export default function ClientPortalPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [os, setOs] = useState<PublicOS | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<'idle' | 'approving' | 'rejecting' | 'done'>('idle');
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectForm, setShowRejectForm] = useState(false);

  // Assinatura digital
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const isDrawingRef = useRef(false);
  const [hasSignature, setHasSignature] = useState(false);
  const [signerName, setSignerName] = useState('');
  const [signerDocument, setSignerDocument] = useState('');

  const getPos = (e: React.MouseEvent | React.TouchEvent, canvas: HTMLCanvasElement) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    if ('touches' in e) {
      const touch = e.touches[0];
      return { x: (touch.clientX - rect.left) * scaleX, y: (touch.clientY - rect.top) * scaleY };
    }
    return { x: ((e as React.MouseEvent).clientX - rect.left) * scaleX, y: ((e as React.MouseEvent).clientY - rect.top) * scaleY };
  };

  const startDraw = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    isDrawingRef.current = true;
    const { x, y } = getPos(e, canvas);
    ctx.beginPath(); ctx.moveTo(x, y);
  };

  const draw = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    if (!isDrawingRef.current) return;
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    const { x, y } = getPos(e, canvas);
    ctx.lineTo(x, y);
    ctx.strokeStyle = '#1e293b'; ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.stroke();
    setHasSignature(true);
  };

  const endDraw = () => { isDrawingRef.current = false; };

  const clearCanvas = () => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setHasSignature(false);
  };

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`${API}/public/os/${token}`);
        setOs(data);
      } catch {
        setError('Ordem de serviço não encontrada ou link inválido.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token]);

  const handleApprove = async () => {
    if (!signerName.trim()) { alert('Por favor, informe seu nome completo.'); return; }
    if (!hasSignature) { alert('Por favor, assine no campo de assinatura.'); return; }

    const canvas = canvasRef.current;
    const signatureBase64 = canvas ? canvas.toDataURL('image/png') : null;

    setAction('approving');
    try {
      const { data } = await axios.post(`${API}/public/os/${token}/approve`, {
        signer_name: signerName.trim(),
        signer_document: signerDocument.trim() || null,
        signature: signatureBase64,
      });
      setOs(data);
      setAction('done');
    } catch {
      setAction('idle');
      alert('Erro ao aprovar. Tente novamente.');
    }
  };

  const handleReject = async () => {
    setAction('rejecting');
    try {
      const { data } = await axios.post(`${API}/public/os/${token}/reject`, {
        reason: rejectReason || null,
      });
      setOs(data);
      setAction('done');
      setShowRejectForm(false);
    } catch {
      setAction('idle');
      alert('Erro ao recusar. Tente novamente.');
    }
  };

  // ── Estados de loading / erro ─────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (error || !os) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4 px-4 text-center">
        <AlertTriangle className="w-12 h-12 text-amber-500" />
        <h1 className="text-xl font-semibold text-gray-800">Link inválido</h1>
        <p className="text-gray-500 max-w-sm">{error}</p>
      </div>
    );
  }

  const budget = budgetLabel[os.budget_status] ?? budgetLabel.RASCUNHO;
  const isAwaiting = os.budget_status === 'AGUARDANDO_APROVACAO';
  const isApproved = os.budget_status === 'APROVADO';
  const isRejected = os.budget_status === 'RECUSADO';

  // Usa o total do banco; se for 0 (OS sem recálculo), soma os itens diretamente
  const computedTotal = Number(os.total_amount) > 0
    ? Number(os.total_amount)
    : os.items.reduce((sum, item) => sum + Number(item.total_price), 0);
  const computedDiscount = Number(os.total_discount) || 0;
  const displayTotal = computedTotal > 0 ? computedTotal : (
    os.items.reduce((sum, i) => sum + Number(i.total_price), 0) - computedDiscount
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ── Header ── */}
      <header className="bg-white border-b border-gray-200 px-4 py-4">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide">Ordem de Serviço</p>
            <h1 className="text-2xl font-bold text-gray-900">OS #{os.number}</h1>
          </div>
          {os.workshop_name && (
            <div className="text-right">
              <p className="text-sm font-semibold text-gray-700">{os.workshop_name}</p>
              {os.workshop_phone && (
                <a
                  href={`tel:${os.workshop_phone}`}
                  className="text-xs text-indigo-600 flex items-center gap-1 justify-end mt-0.5"
                >
                  <Phone className="w-3 h-3" /> {os.workshop_phone}
                </a>
              )}
            </div>
          )}
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-6 space-y-5">

        {/* ── Status da OS ── */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-indigo-50">
              <Wrench className="w-5 h-5 text-indigo-600" />
            </div>
            <div className="flex-1">
              <p className="text-sm text-gray-500">Status do serviço</p>
              <p className="text-lg font-semibold text-gray-900">
                {statusLabel[os.status] ?? os.status}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-gray-400">Data de abertura</p>
                  <p className="font-medium">{fmtDate(os.opened_at)}</p>
                </div>
                {os.expected_delivery_at && (
                  <div>
                    <p className="text-gray-400">Previsão de entrega</p>
                    <p className="font-medium">{fmtDate(os.expected_delivery_at)}</p>
                  </div>
                )}
                {os.client_name && (
                  <div>
                    <p className="text-gray-400">Cliente</p>
                    <p className="font-medium">{os.client_name}</p>
                  </div>
                )}
                {os.machine_info && (
                  <div>
                    <p className="text-gray-400">Máquina / Veículo</p>
                    <p className="font-medium flex items-center gap-1">
                      <Car className="w-3 h-3 text-gray-400" /> {os.machine_info}
                    </p>
                  </div>
                )}
              </div>
              {os.description && (
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <p className="text-gray-400 text-sm">Descrição do problema</p>
                  <p className="text-sm text-gray-700 mt-1">{os.description}</p>
                </div>
              )}
              {os.diagnosis && (
                <div className="mt-2">
                  <p className="text-gray-400 text-sm">Diagnóstico</p>
                  <p className="text-sm text-gray-700 mt-1">{os.diagnosis}</p>
                </div>
              )}
              {os.technician_name && (
                <p className="text-xs text-gray-400 mt-3">
                  Técnico responsável: <span className="font-medium text-gray-600">{os.technician_name}</span>
                </p>
              )}
            </div>
          </div>
        </div>

        {/* ── Orçamento ── */}
        {os.items.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <h2 className="font-semibold text-gray-800">Orçamento</h2>
              <span className={`text-sm font-medium ${budget.color}`}>
                {budget.label}
              </span>
            </div>

            {/* Itens */}
            <div className="divide-y divide-gray-50">
              {os.items.map((item) => (
                <div key={item.id} className="px-5 py-3 flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{item.description}</p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {itemTypeLabel[item.item_type]} ·{' '}
                      {Number(item.quantity).toLocaleString('pt-BR')} × {fmt(item.unit_price)}
                    </p>
                  </div>
                  <p className="text-sm font-semibold text-gray-900 whitespace-nowrap">
                    {fmt(item.total_price)}
                  </p>
                </div>
              ))}
            </div>

            {/* Totais */}
            <div className="px-5 py-4 bg-gray-50 border-t border-gray-100 space-y-1 text-sm">
              {Number(os.total_services) > 0 && (
                <div className="flex justify-between text-gray-600">
                  <span>Serviços</span><span>{fmt(os.total_services)}</span>
                </div>
              )}
              {Number(os.total_parts) > 0 && (
                <div className="flex justify-between text-gray-600">
                  <span>Peças</span><span>{fmt(os.total_parts)}</span>
                </div>
              )}
              {Number(os.total_displacement) > 0 && (
                <div className="flex justify-between text-gray-600">
                  <span>Deslocamento</span><span>{fmt(os.total_displacement)}</span>
                </div>
              )}
              {Number(os.total_discount) > 0 && (
                <div className="flex justify-between text-emerald-600">
                  <span>Desconto</span><span>- {fmt(os.total_discount)}</span>
                </div>
              )}
              <div className="flex justify-between font-bold text-gray-900 text-base pt-2 border-t border-gray-200 mt-2">
                <span>Total</span><span>{fmt(displayTotal)}</span>
              </div>
            </div>
          </div>
        )}

        {/* ── Ação do cliente (aprovar / recusar) ── */}
        {isAwaiting && action !== 'done' && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-5">
            <div className="flex items-start gap-3">
              <Clock className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold text-amber-800">Aprovação + Assinatura Digital</p>
                <p className="text-sm text-amber-700 mt-0.5">
                  Analise o orçamento acima, preencha seus dados e assine para confirmar.
                </p>
              </div>
            </div>

            {!showRejectForm ? (
              <div className="space-y-4">
                {/* Dados do assinante */}
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">
                      Nome completo <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={signerName}
                      onChange={e => setSignerName(e.target.value)}
                      placeholder="Seu nome completo"
                      className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400 outline-none bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">
                      CPF / CNPJ <span className="text-gray-400 font-normal">(opcional)</span>
                    </label>
                    <input
                      type="text"
                      value={signerDocument}
                      onChange={e => setSignerDocument(e.target.value)}
                      placeholder="000.000.000-00"
                      className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400 outline-none bg-white"
                    />
                  </div>
                </div>

                {/* Canvas de assinatura */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs font-semibold text-gray-600">
                      Assinatura <span className="text-red-500">*</span>
                    </label>
                    <button
                      onClick={clearCanvas}
                      className="text-xs text-gray-400 hover:text-gray-600 underline"
                    >
                      Limpar
                    </button>
                  </div>
                  <div className="relative border-2 border-dashed border-gray-300 rounded-xl bg-white overflow-hidden"
                    style={{ touchAction: 'none' }}>
                    <canvas
                      ref={canvasRef}
                      width={700}
                      height={160}
                      className="w-full"
                      style={{ cursor: 'crosshair', display: 'block' }}
                      onMouseDown={startDraw}
                      onMouseMove={draw}
                      onMouseUp={endDraw}
                      onMouseLeave={endDraw}
                      onTouchStart={startDraw}
                      onTouchMove={draw}
                      onTouchEnd={endDraw}
                    />
                    {!hasSignature && (
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <p className="text-gray-300 text-sm select-none">
                          ✍️ Assine aqui com o dedo ou mouse
                        </p>
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    Sua assinatura será registrada com data, hora e IP para validade jurídica.
                  </p>
                </div>

                {/* Botões */}
                <button
                  onClick={handleApprove}
                  disabled={action === 'approving' || !signerName.trim() || !hasSignature}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
                >
                  {action === 'approving' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4" />
                  )}
                  Assinar e Aprovar — {fmt(displayTotal)}
                </button>
                <button
                  onClick={() => setShowRejectForm(true)}
                  className="w-full border border-red-300 text-red-600 hover:bg-red-50 font-medium py-2.5 rounded-lg flex items-center justify-center gap-2 transition"
                >
                  <XCircle className="w-4 h-4" />
                  Recusar orçamento
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <label className="block text-sm font-medium text-gray-700">
                  Motivo da recusa (opcional)
                </label>
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Ex: valor acima do esperado, vou buscar outro orçamento..."
                  rows={3}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-red-300 focus:border-red-400 outline-none resize-none bg-white"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleReject}
                    disabled={action === 'rejecting'}
                    className="flex-1 bg-red-600 hover:bg-red-700 text-white font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 disabled:opacity-60 transition"
                  >
                    {action === 'rejecting' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Confirmar recusa'}
                  </button>
                  <button
                    onClick={() => setShowRejectForm(false)}
                    className="px-4 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50 transition"
                  >
                    Voltar
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Confirmação: aprovado ── */}
        {isApproved && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 flex items-start gap-3">
            <CheckCircle2 className="w-6 h-6 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-emerald-800">Orçamento aprovado!</p>
              <p className="text-sm text-emerald-700 mt-0.5">
                Aprovado em {fmtDate(os.budget_approved_at)}. A oficina já foi notificada e dará início ao serviço em breve.
              </p>
            </div>
          </div>
        )}

        {/* ── Confirmação: recusado ── */}
        {isRejected && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-5 flex items-start gap-3">
            <XCircle className="w-6 h-6 text-red-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-red-800">Orçamento recusado</p>
              <p className="text-sm text-red-700 mt-0.5">
                Recusado em {fmtDate(os.budget_rejected_at)}.
                {os.budget_rejection_reason && (
                  <> Motivo: <em>{os.budget_rejection_reason}</em>.</>
                )}{' '}
                Entre em contato com a oficina para mais informações.
              </p>
            </div>
          </div>
        )}

        {/* Rodapé */}
        <p className="text-center text-xs text-gray-400 pb-6">
          AutoMaster — Sistema de Gestão de Oficinas Agrícolas
        </p>
      </main>
    </div>
  );
}
