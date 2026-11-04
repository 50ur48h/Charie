"""The scripted provider, and the two guards that keep it out of production."""

from __future__ import annotations

import uuid

import pytest

from charie.agent.critic import CriticOut
from charie.agent.loop import Reflection
from charie.agent.planner import Plan
from charie.agent.runner import FinalizeIn
from charie.config import Settings
from charie.llm import registry
from charie.llm.base import LLMRequest, Message, Tags
from charie.llm.registry import STUB_PROVIDERS, ProviderNotConfiguredError, get_provider
from charie.llm.scripted import PROVIDER_NAME, SCRIPTED_SQL, ScriptedProvider
from charie.main import create_app


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "auth_mode": "entra",
        "secrets_backend": "keyvault",
        "oidc_authority": "https://login.example.com/tenant/v2.0",
        "oidc_audience": "api://charie",
        "llm_providers": ("scripted",),
    }
    base.update(overrides)
    return Settings(**base)  # pyright: ignore[reportArgumentType]


def _request(role: str = "compose", prompt: str = "") -> LLMRequest:
    return LLMRequest(
        model="scripted-1",
        messages=[Message(role="user", content=prompt)],
        tags=Tags(org_id=uuid.uuid4(), role=role),  # pyright: ignore[reportArgumentType]
    )


# --- The guards ---


@pytest.mark.parametrize(
    ("env", "build_env"),
    [("prod", "dev"), ("local", "prod"), ("prod", "prod")],
)
def test_a_production_app_will_not_boot_with_the_scripted_provider(
    env: str, build_env: str
) -> None:
    """The test the whole work package turns on."""
    settings = _settings(env=env, build_env=build_env)

    with pytest.raises(RuntimeError, match="answers without a model"):
        create_app(settings=settings)


def test_the_refusal_names_the_variable_and_why() -> None:
    """A refusal an operator cannot act on gets worked around at 3am."""
    settings = _settings(env="prod", build_env="prod")

    with pytest.raises(RuntimeError) as raised:
        create_app(settings=settings)

    message = str(raised.value)
    assert "LLM_PROVIDERS" in message, "it names the variable to change"
    assert "scripted" in message, "and which value is the problem"
    assert "evidenced" in message, "and why this is worse than an outage"


def test_a_non_production_app_boots_with_it() -> None:
    """The control."""
    app = create_app(settings=_settings(env="ci", build_env="dev", auth_mode="dev"))

    assert app is not None


def test_the_registry_still_refuses_a_stub_it_was_never_configured_for() -> None:
    """The second guard, catching what the first cannot."""
    # Registered under a name nothing else uses, and deliberately not cleaned up afterwards.
    registry.register_provider("smuggled", ScriptedProvider)

    with pytest.raises(ProviderNotConfiguredError, match="answers without a model"):
        get_provider("smuggled", _settings(env="prod", build_env="prod"))


def test_the_scripted_provider_is_named_as_a_stub_in_both_places() -> None:
    """The two guards read different sources of truth, so they can disagree."""
    assert PROVIDER_NAME in STUB_PROVIDERS
    assert ScriptedProvider().capabilities().is_stub is True


# --- What it actually answers ---


async def test_it_answers_every_role_the_loop_asks_of_it() -> None:
    """A role the smoke reaches and this does not answer is a smoke that fails in CI with a..."""
    provider = ScriptedProvider()

    plan = await provider.complete(_request("sql"))
    reflect = await provider.complete(_request("plan"))
    critic = await provider.complete(_request("critic"))

    assert SCRIPTED_SQL in plan.text
    assert '"done": true' in reflect.text
    assert '"verdict": "pass"' in critic.text


async def test_composing_cites_the_execution_it_was_shown() -> None:
    """The one piece of state it cannot know in advance."""
    execution_id = str(uuid.uuid4())
    provider = ScriptedProvider()

    completion = await provider.complete(
        _request("compose", prompt=f"- {execution_id}: 1 row over columns order_count")
    )

    assert execution_id in completion.text


async def test_it_reports_no_usage_rather_than_inventing_a_price() -> None:
    """The meter writes every call to `usage_ledger`, so the row still shows a call happened."""
    completion = await ScriptedProvider().complete(_request("compose"))

    assert completion.usage.total_tokens == 0


async def test_every_scripted_reply_satisfies_the_schema_the_loop_asks_with() -> None:
    """Against the real schemas, not against the strings."""
    provider = ScriptedProvider()
    execution_id = str(uuid.uuid4())

    plan = Plan.model_validate_json((await provider.complete(_request("sql"))).text)
    reflection = Reflection.model_validate_json((await provider.complete(_request("plan"))).text)
    verdict = CriticOut.model_validate_json((await provider.complete(_request("critic"))).text)
    final = FinalizeIn.model_validate_json(
        (await provider.complete(_request("compose", prompt=f"- {execution_id}: 1 row"))).text
    )

    assert plan.sql == SCRIPTED_SQL
    # One iteration, or the smoke spends its time on a search it is not testing.
    assert reflection.done is True
    assert verdict.verdict == "pass"
    # Cited, so the answer arrives with evidence attached rather than bare.
    assert final.supported_by == [execution_id]
