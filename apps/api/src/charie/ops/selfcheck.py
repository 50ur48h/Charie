"""Can this deployment's identity do what the product needs?"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Final

from charie.config import Settings, get_settings
from charie.dal.artifacts import artifact_store
from charie.secrets.base import SecretNotFoundError
from charie.secrets.factory import get_secrets_provider

#: The namespace every probe write goes under, named for what it is rather than for what it holds.
PROBE_NAMESPACE: Final = "selfcheck"

#: A probe payload with no resemblance to a credential.
PROBE_VALUE: Final = "deployment-selfcheck-probe"


class SelfCheckError(Exception):
    """A check failed, with a message that names the permission to grant."""


async def check_secrets(settings: Settings) -> str:
    """Write, read, delete, confirm gone — all four, because the product needs all four."""
    provider = get_secrets_provider()
    ref = f"{PROBE_NAMESPACE}/{uuid.uuid4()}"

    try:
        await provider.put(ref, {"probe": PROBE_VALUE})
    except Exception as error:
        raise SelfCheckError(
            f"could not WRITE a secret to {settings.secrets_backend}: {error}. "
            "For Key Vault the identity needs a role that can set a secret — "
            "'Key Vault Secrets Officer'. 'Key Vault Secrets User' can only read, "
            "which is B-125 exactly."
        ) from error

    try:
        got = await provider.get(ref)
    except Exception as error:
        raise SelfCheckError(f"wrote a secret and could not READ it back: {error}") from error

    if got.get("probe") != PROBE_VALUE:
        raise SelfCheckError(
            "the secret read back is not the one written, so the store is not "
            "round-tripping values. Nothing else here is trustworthy until that is."
        )

    try:
        await provider.delete(ref)
    except Exception as error:
        raise SelfCheckError(
            f"could not DELETE a secret: {error}. Rotating and removing a data "
            "source both delete, so this permission is not optional."
        ) from error

    # The delete is only proven by the absence that follows it.
    try:
        await provider.get(ref)
    except SecretNotFoundError:
        return f"secrets ({settings.secrets_backend}): write, read, delete, and gone"
    raise SelfCheckError(
        "delete returned success and the secret is still readable. The credential "
        "of a removed data source would outlive the data source."
    )


async def check_artifacts(settings: Settings) -> str:
    """Write and read a result artifact the way a query execution does."""
    store = artifact_store(settings)
    org_id, execution_id = uuid.uuid4(), uuid.uuid4()
    payload = PROBE_VALUE.encode()

    # `finally`, and the first version did not have it.
    try:
        try:
            reference = await store.put(org_id=org_id, execution_id=execution_id, payload=payload)
        except Exception as error:
            raise SelfCheckError(
                f"could not WRITE an artifact to {settings.artifacts_backend}: {error}. "
                "For Blob the identity needs 'Storage Blob Data Contributor' on the "
                "account, and the container must exist. Every query execution writes "
                "one of these, so nobody could ask a question."
            ) from error

        try:
            got = await store.get(org_id=org_id, reference=reference)
        except Exception as error:
            raise SelfCheckError(
                f"wrote an artifact and could not READ it back: {error}. An answer "
                "would be stored and its evidence unreadable."
            ) from error

        if got != payload:
            # `None` is the interesting case: `get` returns it for a missing blob.
            state = "missing" if got is None else "not what was written"
            raise SelfCheckError(
                f"the artifact read back is {state}. A write that lands somewhere the "
                "read does not look produces this."
            )

        await _forget_probe_artifact(settings, reference)
        return f"artifacts ({settings.artifacts_backend}): write and read a result payload"
    finally:
        # `getattr` because only the Blob store has anything to close.
        aclose = getattr(store, "aclose", None)
        if aclose is not None:
            await aclose()


async def _forget_probe_artifact(settings: Settings, reference: str) -> None:
    """Best effort, and its failure is deliberately not a check failure."""
    if settings.artifacts_backend != "blob":
        return
    try:
        from azure.identity.aio import DefaultAzureCredential
        from azure.storage.blob.aio import BlobServiceClient

        async with (
            DefaultAzureCredential() as credential,
            BlobServiceClient(
                account_url=settings.artifacts_account_url or "", credential=credential
            ) as service,
        ):
            blob = service.get_blob_client(container=settings.artifacts_container, blob=reference)
            await blob.delete_blob()
    except Exception as error:
        print(f"  note: the probe artifact was left behind ({error}).")
        print("  Harmless — the expire-artifacts lifecycle rule removes it.")


async def run() -> int:
    """Every check, then a verdict. Returns a process exit code."""
    settings = get_settings()
    print(f"selfcheck: identity probe against env={settings.env}")

    failures: list[str] = []
    for check in (check_secrets, check_artifacts):
        try:
            print(f"  ok  {await check(settings)}")
        except SelfCheckError as failure:
            print(f"  FAIL  {failure}", file=sys.stderr)
            failures.append(str(failure))

    if failures:
        print(
            f"selfcheck: {len(failures)} check(s) failed. The deployment is running "
            "and cannot do what the product needs — which is the state a person "
            "otherwise discovers by clicking a button.",
            file=sys.stderr,
        )
        return 1

    print("selfcheck: this identity can store a credential and store a result.")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
