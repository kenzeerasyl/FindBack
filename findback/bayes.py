"""Explainable Bayesian filtering and duplicate-evidence protection."""
from __future__ import annotations

from dataclasses import dataclass

from .domain import Belief, ObservationModel


class ImpossibleEvidence(ValueError):
    """The observation has probability zero under the current model."""


@dataclass(frozen=True)
class Evidence:
    event_id: str
    kind: str
    target: str
    outcome: str

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("Evidence needs a nonempty unique event ID")
        valid = {'ask': ('yes', 'no'), 'search': ('found', 'not_found')}
        if self.kind not in valid or self.outcome not in valid[self.kind]:
            raise ValueError("Invalid evidence kind/outcome")


@dataclass(frozen=True)
class Update:
    before: Belief
    likelihoods: tuple[tuple[str, float], ...]
    weights: tuple[tuple[str, float], ...]
    evidence_probability: float
    after: Belief


def update(prior: Belief, model: ObservationModel, evidence: Evidence) -> Update:
    prior.at(evidence.target)  # reject unknown targets before computation
    likelihoods = tuple((name, model.likelihood(evidence.kind, evidence.outcome,
                                               evidence.target, name))
                        for name, _ in prior.entries)
    weights = tuple((name, p*likelihood) for (name, p), (_, likelihood)
                    in zip(prior.entries, likelihoods))
    total = sum(w for _, w in weights)
    if total <= 0:
        raise ImpossibleEvidence("Observation is impossible under the current belief/model")
    posterior = Belief(tuple((name, w/total) for name, w in weights))
    return Update(prior, likelihoods, weights, total, posterior)


@dataclass(frozen=True)
class BeliefTracker:
    belief: Belief
    seen: frozenset[str] = frozenset()
    history: tuple[tuple[Evidence, Update], ...] = ()

    def apply(self, model: ObservationModel, evidence: Evidence) -> BeliefTracker:
        if evidence.event_id in self.seen:
            raise ValueError(f"Evidence already processed: {evidence.event_id}")
        result = update(self.belief, model, evidence)
        return BeliefTracker(result.after, self.seen | {evidence.event_id},
                             self.history + ((evidence, result),))
