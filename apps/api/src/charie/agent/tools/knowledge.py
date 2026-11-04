"""Asking the organization's own documents what a term means (arch 4.6, 5.5)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from charie.agent.context import KnowledgeFrame
from charie.agent.tools.base import Tool, ToolContext
from charie.knowledge.retrieve import DEFAULT_LIMIT, search_knowledge

__all__ = ["SEARCH_KNOWLEDGE", "KnowledgeFrame"]

#: Architecture 7.4's wording, in the envelope.

#: How many passages a call may ask for.
MAX_LIMIT = 10


class SearchKnowledgeIn(BaseModel):
    """``extra="forbid"`` and no optional-without-default fields, so a provider
    that constrains decoding natively enforces this rather than suggesting it
    (B-033)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=400,
        description=(
            "The term or policy you want defined, in ordinary words — "
            "'how do we count net revenue', 'what counts as an active customer'."
        ),
    )
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


#: What the model is told when the corpus genuinely has nothing.
NOTHING_FOUND = (
    "No document in this organization mentions that. Nothing has been written "
    "down about it, so do not infer a definition — say what you could not find."
)


class PassageOut(BaseModel):
    """One extract, and enough to attribute it."""

    text: str
    #: How this passage names itself in an answer: document, heading trail, position.
    source: str
    document: str
    headings: list[str]
    #: Which arm of the hybrid search found it: `vector`, `lexical`, or `both`.
    found_by: str = "both"


class SearchKnowledgeOut(BaseModel):
    #: First field on purpose. It is the first thing the model reads in the envelope.
    framing: str = KnowledgeFrame
    passages: list[PassageOut]
    note: str = ""


async def _search_knowledge(context: ToolContext, params: BaseModel) -> BaseModel:
    # The same narrowing the catalog tools use: validated at the registry gate already.
    args = (
        params
        if isinstance(params, SearchKnowledgeIn)
        else SearchKnowledgeIn.model_validate(params)
    )

    # Hybrid when the run has an embedder, and charged to the run either way (B-073).
    found = await search_knowledge(
        org_id=context.org_id,
        query=args.query,
        limit=args.limit,
        embedder=context.embedder,
        run_id=context.run_id,
        actor_user_id=context.actor_user_id,
        settings=context.settings,
    )

    if not found.passages:
        # A degraded search that found nothing says both things, in that order.
        note = NOTHING_FOUND if found.degraded is None else f"{found.degraded} {NOTHING_FOUND}"
        return SearchKnowledgeOut(passages=[], note=note)

    return SearchKnowledgeOut(
        passages=[
            PassageOut(
                text=passage.text,
                source=passage.citation,
                document=passage.document_title,
                headings=list(passage.headings),
                found_by=passage.found_by,
            )
            for passage in found.passages
        ],
        note=found.degraded or "",
    )


SEARCH_KNOWLEDGE = Tool(
    name="search_knowledge",
    description=(
        "Search this organization's uploaded documents for what a term means "
        "here — a metric definition, a policy, an exclusion. Use it when a "
        "question depends on how the business defines something, then query the "
        "database for the values. It returns written guidance, never data."
    ),
    params=SearchKnowledgeIn,
    handler=_search_knowledge,
)
