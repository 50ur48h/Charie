"""Read office documents through Azure Document Intelligence (05, 08).

Prebuilt Layout returns markdown; timeouts surface as a plain error.
Saved replays are reused without touching Azure; real calls use
persistent cost accounting.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_chain,
    wait_fixed,
)

from charie.shared.ai.client import BACKOFFS, MAX_RETRIES
from charie.shared.ai.cost_log import DbCostLog, MemoryCostLog, usage_row
from charie.shared.ai.errors import (
    AiApiError,
    AiError,
    AiReplayMissing,
    AiUnavailable,
    SpendingPaused,
)
from charie.shared.ai.replay import ReplayStore, default_dir
from charie.shared.ai.spending import spending_state
from charie.shared.config import get_settings

MODEL = "prebuilt-layout"
LAYOUT_USD_PER_PAGE = Decimal("0.01")  # $10 per 1,000 pages, list price.
JOB = "read_document"


@dataclass(frozen=True)
class DocumentText:
    """One document as markdown plus its page count and cost."""

    filename: str
    markdown: str
    page_count: int
    cost_usd: Decimal


def read_document(
    data: bytes,
    *,
    filename: str,
    provider: str = "azure",
    endpoint: str | None = None,
    key: str | None = None,
    app: str = "learner",
    cost_log: Any = None,
    sleep=time.sleep,
    _analyze: Callable[[bytes], tuple[str, int]] | None = None,
) -> DocumentText:
    """Layout-synced markdown for one file. Fake provider for tests."""
    log = cost_log if cost_log is not None else _default_log(provider)
    _check_spending(log)
    started = time.monotonic()
    if provider == "fake":
        doc = DocumentText(
            filename=filename,
            markdown=f"# {filename}\n\nFake layout text for tests.\n",
            page_count=1,
            cost_usd=Decimal("0"),
        )
    else:
        doc = _read_reused_or_live(
            data,
            filename=filename,
            endpoint=endpoint,
            key=key,
            sleep=sleep,
            _analyze=_analyze,
        )
    _save_row(log, app, doc, _elapsed_ms(started))
    return doc


def _default_log(provider: str) -> Any:
    # Real calls persist cost rows; fakes stay out of the database.
    return MemoryCostLog() if provider == "fake" else DbCostLog()


def _check_spending(log: Any) -> None:
    limit, warn = log.limits()
    if spending_state(log.month_spent(datetime.now(UTC)), limit, warn) == "paused":
        raise SpendingPaused()


def _replay_mode() -> str:
    return get_settings().ai_replay


def _read_reused_or_live(
    data: bytes,
    *,
    filename: str,
    endpoint: str | None,
    key: str | None,
    sleep,
    _analyze,
) -> DocumentText:
    # A saved replay wins: no Azure call, no credentials, no cost. An
    # explicitly injected analyzer is the test's stand-in for Azure,
    # so it bypasses the replay lookup (the network is still never touched).
    digest = _fingerprint({"model": MODEL, "sha256": hashlib.sha256(data).hexdigest()})
    store = ReplayStore(default_dir())
    if _analyze is None:
        try:
            record = store.load(JOB, digest)
        except AiReplayMissing:
            if _replay_mode() == "replay":
                raise
        else:
            return _from_record(filename, record, free=True)
    doc = _read_live(
        data, filename=filename, endpoint=endpoint, key=key, sleep=sleep, _analyze=_analyze
    )
    if _replay_mode() == "record":
        store.save(JOB, digest, {"markdown": doc.markdown, "page_count": doc.page_count})
    return doc


def _from_record(filename: str, record: dict[str, Any], *, free: bool) -> DocumentText:
    markdown, page_count = record["markdown"], record["page_count"]
    if not isinstance(markdown, str) or not isinstance(page_count, int) or page_count < 0:
        raise AiError("di_bad_replay", f"The saved read for `{filename}` is damaged.")
    cost = Decimal("0") if free else LAYOUT_USD_PER_PAGE * max(page_count, 1)
    return DocumentText(filename=filename, markdown=markdown, page_count=page_count, cost_usd=cost)


def _read_live(
    data: bytes,
    *,
    filename: str,
    endpoint: str | None,
    key: str | None,
    sleep,
    _analyze,
) -> DocumentText:
    retryer = Retrying(
        stop=stop_after_attempt(MAX_RETRIES + 1),
        wait=wait_chain(*[wait_fixed(s) for s in BACKOFFS]),
        retry=retry_if_exception(lambda err: not isinstance(err, AiError)),
        reraise=False,
        sleep=sleep,
    )
    try:
        if _analyze is not None:
            markdown, pages = retryer(_analyze, data)
        else:
            markdown, pages = _live_result(data, retryer, endpoint, key)
    except RetryError as err:
        raise AiUnavailable() from err
    except AiError:
        raise
    except Exception as err:
        raise AiApiError(f"Could not read `{filename}`: {err}.") from err
    return DocumentText(
        filename=filename,
        markdown=markdown,
        page_count=pages,
        cost_usd=LAYOUT_USD_PER_PAGE * max(pages, 1),
    )


def _live_result(
    data: bytes, retryer: Retrying, endpoint: str | None, key: str | None
) -> tuple[str, int]:
    settings = get_settings()
    resolved_endpoint = endpoint if endpoint is not None else settings.azure_di_endpoint
    secret = (
        key
        if key is not None
        else (settings.azure_di_key.get_secret_value() if settings.azure_di_key else None)
    )
    if not resolved_endpoint or not secret:
        raise AiError(
            "di_misconfigured",
            "Document Intelligence needs AZURE_DI_ENDPOINT and AZURE_DI_KEY in .env.",
        )
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
    from azure.core.credentials import AzureKeyCredential

    client = DocumentIntelligenceClient(resolved_endpoint, AzureKeyCredential(secret))
    poller = client.begin_analyze_document(
        MODEL, AnalyzeDocumentRequest(bytes_source=data), output_content_format="markdown"
    )
    result = retryer(poller.result)
    return result.content or "", len(result.pages or [])


def _save_row(log: Any, app: str, doc: DocumentText, duration_ms: int) -> None:
    log.add(
        usage_row(
            job=JOB,
            app=app,
            model=MODEL,
            prompt_tokens=0,
            cached_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            cost_usd=doc.cost_usd,
            duration_ms=duration_ms,
            status="ok",
            error=None,
        )
    )


def _fingerprint(parts: dict[str, Any]) -> str:
    compact = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
