import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  Activity,
  Archive,
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Database,
  FileSearch,
  FolderOpen,
  Gauge,
  GitBranch,
  HardDrive,
  Library,
  LoaderCircle,
  Moon,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  ShieldCheck,
  Square,
  Sun,
  UploadCloud,
  XCircle,
} from "lucide-react";
import {
  api,
  type Batch,
  type BatchItem,
  type DocumentRecord,
  type DocumentStructure,
  type HealthComponent,
  type PageRecord,
  type SearchResponse,
  isTauriRuntime,
} from "./lib/api";

type View =
  | "overview"
  | "import"
  | "jobs"
  | "library"
  | "search"
  | "acts"
  | "judgments"
  | "failures"
  | "database"
  | "settings";
type SearchMode = "lexical" | "semantic" | "hybrid";

type NavigationItem = { id: View; label: string; icon: typeof Activity };

const navigation: NavigationItem[] = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "import", label: "Import documents", icon: UploadCloud },
  { id: "jobs", label: "Ingestion jobs", icon: Activity },
  { id: "library", label: "Document library", icon: Library },
  { id: "search", label: "Legal search", icon: Search },
  { id: "acts", label: "Bare Acts", icon: BookOpen },
  { id: "judgments", label: "Judgments", icon: FileSearch },
  { id: "failures", label: "Failures", icon: XCircle },
  { id: "database", label: "Database", icon: Database },
  { id: "settings", label: "Settings", icon: Settings },
];

function statusClass(status: string): string {
  return status.toLowerCase().replace(/\s+/g, "-");
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function App() {
  const [view, setView] = useState<View>("overview");
  const [darkMode, setDarkMode] = useState(false);
  const [setup, setSetup] = useState<HealthComponent[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<DocumentRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [setupResult, batchResult, documentResult] = await Promise.all([
        api.getSetup(),
        api.getBatches(),
        api.getDocuments(),
      ]);
      setSetup(setupResult.components);
      setBatches(batchResult);
      setDocuments(documentResult);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Backend unavailable");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const counts = useMemo(() => {
    const completed = batches.filter((batch) => batch.state === "COMPLETED").length;
    const active = batches.filter(
      (batch) => !["COMPLETED", "CANCELLED", "FAILED_RETRYABLE", "FAILED_TERMINAL"].includes(batch.state),
    ).length;
    return { completed, active, documents: documents.length };
  }, [batches, documents.length]);

  return (
    <div className={darkMode ? "app dark" : "app"}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><GitBranch size={19} strokeWidth={2.5} /></div>
          <div><strong>Judicore</strong><span>Legal data builder</span></div>
        </div>
        <div className="workspace-label">Workspace</div>
        <nav className="nav-list" aria-label="Primary navigation">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button key={id} className={view === id ? "nav-item active" : "nav-item"} onClick={() => setView(id)}>
              <Icon size={17} /><span>{label}</span>
              {id === "failures" && batches.some((batch) => batch.state.startsWith("FAILED")) && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="secure-note"><ShieldCheck size={16} /><span>Local-first<br /><small>PostgreSQL is source of truth</small></span></div>
          <button className="theme-toggle" onClick={() => setDarkMode((value) => !value)}>
            {darkMode ? <Sun size={15} /> : <Moon size={15} />} {darkMode ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div><span className="eyebrow">Judicore / {navigation.find((item) => item.id === view)?.label}</span><h1>{pageTitle(view)}</h1></div>
          <div className="topbar-actions">
            <div className={setup.length > 0 && setup.every((item) => ["READY", "WARNING"].includes(item.status)) ? "connection-pill ready" : "connection-pill"}>
              <span className="connection-dot" /> {setup.length === 0 ? "Checking backend" : "System state"}
            </div>
            <button className="icon-button" onClick={() => void refresh()} aria-label="Refresh data" title="Refresh data"><RefreshCw size={17} className={refreshing ? "spin" : ""} /></button>
          </div>
        </header>
        {error && <div className="error-banner"><XCircle size={17} /><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button></div>}
        {view === "overview" && <Overview setup={setup} counts={counts} batches={batches} documents={documents} onNavigate={setView} onSelectDocument={setSelectedDocument} />}
        {view === "import" && <ImportView onCreated={refresh} />}
        {view === "jobs" && <JobsView batches={batches} onChanged={refresh} />}
        {view === "library" && <LibraryView documents={documents} onSelectDocument={setSelectedDocument} />}
        {view === "search" && <SearchView />}
        {view === "acts" && <LibraryView documents={documents.filter((document) => ["BARE_ACT", "RULE", "REGULATION"].includes(document.document_type))} emptyMessage="No legislation documents have been ingested yet." onSelectDocument={setSelectedDocument} />}
        {view === "judgments" && <LibraryView documents={documents.filter((document) => document.document_type.includes("JUDGMENT") || document.document_type === "TRIBUNAL_DECISION")} emptyMessage="No judgment documents have been ingested yet." onSelectDocument={setSelectedDocument} />}
        {view === "failures" && <FailureView batches={batches} />}
        {view === "database" && <DatabaseView setup={setup} documents={documents} />}
        {view === "settings" && <SettingsView setup={setup} />}
      </main>
      {selectedDocument && <DocumentInspector document={selectedDocument} onClose={() => setSelectedDocument(null)} />}
    </div>
  );
}

function pageTitle(view: View): string {
  return navigation.find((item) => item.id === view)?.label ?? "Overview";
}

function Overview({ setup, counts, batches, documents, onNavigate, onSelectDocument }: { setup: HealthComponent[]; counts: { completed: number; active: number; documents: number }; batches: Batch[]; documents: DocumentRecord[]; onNavigate: (view: View) => void; onSelectDocument: (document: DocumentRecord) => void }) {
  const latestBatch = batches[0];
  return <>
    <section className="hero-row">
      <div><span className="hero-kicker">Evidence-backed ingestion</span><h2>Build a legal corpus you can trust.</h2><p>Import source PDFs, preserve page-level provenance, and make every indexed passage traceable to the original file.</p><button className="primary-button" onClick={() => onNavigate("import")}><Plus size={17} /> Start an import</button></div>
      <div className="hero-illustration"><div className="orb orb-one" /><div className="orb orb-two" /><Archive size={80} strokeWidth={1.1} /></div>
    </section>
    <section className="metrics-grid">
      <MetricCard label="Documents" value={String(counts.documents)} detail="Canonical records" icon={Library} />
      <MetricCard label="Active jobs" value={String(counts.active)} detail="Durable work queues" icon={Activity} />
      <MetricCard label="Completed batches" value={String(counts.completed)} detail="Persisted outcomes" icon={CheckCircle2} />
      <MetricCard label="System checks" value={setup.length ? `${setup.filter((item) => item.status === "READY").length}/${setup.length}` : "—"} detail="Actual readiness" icon={ShieldCheck} />
    </section>
    <section className="content-grid">
      <div className="panel large-panel"><PanelHeader title="System readiness" actionLabel="Open database" onAction={() => onNavigate("database")} /><div className="health-list">{setup.length === 0 ? <EmptyState text="Waiting for the backend health response." /> : setup.map((item) => <HealthRow key={item.name} item={item} />)}</div></div>
      <div className="panel"><PanelHeader title="Latest import" actionLabel="View jobs" onAction={() => onNavigate("jobs")} />{latestBatch ? <div className="latest-job"><div className="job-status-icon"><Activity size={20} /></div><div><strong>{latestBatch.item_count} discovered file{latestBatch.item_count === 1 ? "" : "s"}</strong><span>{latestBatch.completed_count} complete · {latestBatch.failed_count} failed</span></div><StatusBadge value={latestBatch.state} /></div> : <EmptyState text="No ingestion batches have been created." />}</div>
    </section>
    <section className="panel"><PanelHeader title="Recently ingested" actionLabel="Open library" onAction={() => onNavigate("library")} />{documents.length === 0 ? <EmptyState text="Your canonical library is empty. Import a PDF or folder to begin." /> : <DocumentTable documents={documents.slice(0, 5)} onSelectDocument={onSelectDocument} />}</section>
  </>;
}

function MetricCard({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: typeof Activity }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><Icon size={16} /></div><strong>{value}</strong><small>{detail}</small></div>;
}

function PanelHeader({ title, actionLabel, onAction }: { title: string; actionLabel?: string; onAction?: () => void }) {
  return <div className="panel-header"><h3>{title}</h3>{actionLabel && onAction && <button className="text-button" onClick={onAction}>{actionLabel}<ArrowUpRight size={14} /></button>}</div>;
}

function HealthRow({ item }: { item: HealthComponent }) {
  return <div className="health-row"><div className={`health-icon ${statusClass(item.status)}`}>{item.status === "READY" ? <CheckCircle2 size={16} /> : item.status === "ERROR" ? <XCircle size={16} /> : <Activity size={16} />}</div><div><strong>{item.name}</strong><span>{item.detail}</span></div><StatusBadge value={item.status} /></div>;
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`status-badge ${statusClass(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function ImportView({ onCreated }: { onCreated: () => Promise<void> }) {
  const [paths, setPaths] = useState<string[]>([]);
  const [webFiles, setWebFiles] = useState<File[]>([]);
  const [recursive, setRecursive] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const webInputRef = useRef<HTMLInputElement>(null);
  const desktopShell = isTauriRuntime();
  const handleWebSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    setWebFiles((current) => {
      const combined = [...current, ...selected];
      return combined.filter(
        (file, index, files) =>
          files.findIndex((candidate) => `${candidate.name}:${candidate.size}:${candidate.lastModified}` === `${file.name}:${file.size}:${file.lastModified}`) === index,
      );
    });
    event.target.value = "";
  };
  const chooseFiles = async () => {
    if (!desktopShell) {
      webInputRef.current?.removeAttribute("webkitdirectory");
      webInputRef.current?.click();
      return;
    }
    try {
      const selected = await open({ multiple: true, directory: false, filters: [{ name: "PDF documents", extensions: ["pdf"] }] });
      const values = Array.isArray(selected) ? selected : selected ? [selected] : [];
      setPaths((current) => [...new Set([...current, ...values])]);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Native file selection is unavailable"); }
  };
  const chooseFolder = async () => {
    if (!desktopShell) {
      webInputRef.current?.setAttribute("webkitdirectory", "");
      webInputRef.current?.click();
      return;
    }
    try {
      const selected = await open({ multiple: false, directory: true });
      if (typeof selected === "string") setPaths((current) => [...new Set([...current, selected])]);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Native folder selection is unavailable"); }
  };
  const createBatch = async () => {
    if (desktopShell && !paths.length) { setMessage("Choose at least one file or folder before starting."); return; }
    if (!desktopShell && !webFiles.length) { setMessage("Choose at least one PDF before starting."); return; }
    setSubmitting(true); setMessage(null);
    try {
      if (desktopShell) {
        await api.createBatch(paths, recursive);
      } else {
        await api.createUploadBatch(webFiles, recursive);
      }
      setPaths([]); setWebFiles([]); setMessage("Batch created. Track the persisted stages in Ingestion jobs."); await onCreated();
    }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : "Unable to create the batch"); }
    finally { setSubmitting(false); }
  };
  const stagedCount = desktopShell ? paths.length : webFiles.length;
  return <section className="import-layout"><div className="panel import-panel"><input ref={webInputRef} type="file" accept=".pdf,application/pdf" multiple onChange={handleWebSelection} hidden /><div className="drop-zone"><div className="drop-icon"><UploadCloud size={28} /></div><h3>Bring in source documents</h3><p>{desktopShell ? "Select individual PDFs or a folder. The backend receives filesystem paths directly and processes the corpus incrementally." : "Select PDFs from this browser. A local copy is sent to the local backend for durable ingestion."}</p><div className="import-actions"><button className="primary-button" onClick={() => void chooseFiles()}><FileSearch size={17} /> Choose PDFs</button><button className="secondary-button" onClick={() => void chooseFolder()}><FolderOpen size={17} /> Choose folder</button></div></div><div className="import-options"><label className="checkbox-label"><input type="checkbox" checked={recursive} onChange={(event) => setRecursive(event.target.checked)} /> Include nested folders</label><span>Unsupported files are recorded as SKIPPED_UNSUPPORTED.</span></div>{stagedCount > 0 && <div className="staged-list"><div className="staged-header"><strong>{desktopShell ? "Staged paths" : "Selected files"}</strong><span>{stagedCount}</span></div>{desktopShell ? paths.map((path) => <div className="staged-path" key={path}><HardDrive size={15} /><span title={path}>{path}</span><button onClick={() => setPaths((current) => current.filter((value) => value !== path))} aria-label={`Remove ${path}`}><XCircle size={15} /></button></div>) : webFiles.map((file) => <div className="staged-path" key={`${file.name}:${file.size}:${file.lastModified}`}><HardDrive size={15} /><span title={file.webkitRelativePath || file.name}>{file.webkitRelativePath || file.name}</span><button onClick={() => setWebFiles((current) => current.filter((value) => value !== file))} aria-label={`Remove ${file.name}`}><XCircle size={15} /></button></div>)}<button className="primary-button full-width" onClick={() => void createBatch()} disabled={submitting}>{submitting ? "Creating batch…" : "Start durable ingestion"}</button></div>}{message && <div className="inline-message">{message}</div>}</div><div className="side-stack"><div className="panel"><PanelHeader title="Pipeline contract" /><div className="pipeline-list">{["Discover and validate", "Extract pages / OCR when needed", "Classify and parse structure", "Persist provenance and chunks", "Index text and embeddings", "Validate durable result"].map((step, index) => <div className="pipeline-step" key={step}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong><ChevronRight size={15} /></div>)}</div></div><div className="notice-card"><ShieldCheck size={19} /><div><strong>{desktopShell ? "Source PDFs remain authoritative" : "Browser import stays local"}</strong><p>{desktopShell ? "Reference mode stores paths and hashes. Originals are never modified or deleted automatically." : "Selected files are copied only to this local backend; no external upload is involved."}</p></div></div></div></section>;
}

function JobsView({ batches, onChanged }: { batches: Batch[]; onChanged: () => Promise<void> }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [items, setItems] = useState<BatchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const action = async (kind: "pause" | "resume" | "cancel" | "retry", id: string) => {
    setJobError(null);
    try { await api[`${kind}Batch`](id); await onChanged(); }
    catch (reason) { setJobError(reason instanceof Error ? reason.message : `Unable to ${kind} batch`); }
  };
  const inspect = async (id: string) => {
    setExpanded(id); setLoading(true); setJobError(null);
    try { setItems(await api.getBatchItems(id)); }
    catch (reason) { setJobError(reason instanceof Error ? reason.message : "Unable to load batch items"); }
    finally { setLoading(false); }
  };
  return <div className="panel"><PanelHeader title="Durable ingestion jobs" />{jobError && <div className="error-banner"><XCircle size={17} />{jobError}</div>}<div className="table-wrap"><table><thead><tr><th>Batch</th><th>Created</th><th>Files</th><th>Progress</th><th>State</th><th>Controls</th></tr></thead><tbody>{batches.length === 0 ? <tr><td colSpan={6}><EmptyState text="No batches yet." /></td></tr> : batches.map((batch) => <tr key={batch.id}><td><button className="link-button" onClick={() => void inspect(batch.id)}><code>{batch.id.slice(0, 8)}</code></button></td><td>{new Date(batch.created_at).toLocaleString()}</td><td>{batch.item_count}</td><td>{batch.completed_count}/{batch.item_count} complete · {batch.failed_count} failed</td><td><StatusBadge value={batch.state} /></td><td><div className="row-actions">{["QUEUED", "EXTRACTING", "OCR", "PARSING", "EMBEDDING"].includes(batch.state) && <button className="small-button" onClick={() => void action("pause", batch.id)}><Pause size={14} /> Pause</button>}{batch.state === "DISCOVERED" && <button className="small-button" onClick={() => void action("resume", batch.id)}><Play size={14} /> Resume</button>}{batch.state.startsWith("FAILED") && <button className="small-button" onClick={() => void action("retry", batch.id)}><RotateCcw size={14} /> Retry</button>}{!["COMPLETED", "CANCELLED", "FAILED_RETRYABLE", "FAILED_TERMINAL"].includes(batch.state) && <button className="small-button danger" onClick={() => void action("cancel", batch.id)}><Square size={13} /> Cancel</button>}</div></td></tr>)}</tbody></table></div>{expanded && <div className="job-inspector"><PanelHeader title={`Batch ${expanded.slice(0, 8)} items`} actionLabel="Close" onAction={() => setExpanded(null)} />{loading ? <div className="loading-state"><LoaderCircle className="spin" size={18} /> Loading persisted item state…</div> : items.map((item) => <div className="job-item" key={item.id}><StatusBadge value={item.state} /><span title={item.path}>{item.path}</span><small>{item.last_error || `attempts ${item.attempts}`}</small></div>)}</div>}</div>;
}

function LibraryView({ documents, emptyMessage = "No documents have been ingested yet.", onSelectDocument }: { documents: DocumentRecord[]; emptyMessage?: string; onSelectDocument: (document: DocumentRecord) => void }) {
  return <div className="panel"><PanelHeader title="Canonical document library" /><p className="panel-intro">Each record points to a source path and SHA-256 digest. Select a document to inspect raw pages, normalized text, legal structure, and references.</p>{documents.length === 0 ? <EmptyState text={emptyMessage} /> : <DocumentTable documents={documents} detailed onSelectDocument={onSelectDocument} />}</div>;
}

function DocumentTable({ documents, detailed = false, onSelectDocument }: { documents: DocumentRecord[]; detailed?: boolean; onSelectDocument: (document: DocumentRecord) => void }) {
  return <div className="table-wrap"><table><thead><tr><th>Document</th><th>Type</th><th>Pages</th>{detailed && <th>Size</th>}<th>Source</th></tr></thead><tbody>{documents.map((document) => <tr key={document.id} className="clickable-row" tabIndex={0} onClick={() => onSelectDocument(document)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectDocument(document); } }}><td><strong className="truncate">{document.title || document.filename}</strong><code>{document.sha256.slice(0, 14)}…</code></td><td><StatusBadge value={document.document_type} /></td><td>{document.page_count}</td>{detailed && <td>{formatBytes(document.byte_size)}</td>}<td><span className="path-cell" title={document.source_path}>{document.source_path}</span>{document.missing_source && <span className="missing-label">Source missing</span>}</td></tr>)}</tbody></table></div>;
}

function DocumentInspector({ document, onClose }: { document: DocumentRecord; onClose: () => void }) {
  const [pages, setPages] = useState<PageRecord[]>([]);
  const [structure, setStructure] = useState<DocumentStructure | null>(null);
  const [tab, setTab] = useState<"pages" | "structure" | "references">("pages");
  const [selectedPage, setSelectedPage] = useState(0);
  const [normalized, setNormalized] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null); setPages([]); setStructure(null); setSelectedPage(0);
    void Promise.all([api.getPages(document.id), api.getStructure(document.id)]).then(([pageResult, structureResult]) => {
      if (!active) return;
      setPages(pageResult); setStructure(structureResult);
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load document inspection data"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [document.id]);
  const page = pages[selectedPage];
  return <div className="inspector-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="document-inspector" aria-label="Document inspector"><div className="inspector-header"><div><span className="eyebrow">Document inspection</span><h2>{document.title || document.filename}</h2><code>{document.source_path}</code></div><button className="icon-button" onClick={onClose} aria-label="Close document inspector"><XCircle size={18} /></button></div><div className="inspector-meta"><StatusBadge value={document.document_type} /><span>{document.page_count} pages</span><span>SHA-256 {document.sha256.slice(0, 18)}…</span></div><div className="inspector-tabs"><button className={tab === "pages" ? "active" : ""} onClick={() => setTab("pages")}>Pages</button><button className={tab === "structure" ? "active" : ""} onClick={() => setTab("structure")}>Legal structure</button><button className={tab === "references" ? "active" : ""} onClick={() => setTab("references")}>References ({structure?.references.length ?? 0})</button></div>{loading ? <div className="loading-state"><LoaderCircle className="spin" size={18} /> Loading persisted document data…</div> : error ? <div className="error-banner"><XCircle size={17} />{error}</div> : tab === "pages" ? <div className="pages-layout"><div className="page-list">{pages.map((item, index) => <button key={item.id} className={index === selectedPage ? "page-button active" : "page-button"} onClick={() => setSelectedPage(index)}><span>Page {item.page_number}</span><small>{item.extraction_method} · {item.normalized_text.length} chars</small></button>)}</div><div className="page-content"><div className="page-toolbar"><span>Page {page?.page_number ?? "—"}</span><label><input type="checkbox" checked={normalized} onChange={(event) => setNormalized(event.target.checked)} /> Normalized text</label></div><pre>{normalized ? page?.normalized_text : page?.raw_text}</pre>{page?.warnings.length ? <div className="page-warning">Warnings: {page.warnings.join("; ")}</div> : null}</div></div> : tab === "structure" ? <StructureView structure={structure} /> : <ReferenceView structure={structure} />}</aside></div>;
}

function StructureView({ structure }: { structure: DocumentStructure | null }) {
  if (!structure) return <EmptyState text="No structure was persisted for this document." />;
  if (structure.act) return <div className="structure-view"><h3>{structure.act.name || structure.act.short_title || "Legislation"}</h3>{structure.act.sections.map((section) => <article className="structure-card" key={`${section.label}-${section.page_start}`}><div><strong>Section {section.label}</strong><span>Pages {section.page_start}–{section.page_end}</span></div><h4>{section.heading}</h4><p>{section.text}</p></article>)}</div>;
  if (structure.judgment) return <div className="structure-view"><div className="judgment-meta"><strong>{structure.judgment.case_title || "Judgment"}</strong><span>{structure.judgment.court || "Court not detected"} · {structure.judgment.paragraphs.length} paragraphs</span></div>{structure.judgment.paragraphs.map((paragraph) => <article className="structure-card" key={paragraph.internal_sequence}><div><strong>{paragraph.official_number ? `Paragraph ${paragraph.official_number}` : `Internal paragraph ${paragraph.internal_sequence}`}</strong><span>Pages {paragraph.page_start}–{paragraph.page_end}</span></div><p>{paragraph.text}</p></article>)}</div>;
  return <EmptyState text="No legislation or judgment structure was persisted." />;
}

function ReferenceView({ structure }: { structure: DocumentStructure | null }) {
  const references = structure?.references ?? [];
  return <div className="reference-list">{references.length === 0 ? <EmptyState text="No references were detected in this document." /> : references.map((reference) => <div className="reference-row" key={reference.id}><StatusBadge value={reference.resolution_status} /><div><strong>{reference.source_text}</strong><span>{reference.reference_type} · pages {reference.page_start}–{reference.page_end}</span></div></div>)}</div>;
}

function SearchView() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runSearch = async () => { if (!query.trim()) return; setSearching(true); setError(null); try { setResult(await api.search(query.trim(), mode)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Search failed"); } finally { setSearching(false); } };
  return <section className="search-layout"><div className="search-bar panel"><Search size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void runSearch(); }} placeholder="Search statutory text, paragraphs, citations…" /><select value={mode} onChange={(event) => setMode(event.target.value as SearchMode)}><option value="hybrid">Hybrid</option><option value="lexical">Lexical FTS</option><option value="semantic">Semantic pgvector</option></select><button className="primary-button" onClick={() => void runSearch()} disabled={searching}>{searching ? "Searching…" : "Search"}</button></div>{error && <div className="error-banner"><XCircle size={17} />{error}</div>}{result && <div className="search-meta"><span>{result.hits.length} provenance-backed result{result.hits.length === 1 ? "" : "s"}</span><span>Mode: <strong>{result.mode}</strong></span><span>Embedding: <strong>{result.embedding_status}</strong></span></div>}<div className="result-list">{result?.hits.map((hit) => <article className="result-card" key={hit.chunk_id}><div className="result-card-top"><StatusBadge value={hit.document_type} /><span>Pages {hit.page_start}–{hit.page_end}</span><span>Score {hit.fused_score.toFixed(4)}</span></div><p>{hit.text}</p><div className="result-source"><span>{hit.section_label ? `Section ${hit.section_label}` : hit.paragraph_number ? `Paragraph ${hit.paragraph_number}` : "Source passage"}</span><code>{hit.source_path}</code></div></article>)}{result && result.hits.length === 0 && <EmptyState text="No results matched the selected retrieval mode." />}{!result && <div className="search-empty"><Search size={34} /><h3>Search the indexed corpus</h3><p>Results include their source file, page range, section or paragraph context, and actual lexical or semantic signals.</p></div>}</div></section>;
}

function FailureView({ batches }: { batches: Batch[] }) {
  const failures = batches.filter((batch) => batch.state.startsWith("FAILED"));
  return <div className="panel"><PanelHeader title="Failures requiring attention" />{failures.length === 0 ? <EmptyState text="No failed batches are currently reported by the backend." /> : failures.map((batch) => <div className="failure-row" key={batch.id}><XCircle size={18} /><div><strong>Batch {batch.id.slice(0, 8)}</strong><span>{batch.item_count} files · {batch.failed_count} failed items · {batch.state}</span></div><StatusBadge value={batch.state} /></div>)}</div>;
}

function DatabaseView({ setup, documents }: { setup: HealthComponent[]; documents: DocumentRecord[] }) {
  return <section className="content-grid"><div className="panel large-panel"><PanelHeader title="Database and subsystem health" />{setup.map((item) => <HealthRow key={item.name} item={item} />)}</div><div className="panel"><PanelHeader title="Canonical counts" /><div className="count-list"><div><span>Documents</span><strong>{documents.length}</strong></div><div><span>Pages</span><strong>{documents.reduce((total, document) => total + document.page_count, 0)}</strong></div><div><span>Database truth</span><StatusBadge value="POSTGRESQL" /></div></div></div></section>;
}

function SettingsView({ setup }: { setup: HealthComponent[] }) {
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const backfill = async () => { setWorking(true); setMessage(null); try { const result = await api.backfillEmbeddings(100); setMessage(`${result.embedded} missing embeddings created with ${result.model} (${result.dimension} dimensions).`); } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Embedding backfill failed"); } finally { setWorking(false); } };
  return <div className="settings-grid"><div className="panel"><PanelHeader title="Runtime configuration" /><div className="settings-list"><div><span>Backend endpoint</span><code>127.0.0.1:8765</code></div><div><span>Storage model</span><strong>Reference mode</strong></div><div><span>Search index</span><strong>PostgreSQL FTS + pgvector</strong></div><div><span>Embedding provider</span><strong>{setup.find((item) => item.name === "Embedding subsystem")?.detail || "Reported by backend"}</strong></div></div><button className="secondary-button full-width" onClick={() => void backfill()} disabled={working}>{working ? "Backfilling…" : "Retry missing embeddings"}</button>{message && <div className="inline-message">{message}</div>}</div><div className="notice-card"><ShieldCheck size={19} /><div><strong>Destructive actions are not implicit</strong><p>Database downgrade, reset, or source deletion is intentionally not exposed as a one-click action.</p></div></div></div>;
}

function EmptyState({ text }: { text: string }) { return <div className="empty-state"><span>{text}</span></div>; }

export default App;
