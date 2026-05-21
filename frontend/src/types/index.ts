// ─── Auth ────────────────────────────────────────────────────────────────────
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export type UserRole = 'ADMIN' | 'TECNICO' | 'VIEWER' | 'SUPER_ADMIN';

export interface User {
  id: string;
  tenant_id: string | null;
  email: string;
  full_name: string;
  role: UserRole;
  active: boolean;
  assinatura_url?: string | null;
  created_at?: string;
  last_login_at?: string | null;
}

// ─── Tenant / Oficina ─────────────────────────────────────────────────────────
export interface Tenant {
  id: string;
  name: string;
  document: string;
  email: string;
  phone?: string | null;
  razao_social: string;
  nome_fantasia?: string | null;
  inscricao_estadual?: string | null;
  inscricao_municipal?: string | null;
  regime_tributario: number;
  crt: string;
  municipio?: string | null;
  uf?: string | null;
  cep?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  active: boolean;
  limite_tecnicos: number;
  logo_url?: string | null;
  created_at: string;
}

export interface CreateTenantPayload {
  name: string;
  document: string;
  email: string;
  phone?: string;
  razao_social: string;
  nome_fantasia?: string;
  inscricao_estadual?: string;
  municipio?: string;
  uf?: string;
  cep?: string;
  logradouro?: string;
  numero?: string;
  bairro?: string;
  limite_tecnicos: number;
  regime_tributario?: number;
  crt?: string;
}

export interface UpdateTenantPayload {
  name?: string;
  document?: string;
  email?: string;
  phone?: string;
  razao_social?: string;
  nome_fantasia?: string;
  inscricao_estadual?: string;
  inscricao_municipal?: string;
  municipio?: string;
  uf?: string;
  cep?: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  limite_tecnicos?: number;
}

// ─── Pagination ───────────────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ─── Service Orders ───────────────────────────────────────────────────────────
export type ServiceOrderStatus = 'ABERTA' | 'EM_ANDAMENTO' | 'FINALIZADA' | 'CANCELADA';
export type BudgetStatus = 'RASCUNHO' | 'AGUARDANDO_APROVACAO' | 'APROVADO' | 'RECUSADO';
export type ItemType = 'SERVICO' | 'PECA' | 'DESLOCAMENTO';

export interface ServiceOrderItem {
  id: string;
  item_type: ItemType;
  description: string;
  quantity: number;
  unit_price: number;
  total_price: number;
}

export interface ServiceOrderClient {
  id: string;
  name: string;
  document: string;
  phone?: string | null;
}

export interface ServiceOrderMachine {
  id: string;
  model: string;
  brand: string;
  serial_number: string;
  machine_type: string;
  year?: number | null;
}

export interface ServiceOrder {
  id: string;
  number: string;
  status: ServiceOrderStatus;
  description: string;
  client: ServiceOrderClient;
  machine?: ServiceOrderMachine;
  items: ServiceOrderItem[];
  total_services: number;
  total_parts: number;
  total_displacement: number;
  total_discount: number;
  total_amount: number;
  opened_at: string;
  started_at?: string;
  finished_at?: string;
  expected_delivery_at?: string;
  technician_name?: string;
  technician_notes?: string;
  // Portal do cliente
  public_token?: string | null;
  budget_status?: BudgetStatus;
  budget_sent_at?: string | null;
  budget_approved_at?: string | null;
  budget_rejected_at?: string | null;
  budget_rejection_reason?: string | null;
  client_viewed_at?: string | null;
}

export interface CreateServiceOrderItem {
  item_type: ItemType;
  description: string;
  quantity: number;
  unit_price: number;
}

export interface CreateServiceOrderPayload {
  client_id: string;
  description: string;
  technician_name?: string;
  machine_id?: string;
  items?: CreateServiceOrderItem[];
}

// ─── Clients ─────────────────────────────────────────────────────────────────
export type DocumentType = 'CPF' | 'CNPJ';

export interface Client {
  id: string;
  name: string;
  document: string;
  document_type: DocumentType;
  email?: string | null;
  phone?: string | null;
  phone_secondary?: string | null;
  fazenda?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  municipio?: string | null;
  uf?: string | null;
  cep?: string | null;
  codigo_municipio?: string | null;
  inscricao_estadual?: string | null;
  active: boolean;
}

export interface CreateClientPayload {
  name: string;
  document: string;
  document_type: DocumentType;
  email?: string;
  phone?: string;
  phone_secondary?: string;
  fazenda?: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  municipio?: string;
  uf?: string;
  cep?: string;
  inscricao_estadual?: string;
}

export interface UpdateClientPayload {
  name?: string;
  email?: string;
  phone?: string;
  phone_secondary?: string;
  fazenda?: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  municipio?: string;
  uf?: string;
  cep?: string;
  inscricao_estadual?: string;
  active?: boolean;
}

// ─── Machines ────────────────────────────────────────────────────────────────
export type MachineType =
  | 'Tratores'
  | 'Colheitadeiras'
  | 'Plantadeiras'
  | 'Semeadoras'
  | 'Pulverizadores'
  | 'Outros';

export const MACHINE_TYPES: MachineType[] = [
  'Tratores',
  'Colheitadeiras',
  'Plantadeiras',
  'Semeadoras',
  'Pulverizadores',
  'Outros',
];

export interface MachineClient {
  id: string;
  name: string;
  document: string;
  phone?: string | null;
}

export interface Machine {
  id: string;
  tenant_id: string;
  client_id: string;
  machine_type: MachineType;
  model: string;
  brand: string;
  serial_number: string;
  year?: number | null;
  color?: string | null;
  engine_number?: string | null;
  horsepower?: string | null;
  chassis_number?: string | null;
  notes?: string | null;
  active: boolean;
  placa?: string | null;
  proprietario?: string | null;
  deleted_at?: string | null;
  client?: MachineClient | null;
  created_at: string;
  updated_at: string;
}

export interface CreateMachinePayload {
  client_id: string;
  machine_type: MachineType;
  model: string;
  brand: string;
  serial_number: string;
  year?: number | null;
  color?: string | null;
  engine_number?: string | null;
  horsepower?: string | null;
  chassis_number?: string | null;
  notes?: string | null;
  placa?: string | null;
  proprietario?: string | null;
}

// ─── Stock ────────────────────────────────────────────────────────────────────
export type MovementType = 'ENTRADA' | 'SAIDA' | 'AJUSTE' | 'RESERVA' | 'BAIXA_OS';

export interface StockItem {
  id: string;
  tenant_id: string;
  sku: string;
  description: string;
  ncm_code: string | null;
  unit: string;
  quantity: string; // Decimal as string
  min_quantity: string;
  cost_price: string;
  sale_price: string;
  active: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StockMovement {
  id: string;
  tenant_id: string;
  stock_item_id: string;
  service_order_id: string | null;
  movement_type: MovementType;
  quantity: string;
  quantity_before: string;
  quantity_after: string;
  unit_cost: string;
  reason: string | null;
  reference: string | null;
  created_at: string;
}

export interface StockItemListResponse {
  items: StockItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ─── Financial ────────────────────────────────────────────────────────────────
export type EntryType = 'RECEITA' | 'DESPESA' | 'ESTORNO';

export interface FinancialEntry {
  id: string;
  tenant_id: string;
  service_order_id: string | null;
  entry_type: EntryType;
  amount: string; // Decimal as string
  description: string;
  category: string | null;
  reference_date: string;
  idempotency_key: string | null;
  notes: string | null;
  created_at: string;
}

export interface FinancialEntryListResponse {
  items: FinancialEntry[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface FinancialSummary {
  total_receitas: string;
  total_despesas: string;
  saldo: string;
  date_from: string | null;
  date_to: string | null;
}

// ─── Invoices ─────────────────────────────────────────────────────────────────
export type InvoiceStatus = 'PENDENTE' | 'PROCESSANDO' | 'AUTORIZADA' | 'REJEITADA' | 'ERRO';

export interface Invoice {
  id: string;
  service_order_id: string;
  status: InvoiceStatus;
  number?: string;
  access_key?: string;
  protocol_number?: string;
  total_amount: number;
  issued_at?: string;
  authorized_at?: string;
  rejected_at?: string;
  rejection_code?: string;
  rejection_message?: string;
  retry_count: number;
}
