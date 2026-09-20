"""
BehaviorGraph — Structural execution representation connecting signals, threshold conditions, and outputs.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class NodeType(str, Enum):
    INPUT = "INPUT"
    CONDITION = "CONDITION"
    STATE_CHANGE = "STATE_CHANGE"
    OUTPUT = "OUTPUT"
    ERROR = "ERROR"


@dataclass
class BehaviorNode:
    id: str
    type: NodeType
    label: str
    source_line: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BehaviorEdge:
    source: str
    target: str
    condition: Optional[str] = None


@dataclass
class BehaviorGraph:
    nodes: List[BehaviorNode] = field(default_factory=list)
    edges: List[BehaviorEdge] = field(default_factory=list)

    def add_node(self, node: BehaviorNode):
        self.nodes.append(node)

    def add_edge(self, edge: BehaviorEdge):
        self.edges.append(edge)

    def get_condition_nodes(self) -> List[BehaviorNode]:
        return [n for n in self.nodes if n.type == NodeType.CONDITION]
