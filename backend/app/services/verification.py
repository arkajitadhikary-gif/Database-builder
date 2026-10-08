"""Provider-neutral verification for extracted legal document candidates."""

from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class VerificationFinding:
    severity: str
    field_name: str
    message: str
    expected_value: str | None = None
    observed_value: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    confidence: float | None = None
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True)
class VerificationResult:
    provider: str
    model: str
    transfer_mode: str
    status: str
    input_sha256: str
    output: dict[str, Any]
    findings: list[VerificationFinding]
    error_message: str | None = None


class VerificationProvider(Protocol):
    async def verify(self, candidate: dict[str, Any]) -> VerificationResult: ...


def _sha256_payload(candidate: dict[str, Any]) -> str:
    payload = json.dumps(candidate, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _transfer_mode(base_url: str) -> str:
    host = base_url.lower()
    return "local" if "127.0.0.1" in host or "localhost" in host else "hosted"


class NvidiaNimVerifier:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def verify(self, candidate: dict[str, Any]) -> VerificationResult:
        settings = self.settings
        input_sha256 = _sha256_payload(candidate)
        transfer_mode = _transfer_mode(settings.ai_nim_base_url)
        if transfer_mode == "hosted" and not settings.ai_nim_hosted_allowed:
            return VerificationResult(
                "nvidia_nim",
                settings.ai_verification_model,
                transfer_mode,
                "ERROR",
                input_sha256,
                {},
                [],
                "hosted AI verification is disabled by configuration",
            )
        prompt = {
            "task": "Verify a deterministic legal-document extraction without inventing facts.",
            "rules": [
                "Only report a mismatch when the supplied page evidence contradicts the candidate.",
                "Return JSON with keys passed (boolean) and findings (array).",
                (
                    "Every finding must include severity, field_name, message, "
                    "page_start, page_end, confidence."
                ),
            ],
            "candidate": candidate,
        }
        try:
            output = await asyncio.to_thread(self._request, prompt, transfer_mode)
        except Exception as exc:
            return VerificationResult(
                "nvidia_nim",
                settings.ai_verification_model,
                transfer_mode,
                "ERROR",
                input_sha256,
                {},
                [],
                f"{type(exc).__name__}: {exc}"[-4000:],
            )
        findings = [
            VerificationFinding(
                severity=str(item.get("severity", "HIGH")),
                field_name=str(item.get("field_name", "unknown")),
                message=str(item.get("message", "verification finding")),
                expected_value=item.get("expected_value"),
                observed_value=item.get("observed_value"),
                page_start=item.get("page_start"),
                page_end=item.get("page_end"),
                confidence=item.get("confidence"),
                evidence=item.get("evidence") or {},
            )
            for item in output.get("findings", [])
            if isinstance(item, dict)
        ]
        status = "REVIEW_REQUIRED" if findings else "PASSED"
        return VerificationResult(
            "nvidia_nim",
            settings.ai_verification_model,
            transfer_mode,
            status,
            input_sha256,
            output,
            findings,
        )

    def _request(self, prompt: dict[str, Any], transfer_mode: str) -> dict[str, Any]:
        settings = self.settings
        endpoint = f"{settings.ai_nim_base_url.rstrip('/')}/chat/completions"
        body = json.dumps(
            {
                "model": settings.ai_verification_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a strict legal data quality verifier. "
                            "Return JSON only."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if settings.ai_nim_api_key:
            headers["Authorization"] = f"Bearer {settings.ai_nim_api_key}"
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("verification provider returned a non-object JSON response")
        return parsed


def get_verification_provider() -> VerificationProvider:
    settings = get_settings()
    if settings.ai_verification_provider != "nvidia_nim":
        raise RuntimeError(
            f"unsupported AI verification provider: {settings.ai_verification_provider}"
        )
    return NvidiaNimVerifier()
