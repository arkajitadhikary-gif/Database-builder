# Database Builder

**Database Builder** is an intelligent, universal, local-first engine and spreadsheet studio that converts any document or PDF (invoices, research papers, financial statements, catalogs, logs, forms, official records, legal contracts, reports, etc.) into durable, structured, multi-table relational databases in PostgreSQL.

With integrated **Groq Llama 3 AI extraction**, it automatically identifies the document category, determines the domain schema, designs clean normalized tables, and extracts every row and column with high fidelity. You can inspect, edit, filter, and export the resulting tables instantly as **SQL DDL + Inserts**, **Excel-ready CSV (UTF-8 BOM)**, or **JSON**.

---

## Key Highlights

- **Universal PDF & Document Intelligence**: No longer bound to any single document category. Handles invoices, medical records, financial statements, technical datasheets, surveys, and research documents automatically.
- **Groq Llama 3 Fast Extraction**: High-speed, high-accuracy structured data extraction with intelligent type inference (`string`, `number`, `boolean`, `date`, `currency`).
- **Interactive Spreadsheet Studio**:
  - Full-fidelity table viewer with column headers, data types, and row indices.
  - Cell editing, manual row addition, and instant row deletion.
  - Multi-table tabs for complex PDFs containing multiple extracted structures.
  - Quick table deletion and batch document deletion with zero lag.
  - Collapsible responsive sidebar for maximized workspace view.
- **Developer-Grade Exports**:
  - **SQL**: Production-ready PostgreSQL DDL (`DROP TABLE`, `CREATE TABLE` with typed columns) and batch `INSERT INTO` statements.
  - **CSV**: Excel-compliant UTF-8 with BOM support for seamless viewing without encoding issues.
  - **JSON**: Clean, structured key-value arrays with full provenance.
- **Local-First & Privacy-Focused**: Source documents stay on your machine. Data is stored directly into your local PostgreSQL database with complete provenance tracking (page numbers and original files).

---

## Repository Layout

| Directory / File | Description |
| --- | --- |
| `backend/app/api` | FastAPI REST API endpoints (documents, universal tables, live exports, health) |
| `backend/app/services` | Groq AI extraction engine, PyMuPDF parsers, OCR, chunking, retrieval |
| `backend/app/db` | SQLAlchemy asynchronous models, PostgreSQL session management |
| `backend/alembic` | Alembic migrations for database schema and pgvector support |
| `frontend/src` | React + TypeScript + Vite UI with modern Spreadsheet Studio |
| `src-tauri` | Tauri 2 desktop shell configuration |
| `docker-compose.yml` | Isolated local PostgreSQL 16 container with `pgvector` |

---

## Quick Start Guide

### 1. Start the PostgreSQL Database

Using Docker Desktop:

```powershell
docker compose up -d postgres
```

This starts PostgreSQL on `127.0.0.1:55432` with user `postgres` and database `judicore_hardened`.

---

### 2. Configure Environment Variables

Create `.env` inside the `backend` folder (or copy from `.env.example`):

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/judicore_hardened
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

> **Tip:** You can obtain a free Groq API key at [console.groq.com](https://console.groq.com).

---

### 3. Run the Backend

```powershell
cd backend
uv sync --dev
uv run alembic upgrade head
uv run python run.py --host 127.0.0.1 --port 8765
```

The backend API will start at `http://127.0.0.1:8765`.
- Health check: `GET http://127.0.0.1:8765/api/v1/health`
- Interactive API docs: `http://127.0.0.1:8765/docs`

---

### 4. Run the Frontend

In a separate terminal:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open your browser at `http://localhost:1420` to access the **Database Builder** Dashboard and Spreadsheet Studio.

---

### 5. Automated Scripts (Windows)

You can also use the root scripts for convenient one-click startup and shutdown:

- **Start**: `.\start_judicore.bat` or `.\start_judicore.ps1`
- **Stop**: `.\stop_judicore.bat` or `.\stop_judicore.ps1`

---

## How It Works

1. **Upload Documents**: Drag and drop any PDF file in the Dashboard or select via the file dialog.
2. **AI Understanding**: The backend parses the PDF text/pages and uses Groq Llama 3 to classify the document type and construct normalized tabular representations.
3. **Spreadsheet Studio**:
   - Browse tables in the sidebar grouped by document.
   - Filter, inspect, and add or delete rows.
   - Re-extract anytime with adjusted prompts if needed.
4. **Export**:
   - Click **Export SQL** to generate a `.sql` script ready to run in any database tool (pgAdmin, DBeaver, psql).
   - Click **Export CSV** for Excel and spreadsheet workflows.
   - Click **Export JSON** for programmatic API and pipeline integration.

---

## License

Open source and community friendly.
