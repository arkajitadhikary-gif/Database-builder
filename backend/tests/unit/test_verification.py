from types import SimpleNamespace

import pytest

import app.services.verification as verification


def test_transfer_mode_is_local_only_for_loopback() -> None:
    assert verification._transfer_mode("http://127.0.0.1:8000/v1") == "local"
    assert verification._transfer_mode("http://localhost:8000/v1") == "local"
    assert verification._transfer_mode("https://integrate.api.nvidia.com/v1") == "hosted"


def test_candidate_hash_is_stable() -> None:
    candidate = {"filename": "act.pdf", "pages": [{"page": 1, "text": "Section 1"}]}
    assert verification._sha256_payload(candidate) == verification._sha256_payload(candidate)
    assert len(verification._sha256_payload(candidate)) == 64


@pytest.mark.asyncio
async def test_hosted_verification_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(
        verification,
        "get_settings",
        lambda: SimpleNamespace(
            ai_nim_base_url="https://integrate.api.nvidia.com/v1",
            ai_nim_hosted_allowed=False,
            ai_verification_model="nvidia/test",
        ),
    )
    result = await verification.NvidiaNimVerifier().verify({"pages": []})
    assert result.status == "ERROR"
    assert result.transfer_mode == "hosted"
    assert "disabled" in (result.error_message or "")
