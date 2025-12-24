"""
Clustering Pipeline (Template Method)

Defines the sequence for grouping raw option legs into logical strategies.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple


@dataclass
class ClusteringContext:
    """Shared state for the clustering pipeline."""

    raw_legs: List[Tuple[int, Dict[str, Any]]]
    leg_infos: List[Dict[str, Any]] = field(default_factory=list)
    clusters: List[List[Dict[str, Any]]] = field(default_factory=list)
    used_indices: Set[int] = field(default_factory=set)

    # Intermediate state for verticals
    call_verticals: List[List[Dict[str, Any]]] = field(default_factory=list)
    put_verticals: List[List[Dict[str, Any]]] = field(default_factory=list)


class ClusteringPipeline:
    """
    Template Method implementation for option strategy clustering.
    """

    def cluster(self, legs_with_idx: List[Tuple[int, Dict[str, Any]]]) -> Tuple[List[List[Dict[str, Any]]], Set[int]]:
        """
        The Template Method: Defines the clustering algorithm skeleton.
        """
        ctx = ClusteringContext(legs_with_idx)

        self._extract_leg_info(ctx)
        self._take_named_clusters(ctx, size=4)  # Iron Condors / Butterflies
        self._take_named_clusters(ctx, size=3)  # Lizards
        self._pair_verticals(ctx)
        self._combine_into_condors(ctx)
        self._pair_strangles(ctx)

        return ctx.clusters, ctx.used_indices

    def _extract_leg_info(self, ctx: ClusteringContext) -> None:
        """Step 1: Normalize and sort leg info."""
        from .steps.extract import extract_leg_info
        ctx.leg_infos = extract_leg_info(ctx.raw_legs)

    def _take_named_clusters(self, ctx: ClusteringContext, size: int) -> None:
        """Step 2/3: Greedily match N-leg named strategies."""
        from .steps.named import take_named_clusters
        new_clusters = take_named_clusters(ctx.leg_infos, ctx.used_indices, size)
        ctx.clusters.extend(new_clusters)

    def _pair_verticals(self, ctx: ClusteringContext) -> None:
        """Step 4: Pair remaining verticals by strike proximity."""
        from .steps.verticals import pair_verticals
        ctx.call_verticals, ctx.put_verticals = pair_verticals(ctx.leg_infos, ctx.used_indices)

    def _combine_into_condors(self, ctx: ClusteringContext) -> None:
        """Step 5: Combine matching verticals into credit condors."""
        from .steps.condors import combine_into_condors
        ic_clusters = combine_into_condors(ctx.call_verticals, ctx.put_verticals, ctx.used_indices)
        ctx.clusters.extend(ic_clusters)

    def _pair_strangles(self, ctx: ClusteringContext) -> None:
        """Step 6: Pair remaining short legs into strangles."""
        from .steps.strangles import pair_strangles
        strangle_clusters = pair_strangles(ctx.leg_infos, ctx.used_indices)
        ctx.clusters.extend(strangle_clusters)
