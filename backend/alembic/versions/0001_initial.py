"""Frozen initial Judicore PostgreSQL schema. Generated once; do not derive at runtime."""
# ruff: noqa: E501

import os

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    bind.exec_driver_sql(
        "DO $$ BEGIN CREATE TYPE document_type AS ENUM ('BARE_ACT', 'RULE', 'REGULATION', 'NOTIFICATION', 'CIRCULAR', 'ORDER', 'SUPREME_COURT_JUDGMENT', 'HIGH_COURT_JUDGMENT', 'TRIBUNAL_DECISION', 'OTHER_LEGAL_DOCUMENT', 'UNKNOWN'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;\n"
    )
    bind.exec_driver_sql(
        "DO $$ BEGIN CREATE TYPE ingestion_state AS ENUM ('DISCOVERED', 'VALIDATING', 'QUEUED', 'EXTRACTING', 'OCR', 'NORMALIZING', 'CLASSIFYING', 'PARSING', 'CHUNKING', 'STORING', 'INDEXING_TEXT', 'EMBEDDING', 'VALIDATING_RESULT', 'COMPLETED', 'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'SKIPPED_DUPLICATE', 'SKIPPED_UNSUPPORTED', 'CANCELLED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;\n"
    )
    bind.exec_driver_sql(
        "DO $$ BEGIN CREATE TYPE duplicate_kind AS ENUM ('EXACT_DUPLICATE', 'CONTENT_DUPLICATE', 'POSSIBLE_VERSION', 'NEW_VERSION', 'NEW_DOCUMENT'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;\n"
    )
    bind.exec_driver_sql(
        "DO $$ BEGIN CREATE TYPE extraction_method AS ENUM ('TEXT', 'OCR', 'MIXED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;\n"
    )
    bind.exec_driver_sql(
        "DO $$ BEGIN CREATE TYPE resolution_status AS ENUM ('RESOLVED', 'AMBIGUOUS', 'UNRESOLVED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE ingestion_batches (\n\tid UUID NOT NULL, \n\tstate ingestion_state NOT NULL, \n\trequested_paths JSONB NOT NULL, \n\trecursive BOOLEAN NOT NULL, \n\tpause_requested BOOLEAN NOT NULL, \n\tcancel_requested BOOLEAN NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE judges (\n\tid UUID NOT NULL, \n\tname TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (name)\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE sources (\n\tid UUID NOT NULL, \n\tpath TEXT NOT NULL, \n\tstorage_mode VARCHAR(32) NOT NULL, \n\tarchived_path TEXT, \n\tsource_exists BOOLEAN NOT NULL, \n\tlast_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (path)\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE system_settings (\n\tkey VARCHAR(128) NOT NULL, \n\tvalue JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (key)\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE documents (\n\tid UUID NOT NULL, \n\tsource_id UUID NOT NULL, \n\tfilename TEXT NOT NULL, \n\tsha256 VARCHAR(64) NOT NULL, \n\tnormalized_text_hash VARCHAR(64), \n\tbyte_size BIGINT NOT NULL, \n\tpage_count INTEGER NOT NULL, \n\tdocument_type document_type NOT NULL, \n\tclassification_method VARCHAR(64), \n\tclassification_confidence FLOAT, \n\ttitle TEXT, \n\tdocument_date DATE, \n\tmetadata JSONB NOT NULL, \n\tmissing_source BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_documents_sha256 UNIQUE (sha256), \n\tCONSTRAINT ck_documents_byte_size_positive CHECK (byte_size > 0), \n\tCONSTRAINT ck_documents_page_count_positive CHECK (page_count > 0), \n\tCONSTRAINT ck_documents_classification_confidence_range CHECK (classification_confidence IS NULL OR classification_confidence BETWEEN 0 AND 1), \n\tFOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE RESTRICT\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE acts (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tname TEXT, \n\tyear INTEGER, \n\tshort_title TEXT, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_acts_document UNIQUE (document_id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE chunks (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tchunk_index INTEGER NOT NULL, \n\ttext TEXT NOT NULL, \n\tnormalized_text TEXT NOT NULL, \n\tdocument_type document_type NOT NULL, \n\tsection_label VARCHAR(128), \n\tparagraph_number VARCHAR(64), \n\tpage_start INTEGER NOT NULL, \n\tpage_end INTEGER NOT NULL, \n\tsource_path TEXT NOT NULL, \n\tchar_count INTEGER NOT NULL, \n\ttoken_count INTEGER NOT NULL, \n\tsearch_tsv TSVECTOR, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_chunks_document_index UNIQUE (document_id, chunk_index), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE document_versions (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\trelated_document_id UUID NOT NULL, \n\trelation VARCHAR(32) NOT NULL, \n\tevidence JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_document_version_pair UNIQUE (document_id, related_document_id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, \n\tFOREIGN KEY(related_document_id) REFERENCES documents (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE duplicates (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\trelated_document_id UUID NOT NULL, \n\tkind duplicate_kind NOT NULL, \n\tevidence JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_duplicate_pair UNIQUE (document_id, related_document_id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, \n\tFOREIGN KEY(related_document_id) REFERENCES documents (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE ingestion_items (\n\tid UUID NOT NULL, \n\tbatch_id UUID NOT NULL, \n\tpath TEXT NOT NULL, \n\tstate ingestion_state NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tlocked_at TIMESTAMP WITH TIME ZONE, \n\tlast_error TEXT, \n\tdocument_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_ingestion_items_batch_path UNIQUE (batch_id, path), \n\tFOREIGN KEY(batch_id) REFERENCES ingestion_batches (id) ON DELETE CASCADE, \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE SET NULL\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE judgments (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tcase_title TEXT, \n\tcourt TEXT, \n\tcase_number TEXT, \n\tdecision_date DATE, \n\tcoram_text TEXT, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_judgments_document UNIQUE (document_id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE pages (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tpage_number INTEGER NOT NULL, \n\traw_text TEXT NOT NULL, \n\tnormalized_text TEXT NOT NULL, \n\textraction_method extraction_method NOT NULL, \n\ttext_start_offset INTEGER, \n\ttext_end_offset INTEGER, \n\tocr_engine VARCHAR(128), \n\tocr_confidence FLOAT, \n\twarnings JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_pages_document_page UNIQUE (document_id, page_number), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        '\nCREATE TABLE "references" (\n\tid UUID NOT NULL, \n\tdocument_id UUID NOT NULL, \n\tsource_text TEXT NOT NULL, \n\treference_type VARCHAR(32) NOT NULL, \n\tnormalized_key TEXT, \n\tresolution_status resolution_status NOT NULL, \n\ttarget_document_id UUID, \n\tpage_start INTEGER NOT NULL, \n\tpage_end INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, \n\tFOREIGN KEY(target_document_id) REFERENCES documents (id) ON DELETE SET NULL\n)\n'
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE embeddings (\n\tid UUID NOT NULL, \n\tchunk_id UUID NOT NULL, \n\tprovider VARCHAR(64) NOT NULL, \n\tmodel VARCHAR(255) NOT NULL, \n\tversion VARCHAR(64) NOT NULL, \n\tdimension INTEGER NOT NULL, \n\tvector VECTOR(384) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_embeddings_chunk_model UNIQUE (chunk_id, provider, model), \n\tFOREIGN KEY(chunk_id) REFERENCES chunks (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE ingestion_errors (\n\tid UUID NOT NULL, \n\titem_id UUID NOT NULL, \n\tstage ingestion_state NOT NULL, \n\terror_type VARCHAR(255) NOT NULL, \n\tmessage TEXT NOT NULL, \n\tretryable BOOLEAN NOT NULL, \n\tdetails JSONB NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(item_id) REFERENCES ingestion_items (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE judgment_judges (\n\tjudgment_id UUID NOT NULL, \n\tjudge_id UUID NOT NULL, \n\trole VARCHAR(64), \n\tPRIMARY KEY (judgment_id, judge_id), \n\tFOREIGN KEY(judgment_id) REFERENCES judgments (id) ON DELETE CASCADE, \n\tFOREIGN KEY(judge_id) REFERENCES judges (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE judgment_paragraphs (\n\tid UUID NOT NULL, \n\tjudgment_id UUID NOT NULL, \n\tofficial_number VARCHAR(64), \n\tinternal_sequence INTEGER NOT NULL, \n\ttext TEXT NOT NULL, \n\tpage_start INTEGER NOT NULL, \n\tpage_end INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_judgment_paragraph_sequence UNIQUE (judgment_id, internal_sequence), \n\tFOREIGN KEY(judgment_id) REFERENCES judgments (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE legal_parts (\n\tid UUID NOT NULL, \n\tact_id UUID NOT NULL, \n\tlabel VARCHAR(128) NOT NULL, \n\ttitle TEXT, \n\tpage_start INTEGER NOT NULL, \n\tpage_end INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(act_id) REFERENCES acts (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE parties (\n\tid UUID NOT NULL, \n\tjudgment_id UUID NOT NULL, \n\tname TEXT NOT NULL, \n\tside VARCHAR(64), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(judgment_id) REFERENCES judgments (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE stage_events (\n\tid UUID NOT NULL, \n\titem_id UUID NOT NULL, \n\tstage ingestion_state NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tdetails JSONB NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(item_id) REFERENCES ingestion_items (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE legal_chapters (\n\tid UUID NOT NULL, \n\tpart_id UUID NOT NULL, \n\tlabel VARCHAR(128) NOT NULL, \n\ttitle TEXT, \n\tpage_start INTEGER NOT NULL, \n\tpage_end INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(part_id) REFERENCES legal_parts (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE legal_sections (\n\tid UUID NOT NULL, \n\tact_id UUID NOT NULL, \n\tparent_section_id UUID, \n\tpart_id UUID, \n\tchapter_id UUID, \n\tlabel VARCHAR(128) NOT NULL, \n\theading TEXT, \n\ttext TEXT NOT NULL, \n\tpage_start INTEGER NOT NULL, \n\tpage_end INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_legal_sections_act_label UNIQUE (act_id, label), \n\tFOREIGN KEY(act_id) REFERENCES acts (id) ON DELETE CASCADE, \n\tFOREIGN KEY(parent_section_id) REFERENCES legal_sections (id) ON DELETE CASCADE, \n\tFOREIGN KEY(part_id) REFERENCES legal_parts (id) ON DELETE SET NULL, \n\tFOREIGN KEY(chapter_id) REFERENCES legal_chapters (id) ON DELETE SET NULL\n)\n"
    )
    bind.exec_driver_sql(
        "\nCREATE TABLE legal_nodes (\n\tid UUID NOT NULL, \n\tsection_id UUID NOT NULL, \n\tnode_type VARCHAR(32) NOT NULL, \n\tlabel VARCHAR(128), \n\ttext TEXT NOT NULL, \n\tpage_start INTEGER NOT NULL, \n\tpage_end INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(section_id) REFERENCES legal_sections (id) ON DELETE CASCADE\n)\n"
    )
    bind.exec_driver_sql(
        "CREATE INDEX ix_documents_normalized_text_hash ON documents (normalized_text_hash)\n"
    )
    bind.exec_driver_sql("CREATE INDEX ix_documents_type ON documents (document_type)\n")
    bind.exec_driver_sql("CREATE INDEX ix_chunks_document_type ON chunks (document_type)\n")
    bind.exec_driver_sql("CREATE INDEX ix_chunks_search_tsv ON chunks USING gin (search_tsv)\n")
    bind.exec_driver_sql("CREATE INDEX ix_ingestion_items_state ON ingestion_items (state)\n")
    bind.exec_driver_sql(
        "CREATE OR REPLACE FUNCTION judicore_chunks_tsvector_update() RETURNS trigger AS $$\nBEGIN\n  NEW.search_tsv := to_tsvector('simple', coalesce(NEW.normalized_text, ''));\n  RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql\n"
    )
    bind.exec_driver_sql(
        "CREATE TRIGGER trg_chunks_tsvector BEFORE INSERT OR UPDATE OF normalized_text ON chunks FOR EACH ROW EXECUTE FUNCTION judicore_chunks_tsvector_update()"
    )
    bind.exec_driver_sql(
        "UPDATE chunks SET search_tsv = to_tsvector('simple', coalesce(normalized_text, '')) WHERE search_tsv IS NULL"
    )


def downgrade() -> None:
    if os.environ.get("JUDICORE_ALLOW_DESTRUCTIVE_MIGRATIONS") != "YES":
        raise RuntimeError("Destructive downgrade blocked. Restore a verified backup instead.")
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_chunks_tsvector ON chunks")
    bind.exec_driver_sql("DROP FUNCTION IF EXISTS judicore_chunks_tsvector_update()")
    bind.exec_driver_sql("DROP TABLE IF EXISTS legal_nodes CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS legal_sections CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS legal_chapters CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS stage_events CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS parties CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS legal_parts CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS judgment_paragraphs CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS judgment_judges CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS ingestion_errors CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS embeddings CASCADE")
    bind.exec_driver_sql('DROP TABLE IF EXISTS "references" CASCADE')
    bind.exec_driver_sql("DROP TABLE IF EXISTS pages CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS judgments CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS ingestion_items CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS duplicates CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS document_versions CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS chunks CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS acts CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS documents CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS system_settings CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS sources CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS judges CASCADE")
    bind.exec_driver_sql("DROP TABLE IF EXISTS ingestion_batches CASCADE")
    bind.exec_driver_sql("DROP TYPE IF EXISTS resolution_status CASCADE")
    bind.exec_driver_sql("DROP TYPE IF EXISTS extraction_method CASCADE")
    bind.exec_driver_sql("DROP TYPE IF EXISTS duplicate_kind CASCADE")
    bind.exec_driver_sql("DROP TYPE IF EXISTS ingestion_state CASCADE")
    bind.exec_driver_sql("DROP TYPE IF EXISTS document_type CASCADE")
