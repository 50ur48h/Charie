"""Can this schema answer that question at all?"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import select

from charie.db.models import CatalogRelationship, CatalogSnapshot
from charie.tenancy.session import org_session

__all__ = [
    "COMPARABLE",
    "JOINABLE",
    "MIN_CONFIDENCE",
    "UNREACHABLE",
    "CapabilityChasm",
    "CapabilityGap",
    "CapabilityVerdict",
    "JoinGraph",
    "decode_inferred_joins",
    "encode_inferred_joins",
    "load_join_graph",
]

#: The three verdicts a pair of tables can earn. Only ``UNREACHABLE`` refuses.
JOINABLE = "joinable"
COMPARABLE = "comparable"
UNREACHABLE = "unreachable"

#: A hop's direction. ``UP`` follows a foreign key from child to parent and narrows.
UP = "up"
DOWN = "down"

#: How sure an inferred relationship must be before the check will rely on it.
MIN_CONFIDENCE = 0.9


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    """Two tables a question needs together, and no way to join them."""

    left: str
    right: str

    def sentence(self) -> str:
        """The refusal, in the shape architecture 4.3 gives it."""
        return (
            f"This database has {self.left} and {self.right}, and the catalog "
            f"records no link between them — it declares no foreign key joining "
            f"the two. That is the limit of what is known here rather than a rule "
            f"against it, and an unverified join would return every row of one "
            f"against every row of the other, so it is not attempted. A declared "
            f"foreign key, or a linking table (for example an order-items table "
            f"joining the two), would make this answerable."
        )


@dataclass(frozen=True, slots=True)
class CapabilityChasm:
    """Two tables joinable only through their shared parent — the chasm trap."""

    left: str
    right: str
    via: str

    def sentence(self) -> str:
        """The instruction, not an apology — this pair has a correct query."""
        return (
            f"{self.left} and {self.right} are both children of {self.via}, so joining "
            f"them directly multiplies their rows together instead of matching them. "
            f"Aggregate each one to the key it shares with {self.via} first, then join "
            f"the two aggregates."
        )


@dataclass(frozen=True, slots=True)
class CapabilityVerdict:
    """What the check found, for the trace, the refusal and the guidance."""

    tables: tuple[str, ...]
    gaps: tuple[CapabilityGap, ...]
    chasms: tuple[CapabilityChasm, ...] = ()

    @property
    def answerable(self) -> bool:
        """A chasm is deliberately not counted here."""
        return not self.gaps

    def reason(self) -> str:
        """One message covering every gap found, or empty when there are none."""
        return " ".join(gap.sentence() for gap in self.gaps)

    def guidance(self) -> str:
        """What to do about the chasms, or empty when there are none."""
        return " ".join(chasm.sentence() for chasm in self.chasms)

    def as_payload(self) -> dict[str, object]:
        """10.3's ``capability_checked {verdicts}`` payload — built for eyes."""
        return {
            "tables": list(self.tables),
            "answerable": self.answerable,
            "verdicts": [
                {"left": gap.left, "right": gap.right, "reachable": False} for gap in self.gaps
            ]
            + [
                {
                    "left": chasm.left,
                    "right": chasm.right,
                    "reachable": True,
                    "verdict": COMPARABLE,
                    "via": chasm.via,
                }
                for chasm in self.chasms
            ],
        }


@dataclass(frozen=True, slots=True)
class JoinGraph:
    """The tables of one catalog and the joins between them."""

    edges: dict[str, frozenset[str]]
    parents: dict[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    #: Pairs joinable only because the platform measured the join rather than being told about it.
    inferred: frozenset[frozenset[str]] = frozenset()

    def inferred_joins(self, tables: Sequence[str]) -> tuple[tuple[str, str], ...]:
        """Which of the joins among `tables` rest on a measurement."""
        wanted = {_bare(name) for name in tables}
        found = [
            tuple(sorted(pair))
            for pair in self.inferred
            if len(pair & wanted) == 2  # both ends are tables this answer used
        ]
        return tuple(sorted((left, right) for left, right in found))

    def _hop(self, here: str, there: str) -> str:
        """Which way this single edge is being walked."""
        downward = here in self.parents.get(there, frozenset())
        upward = there in self.parents.get(here, frozenset())
        return DOWN if downward and not upward else UP

    def path(self, left: str, right: str) -> tuple[str, ...] | None:
        """A shortest join path, or None when the two are unreachable."""
        left, right = _bare(left), _bare(right)
        if left == right:
            return (left,)
        if left not in self.edges or right not in self.edges:
            # A table absent from the catalog is not "unreachable" — it is unknown.
            return None
        seen = {left}
        queue: deque[tuple[str, ...]] = deque([(left,)])
        while queue:
            trail = queue.popleft()
            for neighbour in sorted(self.edges.get(trail[-1], frozenset())):
                if neighbour in seen:
                    continue
                if neighbour == right:
                    return (*trail, neighbour)
                seen.add(neighbour)
                queue.append((*trail, neighbour))
        return None

    def safe_path(self, left: str, right: str) -> tuple[str, ...] | None:
        """A shortest path that never turns up then down, or None."""
        left, right = _bare(left), _bare(right)
        if left == right:
            return (left,)
        if left not in self.edges or right not in self.edges:
            return None
        # Direction of the hop that arrived; None at the start, where anything is still allowed.
        start: tuple[str, ...] = (left,)
        queue: deque[tuple[tuple[str, ...], str | None]] = deque([(start, None)])
        seen: set[tuple[str, str | None]] = {(left, None)}
        while queue:
            trail, arrived = queue.popleft()
            here = trail[-1]
            for neighbour in sorted(self.edges.get(here, frozenset())):
                direction = self._hop(here, neighbour)
                if arrived == UP and direction == DOWN:
                    continue  # the chasm: `here` is a shared parent.
                if neighbour == right:
                    return (*trail, neighbour)
                state = (neighbour, direction)
                if state in seen:
                    continue
                seen.add(state)
                queue.append(((*trail, neighbour), direction))
        return None

    def classify(self, left: str, right: str) -> str:
        """`joinable`, `comparable` or `unreachable` for one pair."""
        if self.safe_path(left, right) is not None:
            return JOINABLE
        return COMPARABLE if self.path(left, right) is not None else UNREACHABLE

    def _hub(self, left: str, right: str) -> str:
        """The node where the shortest path turns from narrowing to fanning out."""
        trail = self.path(left, right) or (left, right)
        for index in range(1, len(trail) - 1):
            if (
                self._hop(trail[index - 1], trail[index]) == UP
                and self._hop(trail[index], trail[index + 1]) == DOWN
            ):
                return trail[index]
        return trail[len(trail) // 2]

    def check(self, tables: Iterable[str]) -> CapabilityVerdict:
        """How every table named relates to every other."""
        wanted = sorted({_bare(name) for name in tables if _bare(name)})
        gaps: list[CapabilityGap] = []
        chasms: list[CapabilityChasm] = []
        for index, left in enumerate(wanted):
            for right in wanted[index + 1 :]:
                verdict = self.classify(left, right)
                if verdict == UNREACHABLE:
                    gaps.append(CapabilityGap(left=left, right=right))
                elif verdict == COMPARABLE:
                    chasms.append(
                        CapabilityChasm(left=left, right=right, via=self._hub(left, right))
                    )
        return CapabilityVerdict(tables=tuple(wanted), gaps=tuple(gaps), chasms=tuple(chasms))

    def unreachable_pairs(self) -> tuple[CapabilityGap, ...]:
        """Every pair in this catalog that cannot be joined."""
        names = sorted(self.edges)
        return tuple(
            CapabilityGap(left=left, right=right)
            for index, left in enumerate(names)
            for right in names[index + 1 :]
            if self.path(left, right) is None
        )

    def comparable_pairs(self) -> tuple[CapabilityChasm, ...]:
        """Every pair reachable only through a shared parent."""
        names = sorted(self.edges)
        return tuple(
            CapabilityChasm(left=left, right=right, via=self._hub(left, right))
            for index, left in enumerate(names)
            for right in names[index + 1 :]
            if self.classify(left, right) == COMPARABLE
        )


def _bare(name: str) -> str:
    """``public.orders`` and ``orders`` are the same table to this check."""
    return name.strip().strip('"').split(".")[-1].lower()


def encode_inferred_joins(pairs: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    """The form `state.capability` carries an inferred join in."""
    return [{"left": left, "right": right} for left, right in pairs]


def decode_inferred_joins(recorded: object) -> tuple[tuple[str, str], ...]:
    """Read back what `encode_inferred_joins` wrote."""
    if not isinstance(recorded, list):
        return ()
    out: list[tuple[str, str]] = []
    for entry in cast(list[object], recorded):
        if not isinstance(entry, dict):
            continue
        pair = cast(dict[str, object], entry)
        left, right = pair.get("left"), pair.get("right")
        if isinstance(left, str) and isinstance(right, str):
            out.append((left, right))
    return tuple(out)


async def load_join_graph(org_id: uuid.UUID, data_source_id: uuid.UUID) -> JoinGraph:
    """The active catalog's join graph, including tables that join to nothing."""
    async with org_session(org_id) as session:
        snapshot = (
            await session.execute(
                select(CatalogSnapshot.id).where(
                    CatalogSnapshot.data_source_id == data_source_id,
                    CatalogSnapshot.status == "active",
                )
            )
        ).scalar_one_or_none()
        if snapshot is None:
            return JoinGraph(edges={})

        from charie.db.models import CatalogTable

        names = (
            (
                await session.execute(
                    select(CatalogTable.table_name).where(CatalogTable.snapshot_id == snapshot)
                )
            )
            .scalars()
            .all()
        )
        rows = (
            await session.execute(
                select(
                    CatalogRelationship.from_table,
                    CatalogRelationship.to_table,
                    CatalogRelationship.confidence,
                    CatalogRelationship.kind,
                ).where(CatalogRelationship.snapshot_id == snapshot)
            )
        ).all()

    adjacency: dict[str, set[str]] = {_bare(name): set() for name in names}
    # `from` is the child — the table carrying the foreign key.
    parents: dict[str, set[str]] = {}
    # Which pairs are joinable only because this platform measured the join rather than being...
    inferred: set[frozenset[str]] = set()
    for from_table, to_table, confidence, kind in rows:
        if confidence is not None and float(confidence) < MIN_CONFIDENCE:
            continue
        left, right = _bare(from_table), _bare(to_table)
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
        parents.setdefault(left, set()).add(right)
        if kind == "inferred":
            inferred.add(frozenset((left, right)))
    return JoinGraph(
        edges={name: frozenset(links) for name, links in adjacency.items()},
        parents={name: frozenset(links) for name, links in parents.items()},
        inferred=frozenset(inferred),
    )
