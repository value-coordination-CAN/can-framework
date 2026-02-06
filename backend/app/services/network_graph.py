from collections import deque
from typing import Any, Dict, List

from sqlalchemy.orm import Session
from app.models.network_edge import NetworkEdge

DECAY = 0.6

def _edge_score(weight: float, hops: int) -> float:
    return float(weight) * (DECAY ** (hops - 1))

def find_paths(
    db: Session,
    source_id: str,
    target_id: str,
    max_depth: int = 6,
    top_n: int = 3,
) -> Dict[str, Any]:
    target_is_external = target_id.startswith("li:")

    def edges_from(uid: str) -> List[NetworkEdge]:
        return db.query(NetworkEdge).filter(NetworkEdge.source_user_id == uid).all()

    q = deque([(source_id, [])])
    visited = {source_id: 0}
    found: List[Dict[str, Any]] = []

    while q:
        node, path = q.popleft()
        hops = len(path)
        if hops >= max_depth:
            continue

        for e in edges_from(node):
            nxt = e.target_user_id
            if nxt is None:
                if target_is_external and e.target_external_id == target_id:
                    found.append(_score_path(path + [e]))
                continue

            if (not target_is_external) and nxt == target_id:
                found.append(_score_path(path + [e]))
                continue

            if visited.get(nxt, 10**9) <= hops + 1:
                continue
            visited[nxt] = hops + 1
            q.append((nxt, path + [e]))

    found.sort(key=lambda x: x["confidence"], reverse=True)
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
    for idx, e in enumerate(edges, start=1):
        conf *= _edge_score(e.weight or 0.0, idx)
        path.append({
            "edge_type": e.edge_type,
            "weight": float(e.weight or 0.0),
            "to_user_id": e.target_user_id,
            "to_external_id": e.target_external_id,
            "source_system": e.source_system,
        })
    return {
        "distance": len(edges),
        "confidence": float(conf),
        "path": path,
        "explanation": "Computed from consented CAN edges (imports/attestations); no external graph crawling.",
    }
