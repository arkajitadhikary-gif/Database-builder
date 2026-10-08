import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  Activity,
  ArrowUpDown,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  Code,
  Database,
  Download,
  FileSearch,
  FileSpreadsheet,
  FolderOpen,
  HardDrive,
  LayoutDashboard,
  Library,
  LoaderCircle,
  Moon,
  PanelLeft,
  PanelLeftClose,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Table2,
  Trash2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import {
  api,
  type Batch,
  type BatchItem,
  type DatabaseTable,
  type DatabaseTablePage,
  type DatabaseRecord,
  type DocumentRecord,
  type ExtractedTableDetail,
  type ExtractedTableRow,
  type ExtractedTableSummary,
  type GroqConfig,
  type HealthComponent,
  type PageRecord,
  type SearchResponse,
  isTauriRuntime,
} from "./lib/api";

type View =
  | "overview"
  | "spreadsheet-studio"
  | "library"
  | "import"
  | "search"
  | "jobs"
  | "database"
  | "table-explorer"
  | "table-detail"
  | "settings";
type SearchMode = "lexical" | "semantic" | "hybrid";

type NavigationItem = { id: View; label: string; icon: typeof Activity };

const navigation: NavigationItem[] = [
  { id: "spreadsheet-studio", label: "Dashboard", icon: LayoutDashboard },
  { id: "import", label: "Upload PDF", icon: UploadCloud },
  { id: "library", label: "Documents", icon: Library },
  { id: "search", label: "Search", icon: Search },
  { id: "settings", label: "Settings", icon: Settings },
];

function statusClass(status: string): string {
  return status.toLowerCase().replace(/[\s/]+/g, "-");
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function App() {
  const [view, setView] = useState<View>("spreadsheet-studio");
  const [darkMode, setDarkMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [setup, setSetup] = useState<HealthComponent[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [extractedTables, setExtractedTables] = useState<ExtractedTableSummary[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<DocumentRecord | null>(null);
  const [selectedTableRow, setSelectedTableRow] = useState<{ tableKey: string; rowId: string; field: string } | null>(null);
  const [selectedStudioDocId, setSelectedStudioDocId] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [setupResult, batchResult, documentResult, tableResult] = await Promise.all([
        api.getSetup(),
        api.getBatches(),
        api.getDocuments(),
        api.getExtractedTables().catch(() => []),
      ]);
      setSetup(setupResult.components);
      setBatches(batchResult);
      setDocuments(documentResult);
      setExtractedTables(tableResult);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Backend unavailable");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const counts = useMemo(() => {
    const completed = batches.filter((batch) => batch.state === "COMPLETED").length;
    const active = batches.filter(
      (batch) => !["COMPLETED", "CANCELLED", "FAILED_RETRYABLE", "FAILED_TERMINAL"].includes(batch.state),
    ).length;
    const totalRows = extractedTables.reduce((acc, t) => acc + (t.row_count || 0), 0);
    return { completed, active, documents: documents.length, tables: extractedTables.length, rows: totalRows };
  }, [batches, documents.length, extractedTables]);

  const handleOpenDocInSpreadsheet = (docId: string) => {
    setSelectedStudioDocId(docId);
    setView("spreadsheet-studio");
  };

  return (
    <div className={`${darkMode ? "app dark" : "app"}${sidebarOpen ? "" : " sidebar-collapsed"}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-title-wrap">
            <div className="brand-mark"><Database size={20} strokeWidth={2.2} /></div>
            <div><strong>Database Builder</strong><span>Universal PDF to Database</span></div>
          </div>
          <button
            className="icon-button"
            style={{ border: 0, background: "transparent", cursor: "pointer" }}
            onClick={() => setSidebarOpen(false)}
            title="Collapse Sidebar"
          >
            <PanelLeftClose size={17} />
          </button>
        </div>
        <div className="workspace-label">Workspace</div>
        <nav className="nav-list" aria-label="Primary navigation">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button key={id} className={view === id ? "nav-item active" : "nav-item"} onClick={() => setView(id)}>
              <Icon size={17} /><span>{label}</span>
              {id === "jobs" && batches.some((batch) => batch.state.startsWith("FAILED")) && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="secure-note">
            <Sparkles size={16} />
            <span>Groq LLM Powered<br /><small>Universal Document Engine</small></span>
          </div>
          <button className="theme-toggle" onClick={() => setDarkMode((value) => !value)}>
            {darkMode ? <Sun size={15} /> : <Moon size={15} />} {darkMode ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            {!sidebarOpen && (
              <button
                className="icon-button"
                onClick={() => setSidebarOpen(true)}
                title="Open Sidebar"
                aria-label="Open Sidebar"
              >
                <PanelLeft size={18} />
              </button>
            )}
            <div>
              <span className="eyebrow">DATABASE BUILDER / {navigation.find((item) => item.id === view)?.label?.toUpperCase()}</span>
              <h1>{pageTitle(view)}</h1>
            </div>
          </div>
          <div className="topbar-actions">
            {sidebarOpen && (
              <button
                className="icon-button"
                onClick={() => setSidebarOpen(false)}
                title="Collapse Sidebar"
                aria-label="Collapse Sidebar"
              >
                <PanelLeftClose size={17} />
              </button>
            )}
            <div className={setup.length > 0 && setup.every((item) => ["READY", "WARNING"].includes(item.status)) ? "connection-pill ready" : "connection-pill"}>
              <span className="connection-dot" /> {setup.length === 0 ? "Checking backend" : "System state: READY"}
            </div>
            <button className="icon-button" onClick={() => void refresh()} aria-label="Refresh data" title="Refresh data">
              <RefreshCw size={17} className={refreshing ? "spin" : ""} />
            </button>
          </div>
        </header>

        {error && <div className="error-banner"><XCircle size={17} /><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button></div>}

        {view === "spreadsheet-studio" && (
          <SpreadsheetStudioView
            initialDocumentId={selectedStudioDocId}
            onRefreshRoot={refresh}
            onNavigate={setView}
          />
        )}
        {view === "overview" && (
          <Overview
            setup={setup}
            counts={counts}
            batches={batches}
            documents={documents}
            tables={extractedTables}
            onNavigate={setView}
            onSelectDocument={setSelectedDocument}
            onOpenDocInSpreadsheet={handleOpenDocInSpreadsheet}
          />
        )}
        {view === "library" && (
          <LibraryView
            documents={documents}
            onSelectDocument={setSelectedDocument}
            onOpenInSpreadsheet={handleOpenDocInSpreadsheet}
            onRefresh={refresh}
          />
        )}
        {view === "import" && <ImportView onCreated={refresh} />}
        {view === "jobs" && <JobsView batches={batches} onChanged={refresh} />}
        {view === "search" && <SearchView />}
        {view === "database" && <DatabaseView setup={setup} documents={documents} />}
        {view === "table-explorer" && (
          <TableExplorerView
            onOpenRow={(tableKey, rowId, field) => {
              setSelectedTableRow({ tableKey, rowId, field });
              setView("table-detail");
            }}
          />
        )}
        {view === "table-detail" && selectedTableRow && (
          <TableRowDetailView selection={selectedTableRow} onBack={() => setView("table-explorer")} />
        )}
        {view === "settings" && <SettingsView setup={setup} onResetAll={refresh} />}
      </main>

      {selectedDocument && <DocumentInspector document={selectedDocument} onClose={() => setSelectedDocument(null)} />}
    </div>
  );
}

function pageTitle(view: View): string {
  return navigation.find((item) => item.id === view)?.label ?? (view === "table-detail" ? "Table detail" : "Overview");
}

/* -------------------------------------------------------------------------
   Spreadsheet Studio View (Excel-like Interactive Grid)
------------------------------------------------------------------------- */

function SpreadsheetStudioView({
  initialDocumentId,
  onRefreshRoot,
  onNavigate,
}: {
  initialDocumentId?: string;
  onRefreshRoot: () => Promise<void>;
  onNavigate: (view: View) => void;
}) {
  const [tables, setTables] = useState<ExtractedTableSummary[]>([]);
  const [selectedTableId, setSelectedTableId] = useState<string>("");
  const [tableDetail, setTableDetail] = useState<ExtractedTableDetail | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState<boolean>(true);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modals for editing / adding rows
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingRow, setEditingRow] = useState<ExtractedTableRow | null>(null);
  const [rowFormData, setRowFormData] = useState<Record<string, string>>({});

  const pageSize = 50;

  const loadTables = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getExtractedTables(initialDocumentId);
      setTables(result);
      if (result.length > 0) {
        setSelectedTableId((current) => {
          if (current && result.some((t) => t.id === current)) return current;
          const withRows = result.find((t) => (t.row_count || 0) > 0);
          return withRows ? withRows.id : result[0].id;
        });
      } else {
        setSelectedTableId("");
        setTableDetail(null);
      }
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to load extracted tables");
    } finally {
      setLoading(false);
    }
  }, [initialDocumentId]);

  useEffect(() => {
    void loadTables();
  }, [loadTables]);

  const loadTableDetail = useCallback(async (id: string, pageOffset = 0, search = "") => {
    if (!id) return;
    setDetailLoading(true);
    try {
      const detail = await api.getExtractedTable(id, search, pageOffset, pageSize);
      setTableDetail(detail);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to load table records");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTableId) {
      void loadTableDetail(selectedTableId, offset, searchQuery);
    }
  }, [selectedTableId, offset, searchQuery, loadTableDetail]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    tables.forEach((t) => set.add(t.document_category || "General Document"));
    return ["ALL", ...Array.from(set)];
  }, [tables]);

  const filteredTables = useMemo(() => {
    if (categoryFilter === "ALL") return tables;
    return tables.filter((t) => (t.document_category || "General Document") === categoryFilter);
  }, [tables, categoryFilter]);

  const handleSort = (colKey: string) => {
    if (sortCol === colKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(colKey);
      setSortAsc(true);
    }
  };

  const sortedRows = useMemo(() => {
    if (!tableDetail?.rows) return [];
    if (!sortCol) return tableDetail.rows;
    return [...tableDetail.rows].sort((a, b) => {
      const valA = a.data?.[sortCol] ?? "";
      const valB = b.data?.[sortCol] ?? "";
      if (typeof valA === "number" && typeof valB === "number") {
        return sortAsc ? valA - valB : valB - valA;
      }
      return sortAsc ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
    });
  }, [tableDetail?.rows, sortCol, sortAsc]);

  const handleTriggerGroq = async () => {
    if (!tableDetail?.table.document_id) return;
    setExtracting(true);
    setError(null);
    try {
      await api.extractDocumentTables(tableDetail.table.document_id);
      await loadTables();
      await onRefreshRoot();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Groq extraction failed");
    } finally {
      setExtracting(false);
    }
  };

  const handleDeleteRow = async (rowId: string) => {
    if (!confirm("Are you sure you want to delete this row?")) return;
    const prevDetail = tableDetail;
    const prevTables = tables;

    // Instant optimistic UI update
    if (tableDetail) {
      setTableDetail({
        ...tableDetail,
        rows: tableDetail.rows.filter((r) => r.id !== rowId),
        total_rows: Math.max(0, tableDetail.total_rows - 1),
      });
    }
    setTables((prev) =>
      prev.map((t) => (t.id === selectedTableId ? { ...t, row_count: Math.max(0, t.row_count - 1) } : t))
    );

    try {
      await api.deleteTableRow(selectedTableId, rowId);
    } catch (reason) {
      setTableDetail(prevDetail);
      setTables(prevTables);
      setError(reason instanceof Error ? reason.message : "Failed to delete row");
    }
  };

  const handleDeleteTable = async (id: string) => {
    if (!confirm(`Are you sure you want to delete table "${tableDetail?.table.table_name}"? This will delete all rows in this table.`)) return;
    const prevTables = [...tables];
    const prevSelectedId = selectedTableId;
    const prevDetail = tableDetail;

    // Instant optimistic UI update
    setTables((prev) => prev.filter((t) => t.id !== id));
    setSelectedTableId("");
    setTableDetail(null);

    try {
      await api.deleteTable(id);
      await onRefreshRoot();
    } catch (reason) {
      setTables(prevTables);
      setSelectedTableId(prevSelectedId);
      setTableDetail(prevDetail);
      setError(reason instanceof Error ? reason.message : "Failed to delete table");
    }
  };

  const openAddModal = () => {
    const initial: Record<string, string> = {};
    tableDetail?.table.columns.forEach((c) => {
      initial[c.key] = "";
    });
    setRowFormData(initial);
    setIsAddModalOpen(true);
  };

  const openEditModal = (row: ExtractedTableRow) => {
    const initial: Record<string, string> = {};
    tableDetail?.table.columns.forEach((c) => {
      initial[c.key] = String(row.data?.[c.key] ?? "");
    });
    setRowFormData(initial);
    setEditingRow(row);
  };

  const saveRowForm = async () => {
    try {
      if (editingRow) {
        await api.updateTableRow(selectedTableId, editingRow.id, rowFormData);
        setEditingRow(null);
      } else {
        await api.addTableRow(selectedTableId, rowFormData);
        setIsAddModalOpen(false);
      }
      await loadTableDetail(selectedTableId, offset, searchQuery);
      await loadTables();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to save row");
    }
  };

  const totalPages = tableDetail ? Math.max(1, Math.ceil(tableDetail.total_rows / pageSize)) : 1;
  const currentPage = Math.floor(offset / pageSize) + 1;

  return (
    <section className="spreadsheet-studio-layout">
      <div className="panel studio-header">
        <div>
          <span className="hero-kicker">Universal PDF to Database Engine / Groq AI</span>
          <h2>Dashboard</h2>
          <p>
            Upload any PDF (invoices, receipts, financial reports, resumes, medical records, catalogs, forms, etc.).
            AI automatically analyzes the document, discovers its structure, and builds relational database tables with instant CSV export.
          </p>
        </div>
        <div className="studio-stats">
          <div className="stat-box">
            <strong>{tables.length}</strong>
            <span>Tables</span>
          </div>
          <div className="stat-box">
            <strong>{tables.reduce((acc, t) => acc + (t.row_count || 0), 0)}</strong>
            <span>Total Rows</span>
          </div>
        </div>
      </div>

      {/* Category Filter Pills */}
      {categories.length > 2 && (
        <div className="database-tabs">
          {categories.map((cat) => (
            <button
              key={cat}
              className={categoryFilter === cat ? "active" : ""}
              onClick={() => {
                setCategoryFilter(cat);
                setOffset(0);
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {/* Table Selector Strip */}
      <div className="table-selection-strip">
        {filteredTables.map((t) => (
          <button
            key={t.id}
            className={`table-pill-btn ${selectedTableId === t.id ? "active" : ""}`}
            onClick={() => {
              setSelectedTableId(t.id);
              setOffset(0);
              setSearchQuery("");
            }}
          >
            <FileSpreadsheet size={15} />
            <span>{t.table_name}</span>
            <span className="pill-count">{t.row_count} rows</span>
          </button>
        ))}
      </div>

      {/* Main Table Spreadsheet Panel */}
      <div className="panel spreadsheet-panel">
        {tableDetail && (
          <div className="excel-meta-banner">
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "9px", marginBottom: "4px" }}>
                <strong>{tableDetail.table.table_name}</strong>
                <span className={`category-badge ${statusClass(tableDetail.table.document_category)}`}>
                  {tableDetail.table.document_category}
                </span>
              </div>
              <span>
                From: <code>{tableDetail.table.document_filename}</code> &nbsp;·&nbsp; {tableDetail.table.description || "Relational dataset"}
              </span>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                className="secondary-button"
                onClick={() => void handleTriggerGroq()}
                disabled={extracting}
                title="Re-run Groq extraction on this document"
              >
                <Sparkles size={14} className={extracting ? "spin" : ""} />
                {extracting ? "Extracting with Groq…" : "Re-extract with Groq"}
              </button>
              <button
                className="secondary-button danger-button"
                onClick={() => void handleDeleteTable(tableDetail.table.id)}
                title="Delete this entire table"
              >
                <Trash2 size={14} /> Delete Table
              </button>
            </div>
          </div>
        )}

        <div className="excel-toolbar">
          <div className="excel-search-box">
            <Search size={15} />
            <input
              type="text"
              placeholder="Filter table rows in real-time…"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setOffset(0);
              }}
            />
            {searchQuery && (
              <button
                style={{ border: 0, background: "transparent", cursor: "pointer" }}
                onClick={() => setSearchQuery("")}
              >
                <X size={14} />
              </button>
            )}
          </div>

          <div className="excel-actions">
            <button className="primary-button" onClick={openAddModal} disabled={!selectedTableId}>
              <Plus size={15} /> Add Row
            </button>
            {selectedTableId && (
              <>
                <a
                  className="btn-excel"
                  href={api.getTableExportCsvUrl(selectedTableId)}
                  target="_blank"
                  rel="noreferrer"
                  download
                  title="Download as CSV"
                >
                  <Download size={15} /> Export CSV
                </a>
                <a
                  className="btn-sql"
                  href={api.getTableExportSqlUrl(selectedTableId)}
                  target="_blank"
                  rel="noreferrer"
                  download
                  title="Download SQL Schema & Inserts (PostgreSQL / SQLite / MySQL)"
                >
                  <Code size={14} /> SQL
                </a>
                <a
                  className="btn-json"
                  href={api.getTableExportJsonUrl(selectedTableId)}
                  target="_blank"
                  rel="noreferrer"
                  download
                  title="Download as JSON"
                >
                  JSON
                </a>
              </>
            )}
          </div>
        </div>

        {error && <div className="error-banner"><XCircle size={17} />{error}</div>}

        {loading || detailLoading ? (
          <div className="loading-state">
            <LoaderCircle className="spin" size={20} /> Loading table grid…
          </div>
        ) : !tableDetail ? (
          <div className="empty-state-welcome">
            <div className="empty-icon-wrap"><Database size={36} /></div>
            <h3>No Database Tables Yet</h3>
            <p>
              Upload any PDF document (invoices, receipts, financial reports, resumes, academic papers, medical records, catalogs, forms, or contracts).
              Groq AI will automatically analyze the document, detect its structure, and generate relational database tables.
            </p>
            <button className="primary-button" onClick={() => onNavigate("import")}>
              <UploadCloud size={16} /> Upload Your First PDF
            </button>
          </div>
        ) : (
          <>
            <div className="excel-grid-container">
              <table className="excel-table">
                <thead>
                  <tr>
                    <th className="row-num">#</th>
                    {tableDetail.table.columns.map((col) => (
                      <th
                        key={col.key}
                        className="sortable"
                        onClick={() => handleSort(col.key)}
                        title={`Click to sort by ${col.label}`}
                      >
                        <div className="th-content">
                          <span>{col.label}</span>
                          <span className="col-type">[{col.type}]</span>
                          {sortCol === col.key ? (
                            <span>{sortAsc ? "▲" : "▼"}</span>
                          ) : (
                            <ArrowUpDown size={11} style={{ opacity: 0.3 }} />
                          )}
                        </div>
                      </th>
                    ))}
                    <th style={{ width: "80px" }}>Source Page</th>
                    <th className="row-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.length === 0 ? (
                    <tr>
                      <td colSpan={tableDetail.table.columns.length + 3} style={{ textAlign: "center", padding: "30px" }}>
                        <EmptyState text={searchQuery ? "No rows match your search query." : "This table has no rows."} />
                      </td>
                    </tr>
                  ) : (
                    sortedRows.map((row, idx) => (
                      <tr key={row.id}>
                        <td className="row-num">{offset + idx + 1}</td>
                        {tableDetail.table.columns.map((col) => {
                          const val = row.data?.[col.key];
                          return (
                            <td key={col.key} title={String(val ?? "—")}>
                              {val == null || val === "" ? <span style={{ opacity: 0.3 }}>—</span> : String(val)}
                            </td>
                          );
                        })}
                        <td style={{ textAlign: "center" }}>
                          <span className="status-badge ready">p. {row.source_page || 1}</span>
                        </td>
                        <td className="row-actions">
                          <button onClick={() => openEditModal(row)} title="Edit row">✏️</button>
                          <button onClick={() => void handleDeleteRow(row.id)} title="Delete row">
                            <Trash2 size={13} />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="spreadsheet-footer">
              <span>
                Showing {sortedRows.length} of {tableDetail.total_rows} rows &nbsp;·&nbsp; Page {currentPage} of {totalPages}
              </span>
              <div>
                <button
                  className="secondary-button"
                  onClick={() => setOffset(Math.max(0, offset - pageSize))}
                  disabled={offset === 0}
                >
                  Previous
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setOffset(offset + pageSize)}
                  disabled={offset + pageSize >= tableDetail.total_rows}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Add / Edit Row Modal */}
      {(isAddModalOpen || editingRow) && tableDetail && (
        <div className="modal-backdrop" onClick={(e) => { if (e.target === e.currentTarget) { setIsAddModalOpen(false); setEditingRow(null); } }}>
          <div className="modal-window">
            <div className="modal-header">
              <h3>{editingRow ? "Edit Row Record" : "Add New Row"}</h3>
              <button
                className="icon-button"
                onClick={() => {
                  setIsAddModalOpen(false);
                  setEditingRow(null);
                }}
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-form">
              {tableDetail.table.columns.map((col) => (
                <div className="form-field" key={col.key}>
                  <label>{col.label} <small>({col.type})</small></label>
                  <input
                    type="text"
                    value={rowFormData[col.key] ?? ""}
                    onChange={(e) => setRowFormData({ ...rowFormData, [col.key]: e.target.value })}
                    placeholder={`Enter ${col.label}…`}
                  />
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => { setIsAddModalOpen(false); setEditingRow(null); }}>
                Cancel
              </button>
              <button className="primary-button" onClick={() => void saveRowForm()}>
                Save Row
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------
   Overview View
------------------------------------------------------------------------- */

function Overview({
  setup,
  counts,
  batches,
  documents,
  tables,
  onNavigate,
  onSelectDocument,
  onOpenDocInSpreadsheet,
}: {
  setup: HealthComponent[];
  counts: { completed: number; active: number; documents: number; tables: number; rows: number };
  batches: Batch[];
  documents: DocumentRecord[];
  tables: ExtractedTableSummary[];
  onNavigate: (view: View) => void;
  onSelectDocument: (document: DocumentRecord) => void;
  onOpenDocInSpreadsheet: (docId: string) => void;
}) {
  const latestBatch = batches[0];
  return (
    <>
      <section className="hero-row">
        <div>
          <span className="hero-kicker">Universal PDF to Database Engine</span>
          <h2>Transform any PDF into Structured Relational Databases.</h2>
          <p>
            Whether it's an Invoice, Financial Balance Sheet, Academic Paper, Resume, Contract, Form, or Technical Document —
            Groq LLM automatically understands the structure, generates relational schemas, and builds interactive database tables.
          </p>
          <div style={{ display: "flex", gap: "10px" }}>
            <button className="primary-button" onClick={() => onNavigate("spreadsheet-studio")}>
              <LayoutDashboard size={17} /> Open Dashboard
            </button>
            <button className="secondary-button" onClick={() => onNavigate("import")}>
              <Plus size={17} /> Upload Any PDF
            </button>
          </div>
        </div>
        <div className="hero-illustration">
          <div className="orb orb-one" />
          <div className="orb orb-two" />
          <Database size={80} strokeWidth={1.1} />
        </div>
      </section>

      <section className="metrics-grid">
        <MetricCard label="Relational Rows" value={String(counts.rows)} detail="Extracted database records" icon={Table2} />
        <MetricCard label="Extracted Tables" value={String(counts.tables)} detail="Structured database tables" icon={Database} />
        <MetricCard label="Documents" value={String(counts.documents)} detail="Processed PDFs" icon={Library} />
        <MetricCard
          label="System Health"
          value={setup.length ? `${setup.filter((item) => item.status === "READY").length}/${setup.length}` : "—"}
          detail="Groq, DB & OCR Ready"
          icon={ShieldCheck}
        />
      </section>

      <section className="content-grid">
        <div className="panel large-panel">
          <PanelHeader title="Extracted Spreadsheet Tables" actionLabel="Open Studio" onAction={() => onNavigate("spreadsheet-studio")} />
          {tables.length === 0 ? (
            <EmptyState text="No spreadsheet tables created yet. Upload a PDF to start extracting." />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Table Name</th>
                    <th>Category</th>
                    <th>Rows</th>
                    <th>Document</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {tables.slice(0, 6).map((t) => (
                    <tr key={t.id}>
                      <td><strong>{t.table_name}</strong></td>
                      <td><span className={`category-badge ${statusClass(t.document_category)}`}>{t.document_category}</span></td>
                      <td>{t.row_count} rows</td>
                      <td><code>{t.document_filename}</code></td>
                      <td>
                        <button className="small-button" onClick={() => onOpenDocInSpreadsheet(t.document_id)}>
                          View Grid
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="panel">
          <PanelHeader title="Latest Import Batch" actionLabel="View Jobs" onAction={() => onNavigate("jobs")} />
          {latestBatch ? (
            <div className="latest-job">
              <div className="job-status-icon"><Activity size={20} /></div>
              <div>
                <strong>{latestBatch.item_count} discovered file{latestBatch.item_count === 1 ? "" : "s"}</strong>
                <span>{latestBatch.completed_count} complete · {latestBatch.failed_count} failed</span>
              </div>
              <StatusBadge value={latestBatch.state} />
            </div>
          ) : (
            <EmptyState text="No ingestion batches have been created." />
          )}
        </div>
      </section>

      <section className="panel">
        <PanelHeader title="Recently Ingested PDFs" actionLabel="Open Library" onAction={() => onNavigate("library")} />
        {documents.length === 0 ? (
          <EmptyState text="Your document library is empty. Import a PDF to begin." />
        ) : (
          <DocumentTable
            documents={documents.slice(0, 5)}
            onSelectDocument={onSelectDocument}
            onOpenInSpreadsheet={onOpenDocInSpreadsheet}
          />
        )}
      </section>
    </>
  );
}

function MetricCard({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: typeof Activity }) {
  return (
    <div className="metric-card">
      <div className="metric-top"><span>{label}</span><Icon size={16} /></div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function PanelHeader({ title, actionLabel, onAction }: { title: string; actionLabel?: string; onAction?: () => void }) {
  return (
    <div className="panel-header">
      <h3>{title}</h3>
      {actionLabel && onAction && (
        <button className="text-button" onClick={onAction}>{actionLabel}<ArrowUpRight size={14} /></button>
      )}
    </div>
  );
}

function HealthRow({ item }: { item: HealthComponent }) {
  return (
    <div className="health-row">
      <div className={`health-icon ${statusClass(item.status)}`}>
        {item.status === "READY" ? <CheckCircle2 size={16} /> : item.status === "ERROR" ? <XCircle size={16} /> : <Activity size={16} />}
      </div>
      <div><strong>{item.name}</strong><span>{item.detail}</span></div>
      <StatusBadge value={item.status} />
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`status-badge ${statusClass(value)}`}>{value.replaceAll("_", " ")}</span>;
}

/* -------------------------------------------------------------------------
   Import View
------------------------------------------------------------------------- */

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
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Native file selection is unavailable");
    }
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
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Native folder selection is unavailable");
    }
  };

  const createBatch = async () => {
    if (desktopShell && !paths.length) { setMessage("Choose at least one file or folder before starting."); return; }
    if (!desktopShell && !webFiles.length) { setMessage("Choose at least one PDF before starting."); return; }
    setSubmitting(true);
    setMessage(null);
    try {
      if (desktopShell) {
        await api.createBatch(paths, recursive);
      } else {
        await api.createUploadBatch(webFiles, recursive);
      }
      setPaths([]);
      setWebFiles([]);
      setMessage("Batch created! Groq AI is converting the PDFs into structured database tables. Check 'Dashboard' when completed.");
      await onCreated();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to create the batch");
    } finally {
      setSubmitting(false);
    }
  };

  const stagedCount = desktopShell ? paths.length : webFiles.length;

  return (
    <section className="import-layout">
      <div className="panel import-panel">
        <input ref={webInputRef} type="file" accept=".pdf,application/pdf" multiple onChange={handleWebSelection} hidden />
        <div className="drop-zone">
          <div className="drop-icon"><UploadCloud size={28} /></div>
          <h3>Bring in Any PDF Document</h3>
          <p>
            {desktopShell
              ? "Select any PDF or folder. Groq AI extracts the schema and generates Excel-like tables."
              : "Select PDFs from your computer. Invoices, balance sheets, resumes, reports, and records are processed locally."}
          </p>
          <div className="import-actions">
            <button className="primary-button" onClick={() => void chooseFiles()}><FileSearch size={17} /> Choose PDFs</button>
            <button className="secondary-button" onClick={() => void chooseFolder()}><FolderOpen size={17} /> Choose folder</button>
          </div>
        </div>

        <div className="import-options">
          <label className="checkbox-label">
            <input type="checkbox" checked={recursive} onChange={(event) => setRecursive(event.target.checked)} /> Include nested folders
          </label>
        </div>

        {stagedCount > 0 && (
          <div className="staged-list">
            <div className="staged-header">
              <strong>{desktopShell ? "Staged paths" : "Selected files"}</strong>
              <span>{stagedCount}</span>
            </div>
            {desktopShell
              ? paths.map((path) => (
                  <div className="staged-path" key={path}>
                    <HardDrive size={15} /><span title={path}>{path}</span>
                    <button onClick={() => setPaths((current) => current.filter((value) => value !== path))}><XCircle size={15} /></button>
                  </div>
                ))
              : webFiles.map((file) => (
                  <div className="staged-path" key={`${file.name}:${file.size}:${file.lastModified}`}>
                    <HardDrive size={15} /><span>{file.name}</span>
                    <button onClick={() => setWebFiles((current) => current.filter((value) => value !== file))}><XCircle size={15} /></button>
                  </div>
                ))}
            <button className="primary-button full-width" onClick={() => void createBatch()} disabled={submitting}>
              {submitting ? "Extracting & Creating Database…" : "Start Universal Database Ingestion"}
            </button>
          </div>
        )}

        {message && <div className="inline-message">{message}</div>}
      </div>

      <div className="side-stack">
        <div className="panel">
          <PanelHeader title="Universal Pipeline" />
          <div className="pipeline-list">
            {[
              "Text & OCR Extraction (PyMuPDF + Tesseract)",
              "Groq LLM Document Understanding",
              "Schema Synthesis & Column Typing",
              "Relational Tables & Rows Ingestion",
              "Vector Embeddings & Hybrid Search",
              "Database Dashboard & CSV Export Ready",
            ].map((step, index) => (
              <div className="pipeline-step" key={step}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{step}</strong>
                <ChevronRight size={15} />
              </div>
            ))}
          </div>
        </div>

        <div className="notice-card">
          <Sparkles size={19} />
          <div>
            <strong>Powered by Groq High-Speed LLM</strong>
            <p>Every document is classified and dynamically converted to clean tabular data without rigid schemas.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
   Document Library View
------------------------------------------------------------------------- */

function LibraryView({
  documents,
  emptyMessage = "No documents have been ingested yet.",
  onSelectDocument,
  onOpenInSpreadsheet,
  onRefresh,
}: {
  documents: DocumentRecord[];
  emptyMessage?: string;
  onSelectDocument: (document: DocumentRecord) => void;
  onOpenInSpreadsheet: (docId: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const [extractingId, setExtractingId] = useState<string | null>(null);

  const handleExtract = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    setExtractingId(docId);
    try {
      await api.extractDocumentTables(docId);
      await onRefresh();
      onOpenInSpreadsheet(docId);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setExtractingId(null);
    }
  };

  const handleDeleteDocument = async (e: React.MouseEvent, docId: string, name: string) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to delete "${name}"? This will delete all its pages and extracted tables.`)) return;
    try {
      await api.deleteDocument(docId);
      await onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="panel">
      <PanelHeader title="Universal Document Library" />
      <p className="panel-intro">
        All indexed documents. Click any document to inspect pages, or click "Dashboard" to open its extracted tables.
      </p>
      {documents.length === 0 ? (
        <EmptyState text={emptyMessage} />
      ) : (
        <DocumentTable
          documents={documents}
          detailed
          onSelectDocument={onSelectDocument}
          onOpenInSpreadsheet={onOpenInSpreadsheet}
          onExtract={handleExtract}
          onDeleteDocument={handleDeleteDocument}
          extractingId={extractingId}
        />
      )}
    </div>
  );
}

function DocumentTable({
  documents,
  detailed = false,
  onSelectDocument,
  onOpenInSpreadsheet,
  onExtract,
  onDeleteDocument,
  extractingId,
}: {
  documents: DocumentRecord[];
  detailed?: boolean;
  onSelectDocument: (document: DocumentRecord) => void;
  onOpenInSpreadsheet?: (docId: string) => void;
  onExtract?: (e: React.MouseEvent, docId: string) => void;
  onDeleteDocument?: (e: React.MouseEvent, docId: string, name: string) => void;
  extractingId?: string | null;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Document</th>
            <th>Type</th>
            <th>Pages</th>
            {detailed && <th>Size</th>}
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr
              key={document.id}
              className="clickable-row"
              tabIndex={0}
              onClick={() => onSelectDocument(document)}
            >
              <td>
                <strong className="truncate">{document.title || document.filename}</strong>
                <code>{document.sha256.slice(0, 14)}…</code>
              </td>
              <td><StatusBadge value={document.document_type} /></td>
              <td>{document.page_count}</td>
              {detailed && <td>{formatBytes(document.byte_size)}</td>}
              <td>
                <div style={{ display: "flex", gap: "6px" }} onClick={(e) => e.stopPropagation()}>
                  {onOpenInSpreadsheet && (
                    <button
                      className="small-button"
                      onClick={() => onOpenInSpreadsheet(document.id)}
                      title="Open in Dashboard"
                    >
                      <LayoutDashboard size={13} /> Dashboard
                    </button>
                  )}
                  {onExtract && (
                    <button
                      className="small-button"
                      onClick={(e) => onExtract(e, document.id)}
                      disabled={extractingId === document.id}
                      title="Extract tables with Groq"
                    >
                      <Sparkles size={13} className={extractingId === document.id ? "spin" : ""} />
                      {extractingId === document.id ? "Extracting…" : "Groq AI"}
                    </button>
                  )}
                  {onDeleteDocument && (
                    <button
                      className="small-button danger-btn"
                      onClick={(e) => onDeleteDocument(e, document.id, document.title || document.filename)}
                      title="Delete document"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Jobs View
------------------------------------------------------------------------- */

function JobsView({ batches, onChanged }: { batches: Batch[]; onChanged: () => Promise<void> }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [items, setItems] = useState<BatchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);

  const action = async (kind: "pause" | "resume" | "cancel" | "retry", id: string) => {
    setJobError(null);
    try {
      await api[`${kind}Batch`](id);
      await onChanged();
    } catch (reason) {
      setJobError(reason instanceof Error ? reason.message : `Unable to ${kind} batch`);
    }
  };

  const inspect = async (id: string) => {
    setExpanded(id);
    setLoading(true);
    setJobError(null);
    try {
      setItems(await api.getBatchItems(id));
    } catch (reason) {
      setJobError(reason instanceof Error ? reason.message : "Unable to load batch items");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <PanelHeader title="Durable Ingestion Jobs" />
      {jobError && <div className="error-banner"><XCircle size={17} />{jobError}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Batch</th>
              <th>Created</th>
              <th>Files</th>
              <th>Progress</th>
              <th>State</th>
              <th>Controls</th>
            </tr>
          </thead>
          <tbody>
            {batches.length === 0 ? (
              <tr><td colSpan={6}><EmptyState text="No batches yet." /></td></tr>
            ) : (
              batches.map((batch) => (
                <tr key={batch.id}>
                  <td>
                    <button className="link-button" onClick={() => void inspect(batch.id)}>
                      <code>{batch.id.slice(0, 8)}</code>
                    </button>
                  </td>
                  <td>{new Date(batch.created_at).toLocaleString()}</td>
                  <td>{batch.item_count}</td>
                  <td>{batch.completed_count}/{batch.item_count} complete · {batch.failed_count} failed</td>
                  <td><StatusBadge value={batch.state} /></td>
                  <td>
                    <div className="row-actions">
                      {["QUEUED", "EXTRACTING", "OCR", "PARSING", "EMBEDDING"].includes(batch.state) && (
                        <button className="small-button" onClick={() => void action("pause", batch.id)}><Pause size={14} /> Pause</button>
                      )}
                      {batch.state === "DISCOVERED" && (
                        <button className="small-button" onClick={() => void action("resume", batch.id)}><Play size={14} /> Resume</button>
                      )}
                      {batch.state.startsWith("FAILED") && (
                        <button className="small-button" onClick={() => void action("retry", batch.id)}><RotateCcw size={14} /> Retry</button>
                      )}
                      {!["COMPLETED", "CANCELLED", "FAILED_RETRYABLE", "FAILED_TERMINAL"].includes(batch.state) && (
                        <button className="small-button danger" onClick={() => void action("cancel", batch.id)}><Square size={13} /> Cancel</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {expanded && (
        <div className="job-inspector">
          <PanelHeader title={`Batch ${expanded.slice(0, 8)} items`} actionLabel="Close" onAction={() => setExpanded(null)} />
          {loading ? (
            <div className="loading-state"><LoaderCircle className="spin" size={18} /> Loading persisted item state…</div>
          ) : (
            items.map((item) => (
              <div className="job-item" key={item.id}>
                <StatusBadge value={item.state} />
                <span title={item.path}>{item.path}</span>
                <small>{item.last_error || `attempts ${item.attempts}`}</small>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------
   Document Inspector View
------------------------------------------------------------------------- */

function DocumentInspector({ document, onClose }: { document: DocumentRecord; onClose: () => void }) {
  const [pages, setPages] = useState<PageRecord[]>([]);
  const [selectedPage, setSelectedPage] = useState(0);
  const [normalized, setNormalized] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setPages([]);
    setSelectedPage(0);
    void api.getPages(document.id)
      .then((pageResult) => {
        if (!active) return;
        setPages(pageResult);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load document pages");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [document.id]);

  const page = pages[selectedPage];

  return (
    <div className="inspector-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="document-inspector" aria-label="Document inspector">
        <div className="inspector-header">
          <div>
            <span className="eyebrow">Document Inspection</span>
            <h2>{document.title || document.filename}</h2>
            <code>{document.source_path}</code>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close document inspector"><XCircle size={18} /></button>
        </div>

        <div className="inspector-meta">
          <StatusBadge value={document.document_type} />
          <span>{document.page_count} pages</span>
          <span>SHA-256 {document.sha256.slice(0, 18)}…</span>
        </div>

        {loading ? (
          <div className="loading-state"><LoaderCircle className="spin" size={18} /> Loading document pages…</div>
        ) : error ? (
          <div className="error-banner"><XCircle size={17} />{error}</div>
        ) : (
          <div className="pages-layout">
            <div className="page-list">
              {pages.map((item, index) => (
                <button
                  key={item.id}
                  className={index === selectedPage ? "page-button active" : "page-button"}
                  onClick={() => setSelectedPage(index)}
                >
                  <span>Page {item.page_number}</span>
                  <small>{item.extraction_method} · {item.normalized_text.length} chars</small>
                </button>
              ))}
            </div>
            <div className="page-content">
              <div className="page-toolbar">
                <span>Page {page?.page_number ?? "—"}</span>
                <label>
                  <input type="checkbox" checked={normalized} onChange={(event) => setNormalized(event.target.checked)} /> Normalized text
                </label>
              </div>
              <pre>{normalized ? page?.normalized_text : page?.raw_text}</pre>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Search View
------------------------------------------------------------------------- */

function SearchView() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      setResult(await api.search(query.trim(), mode));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Search failed");
    } finally {
      setSearching(false);
    }
  };

  return (
    <section className="search-layout">
      <div className="search-bar panel">
        <Search size={19} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void runSearch(); }}
          placeholder="Search any document by text, keywords, entities, or conceptual questions…"
        />
        <select value={mode} onChange={(event) => setMode(event.target.value as SearchMode)}>
          <option value="hybrid">Hybrid (FTS + Vector)</option>
          <option value="lexical">Lexical (FTS)</option>
          <option value="semantic">Semantic (pgvector)</option>
        </select>
        <button className="primary-button" onClick={() => void runSearch()} disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </button>
      </div>

      {error && <div className="error-banner"><XCircle size={17} />{error}</div>}

      {result && (
        <div className="search-meta">
          <span>{result.hits.length} provenance-backed result{result.hits.length === 1 ? "" : "s"}</span>
          <span>Mode: <strong>{result.mode}</strong></span>
          <span>Embedding: <strong>{result.embedding_status}</strong></span>
        </div>
      )}

      <div className="result-list">
        {result?.hits.map((hit) => (
          <article className="result-card" key={hit.chunk_id}>
            <div className="result-card-top">
              <StatusBadge value={hit.document_type} />
              <span>Pages {hit.page_start}–{hit.page_end}</span>
              <span>Score {hit.fused_score.toFixed(4)}</span>
            </div>
            <p>{hit.text}</p>
            <div className="result-source">
              <span>{hit.section_label || hit.paragraph_number || "Source passage"}</span>
              <code>{hit.source_path}</code>
            </div>
          </article>
        ))}
        {result && result.hits.length === 0 && <EmptyState text="No results matched the query." />}
        {!result && (
          <div className="search-empty">
            <Search size={34} />
            <h3>Search across all ingested PDFs</h3>
            <p>Full-text keyword indexing and dense neural pgvector embeddings power accurate semantic retrieval.</p>
          </div>
        )}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
   Database View & Table Explorer
------------------------------------------------------------------------- */

function DatabaseView({ setup, documents }: { setup: HealthComponent[]; documents: DocumentRecord[] }) {
  const [tables, setTables] = useState<DatabaseTable[]>([]);
  const [selectedKey, setSelectedKey] = useState("extracted_tables");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTables = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getDatabaseOverview();
      setTables(result.tables);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Database viewer unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTables();
  }, [loadTables]);

  const selected = tables.find((table) => table.key === selectedKey) ?? tables[0];

  return (
    <section className="database-layout">
      <div className="content-grid">
        <div className="panel large-panel">
          <PanelHeader title="Subsystem Health" />
          {setup.map((item) => <HealthRow key={item.name} item={item} />)}
        </div>
        <div className="panel">
          <PanelHeader title="Canonical Counts" />
          <div className="count-list">
            <div><span>Documents</span><strong>{documents.length}</strong></div>
            <div><span>PostgreSQL Tables</span><strong>{tables.length}</strong></div>
            <div><span>Database Engine</span><StatusBadge value="POSTGRESQL 16" /></div>
          </div>
        </div>
      </div>

      <div className="panel database-browser">
        <div className="panel-header">
          <div>
            <h3>PostgreSQL Tables Browser</h3>
            <p className="panel-intro">Live view of internal PostgreSQL relational tables.</p>
          </div>
          <button className="icon-button" onClick={() => void loadTables()} title="Refresh"><RefreshCw size={16} /></button>
        </div>
        {loading && <div className="loading-state"><LoaderCircle className="spin" size={18} /> Loading tables…</div>}
        {error && <div className="error-banner"><XCircle size={17} />{error}</div>}
        {!loading && !error && (
          <>
            <div className="database-tabs">
              {tables.map((table) => (
                <button key={table.key} className={selected?.key === table.key ? "active" : ""} onClick={() => setSelectedKey(table.key)}>
                  {table.label}<span>{table.count}</span>
                </button>
              ))}
            </div>
            {selected && (
              <>
                <div className="database-table-meta">
                  <span>{selected.count} total rows · showing preview of {selected.rows.length}</span>
                </div>
                {selected.rows.length === 0 ? (
                  <EmptyState text="This table is currently empty." />
                ) : (
                  <div className="table-wrap database-table">
                    <table>
                      <thead>
                        <tr>
                          {selected.columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {selected.rows.map((row, index) => (
                          <tr key={`${selected.key}-${String(row.id ?? index)}`}>
                            {selected.columns.map((column) => (
                              <td key={column} title={String(row[column] ?? "—")}>
                                {row[column] == null ? "—" : String(row[column])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function formatCell(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function TableExplorerView({ onOpenRow }: { onOpenRow: (tableKey: string, rowId: string, field: string) => void }) {
  const [tables, setTables] = useState<DatabaseTable[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [table, setTable] = useState<DatabaseTablePage | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wrapCells, setWrapCells] = useState(false);
  const pageSize = 200;

  useEffect(() => {
    void api.getDatabaseOverview()
      .then((result) => {
        setTables(result.tables);
        setSelectedKey((current) => current || result.tables[0]?.key || "");
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Table list unavailable"));
  }, []);

  useEffect(() => {
    if (!selectedKey) return;
    setLoading(true);
    void api.getDatabaseTable(selectedKey, offset, pageSize)
      .then((result) => {
        setTable(result);
        setError(null);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Table unavailable"))
      .finally(() => setLoading(false));
  }, [offset, selectedKey]);

  const selectTable = (key: string) => { setSelectedKey(key); setOffset(0); };
  const totalPages = table ? Math.max(1, Math.ceil(table.count / pageSize)) : 1;
  const currentPage = table ? Math.floor(table.offset / pageSize) + 1 : 1;

  return (
    <section className="table-explorer-layout">
      <div className="panel explorer-heading">
        <div>
          <span className="hero-kicker">PostgreSQL Schema Browser</span>
          <h2>Table Explorer</h2>
          <p>Inspect raw underlying PostgreSQL tables directly.</p>
        </div>
        <div className="explorer-badge">
          <Table2 size={22} />
          <strong>{tables.length}</strong>
          <span>tables</span>
        </div>
      </div>

      <div className="panel spreadsheet-panel">
        <div className="panel-header">
          <div>
            <h3>Data Grid</h3>
            <p className="panel-intro">Rows {table ? `${table.offset + 1}–${Math.min(table.offset + table.rows.length, table.count)} of ${table.count}` : "—"}</p>
          </div>
          <label className="wrap-toggle">
            <input type="checkbox" checked={wrapCells} onChange={(e) => setWrapCells(e.target.checked)} /> Wrap long cells
          </label>
        </div>

        <div className="database-tabs explorer-tabs">
          {tables.map((item) => (
            <button key={item.key} className={selectedKey === item.key ? "active" : ""} onClick={() => selectTable(item.key)}>
              {item.label}<span>{item.count}</span>
            </button>
          ))}
        </div>

        {error && <div className="error-banner"><XCircle size={17} />{error}</div>}
        {loading && <div className="loading-state"><LoaderCircle className="spin" size={18} /> Loading table page…</div>}

        {!loading && table && (
          <>
            <div className="spreadsheet-scroll">
              <table className={wrapCells ? "spreadsheet-table wrap-cells" : "spreadsheet-table"}>
                <thead>
                  <tr>
                    <th className="row-number-header">#</th>
                    {table.columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.length === 0 ? (
                    <tr><td colSpan={table.columns.length + 1}><EmptyState text="This table is empty." /></td></tr>
                  ) : (
                    table.rows.map((row, index) => (
                      <tr key={`${table.key}-${String(row.id ?? index)}`}>
                        <td className="row-number">{table.offset + index + 1}</td>
                        {table.columns.map((column) => (
                          <td key={column} title={formatCell(row[column])}>
                            {row.id ? (
                              <button className="cell-button" onClick={() => onOpenRow(table.key, String(row.id), column)}>
                                {formatCell(row[column])}
                              </button>
                            ) : (
                              formatCell(row[column])
                            )}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="spreadsheet-footer">
              <span>Page {currentPage} of {totalPages}</span>
              <div>
                <button className="small-button" onClick={() => setOffset(Math.max(0, offset - pageSize))} disabled={offset === 0}>
                  Previous
                </button>
                <button className="small-button" onClick={() => setOffset(offset + pageSize)} disabled={!table || offset + table.rows.length >= table.count}>
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function TableRowDetailView({ selection, onBack }: { selection: { tableKey: string; rowId: string; field: string }; onBack: () => void }) {
  const [record, setRecord] = useState<DatabaseRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.getDatabaseRecord(selection.tableKey, selection.rowId).then(setRecord)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Record unavailable"));
  }, [selection.rowId, selection.tableKey]);

  return (
    <section className="table-detail-layout">
      <button className="secondary-button" onClick={onBack}><ArrowUpRight size={15} /> Back to table</button>
      {error && <div className="error-banner"><XCircle size={17} />{error}</div>}
      {!record && !error && <div className="loading-state"><LoaderCircle className="spin" size={18} /> Loading row detail…</div>}
      {record && (
        <>
          <div className="panel detail-heading">
            <div>
              <span className="hero-kicker">{record.label} / Selected Row</span>
              <h2>{selection.field.replaceAll("_", " ")}</h2>
            </div>
            <code>{record.row_id}</code>
          </div>
          <div className="content-grid">
            <div className="panel">
              <PanelHeader title="Row Values" />
              <div className="detail-field-list">
                {record.columns.map((column) => (
                  <div className={column === selection.field ? "detail-field active" : "detail-field"} key={column}>
                    <span>{column.replaceAll("_", " ")}</span>
                    <strong>{formatCell(record.row[column])}</strong>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel">
              <PanelHeader title="Provenance" />
              <div className="detail-field-list">
                {Object.entries(record.provenance).map(([key, value]) => (
                  <div className="detail-field" key={key}>
                    <span>{key.replaceAll("_", " ")}</span>
                    <strong>{formatCell(value)}</strong>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------
   Settings View (Groq AI & System Settings)
------------------------------------------------------------------------- */

function SettingsView({ setup, onResetAll }: { setup: HealthComponent[]; onResetAll?: () => Promise<void> }) {
  const [groqConfig, setGroqConfig] = useState<GroqConfig | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("qwen/qwen3.8-27b");
  const [savingGroq, setSavingGroq] = useState(false);
  const [groqMessage, setGroqMessage] = useState<string | null>(null);

  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const [resetting, setResetting] = useState(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  const handleResetAll = async () => {
    if (!confirm("Are you sure you want to wipe ALL uploaded documents, extracted tables, and records? This action cannot be undone.")) return;
    setResetting(true);
    setResetMsg(null);
    try {
      const res = await api.resetAllData();
      setResetMsg(res.message);
      if (onResetAll) await onResetAll();
    } catch (err) {
      setResetMsg(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setResetting(false);
    }
  };

  useEffect(() => {
    void api.getGroqConfig().then((cfg) => {
      setGroqConfig(cfg);
      setModel(cfg.model);
    }).catch(() => {});
  }, []);

  const saveGroq = async () => {
    setSavingGroq(true);
    setGroqMessage(null);
    try {
      const updated = await api.updateGroqConfig(apiKey ? apiKey : undefined, model);
      setGroqConfig(updated);
      setGroqMessage("Groq AI settings saved and active!");
      setApiKey("");
    } catch (err) {
      setGroqMessage(err instanceof Error ? err.message : "Failed to update Groq settings");
    } finally {
      setSavingGroq(false);
    }
  };

  const backfill = async () => {
    setWorking(true);
    setMessage(null);
    try {
      const result = await api.backfillEmbeddings(100);
      setMessage(`${result.embedded} missing embeddings created with ${result.model} (${result.dimension} dimensions).`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Embedding backfill failed");
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="settings-grid">
      <div className="panel">
        <PanelHeader title="Groq AI Universal Document Intelligence" />
        <p className="panel-intro">
          Groq LLM extracts schema, classifies document types, and turns unstructured PDF content into relational database tables.
        </p>

        <div className="settings-list">
          <div>
            <span>Groq LLM Status</span>
            <StatusBadge value={groqConfig?.configured ? "CONNECTED" : "KEY REQUIRED"} />
          </div>
        </div>

        <div style={{ marginTop: "18px", display: "grid", gap: "12px" }}>
          <div className="form-field">
            <label>Active Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {groqConfig?.available_models.map((m) => (
                <option key={m} value={m}>{m}</option>
              )) ?? (
                <>
                  <option value="qwen/qwen3.8-27b">qwen/qwen3.8-27b (Recommended)</option>
                  <option value="openai/gpt-oss-120b">openai/gpt-oss-120b</option>
                  <option value="openai/gpt-oss-20b">openai/gpt-oss-20b</option>
                </>
              )}
            </select>
          </div>

          <div className="form-field">
            <label>Update Groq API Key (leave empty to keep current)</label>
            <input
              type="password"
              placeholder="gsk_..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          <button className="primary-button" onClick={() => void saveGroq()} disabled={savingGroq}>
            <Sparkles size={15} /> {savingGroq ? "Saving…" : "Save Groq AI Settings"}
          </button>
          {groqMessage && <div className="inline-message">{groqMessage}</div>}
        </div>
      </div>

      <div className="panel">
        <PanelHeader title="Vector Embeddings & Subsystems" />
        <div className="settings-list">
          <div><span>Backend endpoint</span><code>127.0.0.1:8765</code></div>
          <div><span>Database</span><strong>PostgreSQL 16 + pgvector</strong></div>
          <div>
            <span>Embedding provider</span>
            <strong>{setup.find((item) => item.name === "Embedding subsystem")?.detail || "Local SentenceTransformers"}</strong>
          </div>
        </div>

        <button className="secondary-button full-width" style={{ marginTop: "18px" }} onClick={() => void backfill()} disabled={working}>
          {working ? "Backfilling…" : "Retry / Backfill Embeddings"}
        </button>
        {message && <div className="inline-message">{message}</div>}
      </div>

      <div className="panel" style={{ border: "1px solid rgba(220, 53, 69, 0.4)" }}>
        <PanelHeader title="Danger Zone / Reset Database" />
        <p className="panel-intro">
          Delete all uploaded documents, extracted tables, and records to start completely fresh.
        </p>
        <button
          className="secondary-button danger-button full-width"
          style={{ marginTop: "18px" }}
          onClick={() => void handleResetAll()}
          disabled={resetting}
        >
          <Trash2 size={15} /> {resetting ? "Resetting Database…" : "Reset All Database Records"}
        </button>
        {resetMsg && <div className="inline-message">{resetMsg}</div>}
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state"><span>{text}</span></div>;
}

export default App;
