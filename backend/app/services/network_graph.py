from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.network_edge import NetworkEdge

# Confidence of a path = product of edge weights x DECAY^(hops - 1): each extra hop discounts once.
DECAY = 0.6
MAX_PATHS_EXPLORED = 10_000


def find_paths(
    db: Session,
    source_id: str,
    target_id: str,
    max_depth: int = 6,
    top_n: int = 3,
) -> Dict[str, Any]:
    """Breadth-first search, one query per depth level. Finds alternative simple paths
    (not only the first shortest one) up to max_depth hops."""
    target_is_external = target_id.startswith("li:")
    frontier: List[tuple[str, List[NetworkEdge]]] = [(source_id, [])]
    best_depth: Dict[str, int] = {source_id: 0}
    found: List[Dict[str, Any]] = []
    explored = 0

    for depth in range(1, max_depth + 1):
        if not frontier or explored > MAX_PATHS_EXPLORED:
            break
        nodes = {node for node, _ in frontier}
        edges_by_source: Dict[str, List[NetworkEdge]] = defaultdict(list)
        for e in db.query(NetworkEdge).filter(NetworkEdge.source_user_id.in_(nodes)).all():
            edges_by_source[e.source_user_id].append(e)

        next_frontier: List[tuple[str, List[NetworkEdge]]] = []
        for node, path in frontier:
            on_path = {source_id} | {e.target_user_id for e in path}
            for e in edges_by_source.get(node, []):
                explored += 1
                nxt = e.target_user_id
                if nxt is None:
                    if target_is_external and e.target_external_id == target_id:
                        found.append(_score_path(path + [e]))
                    continue
                if not target_is_external and nxt == target_id:
                    found.append(_score_path(path + [e]))
                    continue
                if nxt in on_path:
                    continue  # no cycles
                # Allow alternative routes of the same length; drop strictly longer ones.
                if best_depth.get(nxt, depth) < depth:
                    continue
                best_depth[nxt] = depth
                next_frontier.append((nxt, path + [e]))
        frontier = next_frontier

    found.sort(key=lambda x: (-x["confidence"], x["distance"]))
    return {
        "from": source_id,
        "to": target_id,
        "max_depth": max_depth,
        "found": len(found),
        "paths": found[:top_n],
    }


def _score_path(edges: List[NetworkEdge]) -> Dict[str, Any]:
    conf = 1.0
    path = []
    for e in edges:
        conf *= float(e.weight or 0.0)
        path.append({
            "edge_type": e.edge_type,
            "weight": float(e.weight or 0.0),
            "to_user_id": e.target_user_id,
            "to_external_id": e.target_external_id,
            "source_system": e.source_system,
        })
    conf *= DECAY ** (len(edges) - 1)
    return {
        "distance": len(edges),
        "confidence": float(conf),
        "path": path,
        "explanation": "Computed from edges users imported or attested themselves; no external graph crawling.",
    }
