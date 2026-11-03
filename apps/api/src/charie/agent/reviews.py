"""The evidence and display contract for a business performance review (B-188).

The existing Markdown renderer already supports interleaved cards and charts.
These instructions make those components reachable from a real investigation;
they do not change the SQL policy, budgets or the critic's evidence checks.
"""

from __future__ import annotations

import re

_REVIEW = re.compile(
    r"\b(?:business review|performance review|performance overview|monthly review|"
    r"monthly performance|presentation)\b|"
    r"\bhow\s+(?:(?:are|did|have|were)\s+)?we\s+(?:doing|did|do|done|perform)|"
    r"\bhow\s+(?:are|were|is|was|did)\s+(?:our\s+|the\s+)?"
    r"(?:sales|business|revenue|restaurants|outlets|stores)\b",
    re.IGNORECASE,
)


_BRIEF = re.compile(
    r"\b(?:short (?:answer|response|summary)|(?:brief|concise) (?:answer|response)|"
    r"briefly|in brief|keep it (?:short|brief|concise)|be (?:brief|concise)|"
    r"(?:one|two|three|[123])[ -](?:sentences?|lines?)|"
    r"just (?:the )?(?:answer|number|total)|tl;?dr)\b",
    re.IGNORECASE,
)


def brief_requested(question: str) -> bool:
    return _BRIEF.search(question) is not None


def review_requested(question: str) -> bool:
    return not brief_requested(question) and business_question(question)


def business_question(question: str) -> bool:
    return _REVIEW.search(question) is not None


BRIEF_DISPLAY = """\
The person explicitly asked for a short answer. Give the direct result in one
short paragraph, or the requested sentence/line count. Keep essential uncertainty,
but omit KPI tables, charts and a full review. Leave chart.of empty. Query only
what is needed to answer accurately; do not add an unrelated investigation.
For a performance comparison, fetch both periods in one aggregate when possible.
Brevity changes the presentation, not the question's scope or evidence standard.
"""

VISUAL_DISPLAY = """\
Use the Calm visual style by default, without waiting for formatting instructions.
Lead with the answer, then alternate brief explanations with useful visuals.
Put key figures in a Metric | Value | Change | Comparison table (omit unavailable
columns); put comparisons and time series in separate tables so the screen can
draw them inline. Use only relevant, supported blocks: a simple fact or definition
does not need a dashboard. Never invent metrics or fetch unrelated data to fill it.
"""


REVIEW_EVIDENCE = """\
This is a business performance review. Gather three complementary results before
declaring it complete, using separate narrow queries when necessary:
1. A company-wide comparison summary: sales, orders, average order and the count
   of outlets growing out of the comparable population, with prior-period values
   and changes. Calculate totals and counts over the full population in SQL,
   never by adding the few outlet rows visible in a preview. Calculate average
   order as total sales / total orders, not an average of outlet averages.
   Prefer conditional aggregation over both periods to produce exactly one row
   per outlet before the company aggregation. If joining monthly aggregates,
   filter EACH side to its own period before joining: a month condition on only
   one side duplicates rows and inflates totals and the comparable population.
   Check that the outlet row count equals its distinct outlet count. Reconcile
   the requested-period summary with the sum of its daily series; if results
   disagree, correct and rerun the query rather than choosing one conflicting
   result to fill the KPI cards. Keep the corrected query's summary in evidence.
2. A bounded outlet comparison, including the largest gains and falls (at most
   eight rows), with a readable outlet name via a verified join where available,
   and an explicit percentage change rounded in SQL to one decimal place.
   Count growing outlets before limiting the ranking. Distinguish new/missing
   outlets from comparable ones.
3. A narrow daily sales series for the requested month (date and sales only),
   or a coarser explicitly labelled series if the question requests it.
Use one sales definition, currency, status filter and outlet scope throughout.
Use the organization's definition where one exists; never relabel gross sales
as net sales. State any necessary definition assumption. Keep explicit period
bounds, explain unequal period lengths, and handle a zero prior denominator as
undefined rather than inventing a percentage. No data is not zero activity.
Only finish when these requested parts are supported or a specific missing part
is established. If a result preview omits needed rows, narrow its columns or
query an aggregate rather than claiming the database lacks the answer.
"""


REVIEW_DISPLAY = """\
Present this business review in the Calm answer flow, with Markdown blocks in
this order. These table shapes are rendered as cards and inline charts:
1. Lead with the plain-English takeaway in one short paragraph: tell the person
   what happened, not how the analysis was organised. Explain the comparison
   briefly; keep definitions and checks after the main result where needed.
2. A four-row KPI table with exactly these headers:
   Metric | Value | Change | Comparison
   Rows: Sales (use the source's exact definition), Orders, Average order, Outlets up.
   Use 'Net sales' only when the supporting query/definition establishes net
   sales. A column including tax and fees must be labelled 'Sales incl. tax and
   fees', never 'Net sales'. Do not change the measure to match the design.
   Value holds the current figure; Change holds the measured signed percentage
   such as +6.2% or -2.4%, or N/A when undefined; Comparison names the baseline.
   For Outlets up use '21 of 24' style, using actual counts, and say what grew.
   Omit an unavailable metric and explain why; never invent a value to fill a card.
3. A short interpretation, then an outlet-change table (at most eight rows),
   using Outlet | Sales change (%) with explicit signed percentages. This becomes
   a diverging bar chart; the underlying table remains available to the reader.
4. A short interpretation, then Date | Sales (using the same honest sales label),
   with ISO YYYY-MM-DD dates and one row for every returned day. This becomes a
   line chart. Do not collapse all days into prose or substitute selected days
   while calling it the whole month.
5. Brief evidence-based takeaways and what to check next; separate observations
   from possible causes. Do not invent incidents or copy the design's example.
Put prose between the tables. Do not emit HTML, images or invented chart syntax.
Keep interpretation brief so the complete daily table and closing takeaways fit.
Do not introduce combined totals in takeaways unless a query returned them.
Do not also request the standalone chart when these inline chart tables cover
the same results: leave chart.of empty to avoid a duplicate picture at the end.
Use only results this run obtained, cite their execution ids, and explicitly
name any part the evidence cannot establish instead of padding a complete report.
When every requested part is established, set unanswered to the empty string.
It names a missing part, not a boolean: never put 'false' or 'none' in it.
"""
