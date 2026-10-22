// Typed client for the Boster backend. Types mirror backend/app/schemas.py.

export type VerificationStatus =
  | 'verified'
  | 'extracted'
  | 'user_entered'
  | 'calculated'
  | 'estimated'
  | 'missing'
  | 'conflicting'

export type ConcernLevel = 'low' | 'moderate' | 'high' | 'insufficient_information'

export interface SourceRef {
  observation_id: number
  value: number
  status: VerificationStatus
  method: string
  document_id: number | null
  document_name: string | null
  page: number | null
  printed_label: string | null
  note: string | null
}

export interface ReportedValue {
  value: number | null
  status: VerificationStatus
  sources: SourceRef[]
  note: string | null
}

export interface CalculatedValue {
  value: number | null
  formula: string
  inputs: Record<string, number>
  missing_inputs: string[]
  note: string | null
}

export interface YearValue {
  fiscal_year: number
  reported: ReportedValue | null
  calculated: CalculatedValue | null
  display_value: number | null
  display_status: VerificationStatus
  display_origin: 'reported' | 'calculated' | null
  warning: string | null
}

export interface MetricSeries {
  key: string
  label: string
  unit: string
  category: 'base_figure' | 'area' | 'key_figure'
  description: string
  area_basis: string | null
  values: YearValue[]
}

export interface RiskIndicator {
  key: string
  label: string
  value: number | null
  unit: string | null
  fiscal_year: number | null
  level: ConcernLevel
  level_label: string
  rationale: string
  rule: string
}

export interface RiskAssessment {
  fiscal_year: number | null
  overall_level: ConcernLevel
  overall_label: string
  overall_rule: string
  indicators: RiskIndicator[]
  disclaimer: string
}

export interface DocumentSummary {
  id: number
  cooperative_id: number | null
  original_filename: string
  document_url: string | null
  document_type: string
  reporting_year: number | null
  fiscal_period_start: string | null
  fiscal_period_end: string | null
  page_count: number
  extraction_status: 'succeeded' | 'partial' | 'needs_ocr' | 'failed'
  extraction_messages: string[]
  uploaded_at: string
}

export interface Finding {
  topic: string
  document_id: number
  document_name: string
  page: number
  excerpt: string
}

export interface CooperativeInfo {
  id: number
  name: string
  organisation_number: string | null
  land_tenure: 'owned' | 'leasehold' | null
  land_tenure_source: string | null
  created_at: string
  updated_at: string
}

export interface CooperativeOverview {
  cooperative: CooperativeInfo
  fiscal_years: number[]
  latest_fiscal_year: number | null
  metrics: MetricSeries[]
  risk: RiskAssessment
  completeness: { fiscal_year: number | null; available: string[]; missing: string[] }
  documents: DocumentSummary[]
  findings: Finding[]
}

export interface CooperativeListItem {
  id: number
  name: string
  organisation_number: string | null
  latest_fiscal_year: number | null
  document_count: number
  overall_level: ConcernLevel
  overall_label: string
  updated_at: string
}

export interface MetricDefinition {
  key: string
  label: string
  unit: string
  category: string
  description: string
  area_basis: string | null
}

export interface ComparedCooperative {
  id: number
  name: string
  organisation_number: string | null
  land_tenure: 'owned' | 'leasehold' | null
  fiscal_year: number | null
  period_months: number | null
  overall_level: ConcernLevel
  overall_label: string
  completeness_available: number
  completeness_total: number
}

export interface ComparisonCell {
  cooperative_id: number
  fiscal_year: number | null
  value: number | null
  status: VerificationStatus
  level: ConcernLevel | null
  level_label: string | null
  warning: string | null
}

export interface HistoryPoint {
  fiscal_year: number
  value: number | null
  status: VerificationStatus
}

export interface ComparisonRow {
  key: string
  label: string
  unit: string
  description: string
  area_basis: string | null
  is_default: boolean
  cells: ComparisonCell[]
  history: Record<string, HistoryPoint[]>
  note: string | null
}

export interface CooperativeComparison {
  cooperatives: ComparedCooperative[]
  rows: ComparisonRow[]
  warnings: string[]
}

export const MAX_COMPARED_COOPERATIVES = 4

export type PropertyFieldValue = string | number | boolean | null

export interface PropertyField {
  key: string
  label: string
  value: PropertyFieldValue
  kind: 'text' | 'number' | 'integer' | 'boolean' | 'date' | 'longtext'
  unit: string | null
  status: VerificationStatus
  method: string | null
  excerpt: string | null
  note: string | null
}

export interface DerivedValue {
  key: string
  label: string
  value: number | null
  unit: string
  formula: string
  inputs: Record<string, string>
  missing_inputs: string[]
  note: string | null
}

export interface LinkedCooperative {
  id: number
  name: string
  organisation_number: string | null
  fiscal_year: number | null
  overall_level: ConcernLevel
  overall_label: string
  land_tenure: 'owned' | 'leasehold' | null
  indicators: RiskIndicator[]
  completeness_available: number
  completeness_total: number
}

export interface PropertyOverview {
  id: number
  title: string | null
  source_url: string | null
  source_name: string | null
  retrieval_status: 'fetched' | 'pasted' | 'fetch_failed' | 'manual'
  retrieval_message: string | null
  retrieved_at: string | null
  created_at: string
  updated_at: string
  fields: PropertyField[]
  description: PropertyField
  derived: DerivedValue[]
  cooperative: LinkedCooperative | null
  cooperative_suggestions: CooperativeListItem[]
  missing: string[]
  has_listing_text: boolean
}

export interface PropertyListItem {
  id: number
  title: string | null
  address: string | null
  source_name: string | null
  asking_price: number | null
  living_area: number | null
  rooms: number | null
  monthly_fee: number | null
  cooperative_id: number | null
  cooperative_name: string | null
  cooperative_overall_level: ConcernLevel | null
  cooperative_overall_label: string | null
  retrieval_status: string
  updated_at: string
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError('Kunde inte nå servern. Kontrollera att backend körs.')
  }
  if (!response.ok) {
    let message = `Något gick fel (HTTP ${response.status}).`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = 'Ogiltig uppgift: ' + body.detail.map((d: { msg: string }) => d.msg).join(', ')
    } catch {
      // Keep the generic message.
    }
    throw new ApiError(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const api = {
  listCooperatives: () => request<CooperativeListItem[]>('/api/cooperatives'),
  getCooperative: (id: number) => request<CooperativeOverview>(`/api/cooperatives/${id}`),
  updateCooperative: (id: number, changes: Partial<Pick<CooperativeInfo, 'name' | 'organisation_number' | 'land_tenure'>>) =>
    request<CooperativeOverview>(`/api/cooperatives/${id}`, json('PATCH', changes)),
  deleteCooperative: (id: number) => request<void>(`/api/cooperatives/${id}`, { method: 'DELETE' }),
  addObservation: (id: number, observation: { metric_key: string; fiscal_year: number; value: number; note?: string }) =>
    request<CooperativeOverview>(`/api/cooperatives/${id}/observations`, json('POST', observation)),
  verifyObservation: (observationId: number) =>
    request<CooperativeOverview>(`/api/observations/${observationId}/verify`, { method: 'POST' }),
  deleteObservation: (observationId: number) =>
    request<CooperativeOverview>(`/api/observations/${observationId}`, { method: 'DELETE' }),
  compareCooperatives: (ids: number[]) =>
    request<CooperativeComparison>(`/api/comparisons/cooperatives?ids=${ids.join(',')}`),
  listProperties: () => request<PropertyListItem[]>('/api/properties'),
  getProperty: (id: number) => request<PropertyOverview>(`/api/properties/${id}`),
  addPropertyFromUrl: (url: string) => request<PropertyOverview>('/api/properties/from-url', json('POST', { url })),
  addPropertyFromText: (text: string, url?: string) =>
    request<PropertyOverview>('/api/properties/from-text', json('POST', { text, url: url || undefined })),
  refreshProperty: (id: number) => request<PropertyOverview>(`/api/properties/${id}/refresh`, { method: 'POST' }),
  addPropertyText: (id: number, text: string) =>
    request<PropertyOverview>(`/api/properties/${id}/text`, json('POST', { text })),
  updateProperty: (id: number, changes: Record<string, PropertyFieldValue>) =>
    request<PropertyOverview>(`/api/properties/${id}`, json('PATCH', changes)),
  verifyPropertyField: (id: number, field: string) =>
    request<PropertyOverview>(`/api/properties/${id}/fields/${field}/verify`, { method: 'POST' }),
  linkPropertyCooperative: (id: number, cooperativeId: number | null) =>
    request<PropertyOverview>(`/api/properties/${id}/cooperative`, json('PUT', { cooperative_id: cooperativeId })),
  deleteProperty: (id: number) => request<void>(`/api/properties/${id}`, { method: 'DELETE' }),
  listMetrics: () => request<MetricDefinition[]>('/api/metrics'),
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentSummary>('/api/documents/upload', { method: 'POST', body: form })
  },
  addDocumentFromUrl: (url: string) => request<DocumentSummary>('/api/documents/from-url', json('POST', { url })),
  moveDocument: (documentId: number, cooperativeId: number) =>
    request<DocumentSummary>(`/api/documents/${documentId}`, json('PATCH', { cooperative_id: cooperativeId })),
  deleteDocument: (documentId: number) => request<void>(`/api/documents/${documentId}`, { method: 'DELETE' }),
  documentFileUrl: (documentId: number, page?: number | null) =>
    `/api/documents/${documentId}/file${page ? `#page=${page}` : ''}`,
}
