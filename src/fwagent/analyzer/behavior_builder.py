"""
BehaviorGraphBuilder — Constructs a BehaviorGraph from a FirmwareModel.
"""

from fwagent.models import FirmwareModel
from fwagent.analyzer.behavior import BehaviorGraph, BehaviorNode, BehaviorEdge, NodeType


class BehaviorGraphBuilder:
    def build(self, model: FirmwareModel) -> BehaviorGraph:
        """Build graph from the FirmwareModel thresholds and signals."""
        graph = BehaviorGraph()
        
        for sig in model.inputs:
            graph.add_node(
                BehaviorNode(
                    id=f"IN_{sig.name}",
                    type=NodeType.INPUT,
                    label=sig.name or "input",
                    source_line=sig.line
                )
            )

        for th in model.thresholds:
            cond_id = f"COND_{th.signal}_{th.op}_{th.value}"
            graph.add_node(
                BehaviorNode(
                    id=cond_id,
                    type=NodeType.CONDITION,
                    label=f"{th.signal} {th.op} {th.value}",
                    source_line=th.line,
                    metadata={"signal": th.signal, "op": th.op, "value": th.value}
                )
            )
            # Link input to condition if matching signal
            for sig in model.inputs:
                if sig.name == th.signal or sig.pin == th.signal:
                    graph.add_edge(
                        BehaviorEdge(
                            source=f"IN_{sig.name}",
                            target=cond_id,
                            condition=f"{th.signal} {th.op} {th.value}"
                        )
                    )

        for out in model.outputs:
            out_id = f"OUT_{out.name}"
            graph.add_node(
                BehaviorNode(
                    id=out_id,
                    type=NodeType.OUTPUT,
                    label=out.name or "output",
                    source_line=out.line
                )
            )
            # Link conditions to output
            for th in model.thresholds:
                cond_id = f"COND_{th.signal}_{th.op}_{th.value}"
                graph.add_edge(
                    BehaviorEdge(
                        source=cond_id,
                        target=out_id
                    )
                )

        return graph
