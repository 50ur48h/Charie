"""Step 10, owner questions: turn uncertainty into ranked questions (P09.5).

Code gathers every open topic, ranks it and caps new questions at twenty
per run; the rest stay pending for a later run. The AI writes plain
wording and option proposals; code validates the options and calculates
each affected recipe with the proposed interpretation. Answering and
skipping arrive in P09.6.
"""

from sqlalchemy import select

from charie.learner.steps.base import (
    Step,
    StepContext,
    register_step,
    register_step_handler,
    run_query,
)
from charie.shared.knowledge.questions import gather_topics, make_owner_questions, select_new
from charie.shared.settings import get_setting
from charie.shared.tables.questions import OwnerQuestion

JOB_KIND = "write_owner_questions"
STEP_NAME = "owner_questions"


def pending_topics(ctx: StepContext) -> list:
    """Ranked topics with no waiting or skipped question on the same evidence."""
    existing = [
        (row.topic, (row.evidence or {}).get("fingerprint", ""), row.status)
        for row in ctx.session.scalars(select(OwnerQuestion)).all()
    ]
    new, _ = select_new(gather_topics(ctx.session, ctx.version_id), existing)
    return new


def make_jobs(ctx: StepContext) -> list[dict]:
    """One writing job while any topic still needs a question."""
    if not pending_topics(ctx):
        return []
    return [{"step": STEP_NAME}]


def run_job(info, ctx: StepContext) -> None:
    """Gather, rank, write, number and save this run's questions."""
    topics = pending_topics(ctx)

    def run(sql: str):
        return run_query(ctx, "owner_question", sql).rows

    created, pending = make_owner_questions(
        ctx.session, ctx.version_id, topics, run, get_setting(ctx.session, "time_zone") or "UTC"
    )
    ctx.say(
        "found", f"Wrote {len(created)} owner question(s); {len(pending)} topic(s) wait for later."
    )


def finish_step(ctx: StepContext) -> None:
    """How many questions wait for the owner, for the run summary."""
    waiting = ctx.session.scalars(
        select(OwnerQuestion).where(OwnerQuestion.status == "waiting")
    ).all()
    ctx.say("found", f"{len(waiting)} owner question(s) wait for you.")


OWNER_QUESTIONS_STEP = Step(
    name="owner_questions",
    title="Owner questions",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="No open uncertainties need your answer.",
)

register_step(OWNER_QUESTIONS_STEP)
register_step_handler("owner_questions")
