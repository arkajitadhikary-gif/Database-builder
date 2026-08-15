from __future__ import annotations

import re
from dataclasses import dataclass

from app.db.models import DocumentType

_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_PAGE_BREAK_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class Classification:
    document_type: DocumentType
    method: str
    confidence: float
    signals: list[str]


def normalize_text(raw_text: str) -> str:
    text = raw_text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(_WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    return _PAGE_BREAK_RE.sub("\n\n", text).strip()


def classify_document(text: str, filename: str = "") -> Classification:
    sample = f"{filename}\n{text[:12000]}".casefold()
    scores: dict[DocumentType, tuple[float, list[str]]] = {
        DocumentType.BARE_ACT: (0.0, []),
        DocumentType.RULE: (0.0, []),
        DocumentType.REGULATION: (0.0, []),
        DocumentType.NOTIFICATION: (0.0, []),
        DocumentType.CIRCULAR: (0.0, []),
        DocumentType.ORDER: (0.0, []),
        DocumentType.SUPREME_COURT_JUDGMENT: (0.0, []),
        DocumentType.HIGH_COURT_JUDGMENT: (0.0, []),
        DocumentType.TRIBUNAL_DECISION: (0.0, []),
        DocumentType.OTHER_LEGAL_DOCUMENT: (0.0, []),
        DocumentType.UNKNOWN: (0.0, []),
    }

    def add(kind: DocumentType, score: float, signal: str) -> None:
        current, signals = scores[kind]
        scores[kind] = (current + score, [*signals, signal])

    if re.search(r"\bact\s+\d{4}\b|\bact\b", sample):
        add(DocumentType.BARE_ACT, 0.55, "act marker")
    if "rules" in sample or re.search(r"\brule\s+\d+", sample):
        add(DocumentType.RULE, 0.45, "rule marker")
    if "regulations" in sample or "regulation" in sample:
        add(DocumentType.REGULATION, 0.45, "regulation marker")
    if "notification" in sample:
        add(DocumentType.NOTIFICATION, 0.5, "notification marker")
    if "circular" in sample:
        add(DocumentType.CIRCULAR, 0.5, "circular marker")
    if "order" in sample:
        add(DocumentType.ORDER, 0.3, "order marker")
    if "supreme court" in sample:
        add(DocumentType.SUPREME_COURT_JUDGMENT, 0.85, "supreme court marker")
    if "high court" in sample:
        add(DocumentType.HIGH_COURT_JUDGMENT, 0.8, "high court marker")
    if "tribunal" in sample or "bench" in sample:
        add(DocumentType.TRIBUNAL_DECISION, 0.45, "tribunal/bench marker")
    if re.search(r"\bjudgment\b|\bjudgement\b|\bpetition\b|\bappellant\b", sample):
        add(DocumentType.OTHER_LEGAL_DOCUMENT, 0.4, "judgment marker")

    ranked = sorted(scores.items(), key=lambda pair: pair[1][0], reverse=True)
    best_type, (best_score, signals) = ranked[0]
    if best_score <= 0:
        return Classification(DocumentType.UNKNOWN, "deterministic-signals-v1", 0.0, [])
    confidence = min(0.99, round(best_score, 2))
    return Classification(best_type, "deterministic-signals-v1", confidence, signals)
