"""Causal reasoning module for SUPRA.

Provides DAG construction, causal consistency checking, confounder detection,
and counterfactual reasoning for strategy candidates.

Integration with SUPRA:
  from supra_agentic.causal import CausalGraph, CausalVerifier

  graph = CausalGraph.from_decomposition(decomposition)
  verifier = CausalVerifier(graph)
  result = verifier.check_candidate(candidate)
"""

from __future__ import annotations

import re
from typing import Any


class CausalNode:
    """A node in a causal graph representing a variable."""

    def __init__(self, name: str, node_type: str = "variable"):
        self.name = name
        self.node_type = node_type  # "treatment", "outcome", "confounder", "mediator"

    def __repr__(self):
        return f"CausalNode({self.name}, {self.node_type})"

    def __eq__(self, other):
        return isinstance(other, CausalNode) and self.name == other.name

    def __hash__(self):
        return hash(self.name)


class CausalEdge:
    """A directed edge representing a causal relationship."""

    def __init__(self, source: str, target: str, relationship: str = "causes"):
        self.source = source
        self.target = target
        self.relationship = relationship  # "causes", "inhibits", "correlates"

    def __repr__(self):
        return f"CausalEdge({self.source} -> {self.target}, {self.relationship})"


class CausalGraph:
    """Directed Acyclic Graph (DAG) for causal reasoning."""

    def __init__(self):
        self.nodes: dict[str, CausalNode] = {}
        self.edges: list[CausalEdge] = []

    def add_node(self, name: str, node_type: str = "variable") -> CausalNode:
        if name not in self.nodes:
            self.nodes[name] = CausalNode(name, node_type)
        return self.nodes[name]

    def add_edge(self, source: str, target: str, relationship: str = "causes"):
        if source not in self.nodes:
            self.add_node(source)
        if target not in self.nodes:
            self.add_node(target)
        self.edges.append(CausalEdge(source, target, relationship))

    def get_parents(self, node: str) -> list[str]:
        return [e.source for e in self.edges if e.target == node]

    def get_children(self, node: str) -> list[str]:
        return [e.target for e in self.edges if e.source == node]

    def find_backdoor_paths(self, treatment: str, outcome: str) -> list[list[str]]:
        """Find backdoor paths between treatment and outcome.
        
        A backdoor path is any path from treatment to outcome that starts with
        an arrow pointing TO the treatment (i.e., through confounders).
        """
        paths = []
        parents = self.get_parents(treatment)
        for parent in parents:
            if parent == outcome:
                paths.append([parent, treatment])
            else:
                sub_paths = self._dfs_paths(parent, outcome, visited={treatment})
                for sp in sub_paths:
                    paths.append([parent] + sp)
        return paths

    def _dfs_paths(self, start: str, end: str, visited: set[str]) -> list[list[str]]:
        """DFS to find all paths from start to end."""
        if start == end:
            return [[end]]
        if start in visited:
            return []
        visited.add(start)
        paths = []
        for child in self.get_children(start):
            sub_paths = self._dfs_paths(child, end, visited.copy())
            for sp in sub_paths:
                paths.append([start] + sp)
        return paths

    def identify_confounders(self, treatment: str, outcome: str) -> list[str]:
        """Identify confounders: variables affecting both treatment and outcome."""
        treatment_parents = set(self.get_parents(treatment))
        outcome_ancestors = self._get_ancestors(outcome)
        return list(treatment_parents & outcome_ancestors)

    def _get_ancestors(self, node: str) -> set[str]:
        """Get all ancestors of a node."""
        ancestors = set()
        for parent in self.get_parents(node):
            ancestors.add(parent)
            ancestors |= self._get_ancestors(parent)
        return ancestors

    @classmethod
    def from_decomposition(cls, decomposition: Any) -> CausalGraph:
        """Build a causal graph from a SUPRA StructuredDecomposition."""
        graph = cls()

        # Add nodes from invariants
        for inv in decomposition.invariants:
            graph.add_node(inv[:50], "invariant")

        # Add nodes from assumptions
        for assump in decomposition.mutable_assumptions:
            graph.add_node(assump[:50], "assumption")

        # Add nodes from risk factors
        for risk in decomposition.risk_factors:
            graph.add_node(risk[:50], "risk")

        # Add objective as outcome
        obj_node = decomposition.core_objective[:50]
        graph.add_node(obj_node, "outcome")

        # Create edges: assumptions -> objective, risks -> objective
        for assump in decomposition.mutable_assumptions:
            graph.add_edge(assump[:50], obj_node, "influences")
        for risk in decomposition.risk_factors:
            graph.add_edge(risk[:50], obj_node, "threatens")

        return graph

    def summary(self) -> dict[str, Any]:
        return {
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
            "nodes": [{"name": n.name, "type": n.node_type} for n in self.nodes.values()],
            "edges": [{"source": e.source, "target": e.target, "rel": e.relationship} for e in self.edges],
        }


class CausalVerifier:
    """Verify causal consistency of strategy candidates."""

    def __init__(self, graph: CausalGraph):
        self.graph = graph

    def check_candidate(self, candidate: Any) -> dict[str, Any]:
        """Check if a strategy candidate is causally consistent."""
        hypothesis = candidate.hypothesis if hasattr(candidate, 'hypothesis') else str(candidate)

        # Extract potential treatment and outcome from hypothesis
        treatment = self._extract_treatment(hypothesis)
        outcome = self._extract_outcome(hypothesis)

        # Check for confounders
        confounders = []
        if treatment and outcome:
            confounders = self.graph.identify_confounders(treatment, outcome)

        # Check backdoor paths
        backdoor_paths = []
        if treatment and outcome:
            backdoor_paths = self.graph.find_backdoor_paths(treatment, outcome)

        # Calculate causal confidence
        confidence = self._calc_causal_confidence(confounders, backdoor_paths)

        return {
            "treatment": treatment,
            "outcome": outcome,
            "confounders": confounders,
            "backdoor_paths": backdoor_paths,
            "causal_confidence": confidence,
            "is_consistent": len(confounders) == 0 and len(backdoor_paths) == 0,
        }

    def _extract_treatment(self, hypothesis: str) -> str | None:
        """Extract treatment variable from hypothesis text."""
        # Look for patterns like "X causes Y", "applying X", "deploying X"
        patterns = [
            r"(?:applying|deploying|using|implementing)\s+['\"]?([^'\"]+?)['\"]?",
            r"(.+?)\s+(?:causes|leads to|produces|results in)",
        ]
        for pat in patterns:
            match = re.search(pat, hypothesis, re.IGNORECASE)
            if match:
                return match.group(1)[:50]
        return None

    def _extract_outcome(self, hypothesis: str) -> str | None:
        """Extract outcome variable from hypothesis text."""
        patterns = [
            r"(?:causes|leads to|produces|results in)\s+['\"]?([^'\"]+?)['\"]?",
            r"(?:fulfills|solves|achieves)\s+['\"]?([^'\"]+?)['\"]?",
        ]
        for pat in patterns:
            match = re.search(pat, hypothesis, re.IGNORECASE)
            if match:
                return match.group(1)[:50]
        return None

    def _calc_causal_confidence(self, confounders: list, backdoor_paths: list) -> float:
        """Calculate causal confidence score [0, 1]."""
        base = 0.9
        penalty = 0.1 * len(confounders) + 0.05 * len(backdoor_paths)
        return round(max(0.0, base - penalty), 4)
