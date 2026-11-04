"""How a run says it is done (architecture Part 4.6's ``finalize``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from charie.agent.tools.base import Tool, ToolContext

__all__ = ["FINALIZE", "ChartAsk", "FinalizeIn"]


class ChartAsk(BaseModel):
    """The chart to draw, if one helps (WP11.1).

    One nested field on ``FinalizeIn`` rather than four flat ones, and every
    member defaulted rather than optional: B-033 wants a closed schema a provider
    can constrain natively, and ``None`` is the shape that costs a repair round.
    An empty ``of`` means no chart was asked for, which is the common case — the
    same idiom ``Plan.define`` uses for a lookup nobody needs.
    """

    model_config = ConfigDict(extra="forbid")

    of: str = Field(
        default="",
        max_length=64,
        description=(
            "Leave empty unless a chart genuinely helps. Otherwise the execution "
            "id from supported_by whose rows should be drawn."
        ),
    )
    mark: str = Field(default="", description="bar | line | point | area")
    x: str = Field(default="", max_length=120, description="Column for the horizontal axis")
    y: str = Field(
        default="", max_length=120, description="Column for the vertical axis. Must hold numbers."
    )
    series: str = Field(
        default="",
        max_length=120,
        description=(
            "Optional column to split the marks by colour, when the split is "
            "part of the answer — revenue by month *per channel*. Leave empty "
            "for a single series: colouring one series by its own x values adds "
            "no information the axis does not already carry, and is refused."
        ),
    )


class FinalizeIn(BaseModel):
    """``extra="forbid"`` and every field required — so a provider that can
    constrain decoding natively enforces this shape rather than suggesting it
    (B-033), and the repair path becomes the exception."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(
        min_length=1,
        max_length=8000,
        description=(
            "The answer, in plain words, for the person who asked. If you could "
            "not answer, say what is missing instead — do not guess. Write about "
            "the data and never about the chart: whether one can be drawn is "
            "decided after you answer, and the card says so in its own place. An "
            "apology for what a chart cannot do reads to the reader as the "
            "product being broken."
        ),
    )
    unanswered: str = Field(
        default="",
        max_length=200,
        description=(
            "The part of the question you could not answer, in a few words — "
            "'the cost', 'the date range'. Empty if you answered all of it. Name "
            "the part, not the reason; the reason belongs in your answer."
        ),
    )
    supported_by: list[str] = Field(
        default_factory=list[str],
        max_length=20,
        description=(
            "Execution ids from run_sql results in this run, and nothing else. "
            "Every number in your answer must come from one of them."
        ),
    )
    confidence: str = Field(
        default="medium", description="high | medium | low — how sure you are of this answer."
    )
    chart: ChartAsk = Field(
        default_factory=ChartAsk,
        description=(
            "A chart of one of the results above, when a picture says something "
            "the sentence cannot — a trend over time, a comparison across "
            "categories. Leave `of` empty when it would not."
        ),
    )

    @property
    def claims_an_answer(self) -> bool:
        """Whether this draft asserts something a reviewer should check."""
        return bool(self.supported_by) or not self.unanswered


class FinalizeOut(BaseModel):
    accepted: bool = True


async def _finalize(context: ToolContext, params: BaseModel) -> BaseModel:
    """Accept the model's ending. The runner is what acts on it."""
    return FinalizeOut()


FINALIZE = Tool(
    name="finalize",
    description=(
        "Finish the run with an answer. Cite the execution ids of the queries "
        "your answer rests on. If the data cannot answer the question, set "
        "answered=false and say what is missing."
    ),
    params=FinalizeIn,
    handler=_finalize,
)
