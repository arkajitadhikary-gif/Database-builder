import { invoke } from "@tauri-apps/api/core";

export type HealthStatus = "READY" | "WARNING" | "NOT CONFIGURED" | "ERROR";

export interface HealthComponent {
  name: string;
  status: HealthStatus;
  detail: string;
}

export interface SetupResponse {
  components: HealthComponent[];
}

export interface Batch {
  id: string;
  state: string;
  requested_paths: string[];
  recursive: boolean;
  created_at: string;
  item_count: number;
  completed_count: number;
  failed_count: number;
}

export interface BatchItem {
  id: string;
  path: string;
  state: string;
  attempts: number;
  locked_at: string | null;
  last_error: string | null;
  document_id: string | null;
}

export interface DocumentRecord {
  id: string;
  filename: string;
  sha256: string;
  normalized_text_hash: string | null;
  byte_size: number;
  page_count: number;
  document_type: string;
  title: string | null;
  document_date: string | null;
  missing_source: boolean;
  source_path: string;
  created_at: string;
}

export interface PageRecord {
  id: string;
  page_number: number;
  raw_text: string;
  normalized_text: string;
  extraction_method: string;
  text_start_offset: number | null;
  text_end_offset: number | null;
  ocr_engine: string | null;
  ocr_confidence: number | null;
  warnings: string[];
}

export interface ReferenceRecord {
  id: string;
  source_text: string;
  reference_type: string;
  normalized_key: string | null;
  resolution_status: string;
  target_document_id: string | null;
  page_start: number;
  page_end: number;
}

export interface LegalSectionRecord {
  label: string;
  heading: string | null;
  text: string;
  page_start: number;
  page_end: number;
}

export interface ActStructure {
  name: string | null;
  year: number | null;
  short_title: string | null;
  sections: LegalSectionRecord[];
}

export interface JudgmentParagraph {
  official_number: string | null;
  internal_sequence: number;
  text: string;
  page_start: number;
  page_end: number;
}

export interface JudgmentStructure {
  case_title: string | null;
  court: string | null;
  case_number: string | null;
  decision_date: string | null;
  coram_text: string | null;
  paragraphs: JudgmentParagraph[];
}

export interface DocumentStructure {
  document_id: string;
  act: ActStructure | null;
  judgment: JudgmentStructure | null;
  references: ReferenceRecord[];
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  text: string;
  document_type: string;
  source_path: string;
  page_start: number;
  page_end: number;
  section_label: string | null;
  paragraph_number: string | null;
  lexical_score: number | null;
  semantic_score: number | null;
  fused_score: number;
}

export interface SearchResponse {
  mode: string;
  hits: SearchHit[];
  embedding_status: string;
}

export interface EmbeddingBackfillResponse {
  requested: number;
  embedded: number;
  provider: string;
  model: string;
  dimension: number;
}

export interface DatabaseTable {
  key: string;
  label: string;
  count: number;
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface DatabaseOverview {
  tables: DatabaseTable[];
}

export interface DatabaseTablePage extends DatabaseTable {
  offset: number;
  limit: number;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8765/api/v1";
let sessionToken: string | null = null;
let sessionTokenPromise: Promise<void> | null = null;

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function loadSessionToken(): Promise<void> {
  if (sessionTokenPromise) return sessionTokenPromise;
  sessionTokenPromise = invoke<string>("backend_session_token")
    .then((token) => { sessionToken = token; })
    .catch(() => { sessionToken = null; });
  return sessionTokenPromise;
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  await loadSessionToken();
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const isFormDataBody = typeof FormData !== "undefined" && init?.body instanceof FormData;
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init?.signal ?? controller.signal,
      headers: {
        ...(isFormDataBody ? {} : { "Content-Type": "application/json" }),
        ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || `${response.status} ${response.statusText}`);
    }
    return (await response.json()) as T;
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s: ${path}`);
    }
    throw reason;
  } finally {
    window.clearTimeout(timer);
  }
}

export const api = {
  getSetup: () => request<SetupResponse>("/setup"),
  getBatches: () => request<Batch[]>("/batches"),
  getDocuments: (documentType?: string) =>
    request<DocumentRecord[]>(`/documents?limit=100${documentType ? `&document_type=${encodeURIComponent(documentType)}` : ""}`),
  getBatchItems: (id: string) => request<BatchItem[]>(`/batches/${id}/items`),
  getPages: (id: string) => request<PageRecord[]>(`/documents/${id}/pages`),
  getStructure: (id: string) => request<DocumentStructure>(`/documents/${id}/structure`),
  getDatabaseOverview: () => request<DatabaseOverview>("/database/overview", undefined, 30000),
  getDatabaseTable: (key: string, offset = 0, limit = 200) =>
    request<DatabaseTablePage>(`/database/tables/${encodeURIComponent(key)}?offset=${offset}&limit=${limit}`, undefined, 30000),
  createBatch: (paths: string[], recursive: boolean) =>
    request<Batch>("/batches", {
      method: "POST",
      body: JSON.stringify({ paths, recursive }),
    }),
  pauseBatch: (id: string) => request<Batch>(`/batches/${id}/pause`, { method: "POST" }),
  resumeBatch: (id: string) => request<Batch>(`/batches/${id}/resume`, { method: "POST" }),
  cancelBatch: (id: string) => request<Batch>(`/batches/${id}/cancel`, { method: "POST" }),
  retryBatch: (id: string) => request<Batch>(`/batches/${id}/retry`, { method: "POST" }),
  createUploadBatch: (files: File[], recursive: boolean) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file, file.name));
    formData.append("recursive", String(recursive));
    return request<Batch>("/batches/upload", {
      method: "POST",
      body: formData,
    }, 120000);
  },
  backfillEmbeddings: (limit = 100) =>
    request<EmbeddingBackfillResponse>("/embeddings/backfill", {
      method: "POST",
      body: JSON.stringify({ limit }),
    }, 120000),
  search: (query: string, mode: "lexical" | "semantic" | "hybrid") =>
    request<SearchResponse>("/search", {
      method: "POST",
      body: JSON.stringify({ query, mode, limit: 30 }),
    }, mode === "lexical" ? 15000 : 120000),
};

export { API_BASE };
