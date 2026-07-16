from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Hashable


INF = 10**18


@dataclass
class Edge:
    to: int
    rev: int
    capacity: int
    cost: int
    initial_capacity: int


@dataclass
class EdgeHandle:
    source: int
    index: int
    lower: int


class MinCostFlow:
    """Small integer min-cost-flow solver using successive shortest augmenting paths."""

    def __init__(self) -> None:
        self.node_index: dict[Hashable, int] = {}
        self.node_names: list[Hashable] = []
        self.graph: list[list[Edge]] = []
        self.balance: list[int] = []  # positive = supply (required net outflow)

    def _node(self, name: Hashable) -> int:
        if name in self.node_index:
            return self.node_index[name]
        index = len(self.graph)
        self.node_index[name] = index
        self.node_names.append(name)
        self.graph.append([])
        self.balance.append(0)
        return index

    def set_supply(self, name: Hashable, supply: int) -> None:
        node = self._node(name)
        self.balance[node] += int(supply)

    def add_edge(self, source: Hashable, target: Hashable, capacity: int, cost: int = 0, lower: int = 0) -> EdgeHandle:
        if lower < 0 or capacity < lower:
            raise ValueError("Invalid lower/capacity bounds")
        u, v = self._node(source), self._node(target)
        residual_capacity = int(capacity - lower)
        forward = Edge(v, len(self.graph[v]), residual_capacity, int(cost), residual_capacity)
        reverse = Edge(u, len(self.graph[u]), 0, -int(cost), 0)
        self.graph[u].append(forward)
        self.graph[v].append(reverse)
        # Lower flow consumes source supply and satisfies target demand.
        self.balance[u] -= int(lower)
        self.balance[v] += int(lower)
        return EdgeHandle(source=u, index=len(self.graph[u]) - 1, lower=int(lower))

    def flow_on(self, handle: EdgeHandle) -> int:
        edge = self.graph[handle.source][handle.index]
        used_residual = edge.initial_capacity - edge.capacity
        return handle.lower + used_residual

    def solve(self) -> tuple[bool, int]:
        original_count = len(self.graph)
        super_source = self._node(("__super_source__", original_count))
        super_sink = self._node(("__super_sink__", original_count))
        required = 0
        for node in range(original_count):
            supply = self.balance[node]
            if supply > 0:
                self._add_raw_edge(super_source, node, supply, 0)
                required += supply
            elif supply < 0:
                self._add_raw_edge(node, super_sink, -supply, 0)

        flow, cost = self._min_cost_max_flow(super_source, super_sink, required)
        return flow == required, cost

    def _add_raw_edge(self, u: int, v: int, capacity: int, cost: int) -> None:
        forward = Edge(v, len(self.graph[v]), int(capacity), int(cost), int(capacity))
        reverse = Edge(u, len(self.graph[u]), 0, -int(cost), 0)
        self.graph[u].append(forward)
        self.graph[v].append(reverse)

    def _min_cost_max_flow(self, source: int, sink: int, target_flow: int) -> tuple[int, int]:
        size = len(self.graph)
        potential = [0] * size
        total_flow = 0
        total_cost = 0

        while total_flow < target_flow:
            distance = [INF] * size
            parent_node = [-1] * size
            parent_edge = [-1] * size
            distance[source] = 0
            queue = [(0, source)]

            while queue:
                dist, node = heapq.heappop(queue)
                if dist != distance[node]:
                    continue
                for edge_index, edge in enumerate(self.graph[node]):
                    if edge.capacity <= 0:
                        continue
                    reduced = edge.cost + potential[node] - potential[edge.to]
                    new_distance = dist + reduced
                    if new_distance < distance[edge.to]:
                        distance[edge.to] = new_distance
                        parent_node[edge.to] = node
                        parent_edge[edge.to] = edge_index
                        heapq.heappush(queue, (new_distance, edge.to))

            if distance[sink] == INF:
                break

            for node in range(size):
                if distance[node] < INF:
                    potential[node] += distance[node]

            amount = target_flow - total_flow
            node = sink
            while node != source:
                previous = parent_node[node]
                if previous < 0:
                    amount = 0
                    break
                edge = self.graph[previous][parent_edge[node]]
                amount = min(amount, edge.capacity)
                node = previous
            if amount <= 0:
                break

            node = sink
            path_cost = 0
            while node != source:
                previous = parent_node[node]
                edge_index = parent_edge[node]
                edge = self.graph[previous][edge_index]
                path_cost += edge.cost
                edge.capacity -= amount
                self.graph[node][edge.rev].capacity += amount
                node = previous

            total_flow += amount
            total_cost += amount * path_cost

        return total_flow, total_cost
