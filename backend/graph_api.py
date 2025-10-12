# backend/app/routers/graph.py
from __future__ import annotations

from datetime import datetime, timezone
from os import getenv
from typing import Dict, List, Literal, Optional, Sequence
import math

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.ext.asyncio import AsyncSession

from db.deps import get_async_session
from db.repositories import (
    get_events,
    get_user_by_id,
    list_friends_for_event,
    list_friends_for_user,
)
from models import Event as EventDTO, User as UserDTO

router = APIRouter(prefix="/api/graph", tags=["graph"])

# ---------- Response models ----------
class GraphNode(BaseModel):
  id: str
  type: Literal["event", "person", "topic", "venue", "cohort"]
  label: str
  ring: int
  topic: Optional[str] = None
  starts_at: Optional[str] = None
  score: float = 0.0
  social_count: int = 0

class GraphEdge(BaseModel):
  source: str
  target: str
  type: str
  weight: float

class Explanation(BaseModel):
  reasons: List[str]

class GraphResponse(BaseModel):
  nodes: List[GraphNode]
  edges: List[GraphEdge]
  scores: Dict[str, float]
  explanations: Dict[str, Explanation]

# ---------- Config and logging ----------
ENABLE_GRAPH_DEBUG = getenv("ENABLE_GRAPH_DEBUG", "false").lower() == "true"

def _log(enabled: bool, msg: str) -> None:
  if enabled:
    print(f"[graph] {msg}")

# ---------- Helpers ----------
def _to_utc(dt: datetime) -> datetime:
  return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _parse_iso(val: Optional[datetime | str]) -> Optional[datetime]:
  if val is None:
    return None
  try:
    if isinstance(val, datetime):
      return _to_utc(val)
    return datetime.fromisoformat(str(val).replace("Z", "+00:00")).astimezone(timezone.utc)
  except Exception:
    return None

def _time_ring(starts_at: Optional[datetime | str]) -> int:
  dt = _parse_iso(starts_at)
  if not dt:
    return 2
  now = datetime.now(timezone.utc)
  delta = (dt - now).total_seconds()
  if delta < 0:
    return 2
  if delta <= 24 * 3600:
    return 0
  if delta <= 7 * 24 * 3600:
    return 1
  return 2

def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
  s = sum(max(w, 0.0) for w in weights.values())
  return {k: (max(v, 0.0) / s if s > 0 else 0.0) for k, v in weights.items()}

# ---------- Data access ----------
async def fetch_user(session: AsyncSession, user_id: str) -> UserDTO:
  orm_user = await get_user_by_id(session, user_id)
  if orm_user is None:
    raise HTTPException(status_code=404, detail="User not found")
  return UserDTO.model_validate(orm_user)

async def fetch_events_for_user(session: AsyncSession, caller_user_id: str) -> List[EventDTO]:
  orm_events = await get_events(session)
  out: List[EventDTO] = []
  for oe in orm_events:
    ev = EventDTO.model_validate(oe)
    orm_friends = await list_friends_for_event(session, caller_user_id, oe.id)
    ev.friends = [UserDTO.model_validate(u) for u in orm_friends]
    out.append(ev)
  return out

async def fetch_user_friends(session: AsyncSession, user_id: str) -> List[UserDTO]:
  orm_friends = await list_friends_for_user(session, user_id)
  return [UserDTO.model_validate(u) for u in orm_friends]

# ---------- Core computation ----------
def build_graph_and_rank(
  ego: UserDTO,
  events: Sequence[EventDTO],
  friends: Sequence[UserDTO],
  *,
  alpha: float = 0.15,
  w_content: float = 1.0,
  w_social: float = 2.0,
  w_time: float = 0.6,
  cosine_min: float = 0.05,
  social_cap: int = 5,
  debug: bool = False,
) -> GraphResponse:
  G = nx.DiGraph()

  # Prepare event nodes
  event_ids: List[str] = []
  event_texts: List[str] = []
  event_social: Dict[str, int] = {}
  for ev in events:
    eid = str(ev.id)
    ring = _time_ring(ev.starts_at)
    topic = (ev.category or "Other").strip() if ev.category else "Other"
    social_count = len(ev.friends or [])
    event_ids.append(eid)
    event_texts.append(" ".join(filter(None, [ev.name, ev.description or "", ev.category or ""])))
    event_social[eid] = int(social_count)

    G.add_node(
      f"event:{eid}",
      type="event",
      label=ev.name,
      ring=ring,
      starts_at=_parse_iso(ev.starts_at).isoformat() if _parse_iso(ev.starts_at) else None,
      topic=topic,
    )

  _log(debug, f"events={len(event_ids)}; friends={len(friends)}")

  # Content similarity edges
  if event_texts:
    tfidf = TfidfVectorizer(stop_words="english")
    X = tfidf.fit_transform(event_texts)
    S = cosine_similarity(X)
    added = 0
    n = len(event_ids)
    for i in range(n):
      for j in range(n):
        if i == j:
          continue
        sim = float(S[i, j])
        if sim > cosine_min:
          src = f"event:{event_ids[i]}"
          dst = f"event:{event_ids[j]}"
          G.add_edge(src, dst, type="content", weight=w_content * sim)
          added += 1
    _log(debug, f"content_edges={added}")

  # Time proximity edges with dynamic sigma (horizon-aware)
  # Horizon = max future start - now (>= 1 day), sigma ~ horizon/30 but >= 2h
  now = datetime.now(timezone.utc).timestamp()
  ts_list: List[float] = []
  ts_map: Dict[str, Optional[float]] = {}
  for ev in events:
    eid = str(ev.id)
    dt = _parse_iso(ev.starts_at)
    ts = dt.timestamp() if dt else None
    ts_map[eid] = ts
    if ts and ts > now:
      ts_list.append(ts)
  if ts_list:
    horizon = max(ts_list) - now
  else:
    horizon = 24 * 3600
  sigma = max(2 * 3600.0, horizon / 30.0)

  time_added = 0
  for i, evi in enumerate(events):
    ti = ts_map.get(str(evi.id))
    if ti is None:
      continue
    for j, evj in enumerate(events):
      if i == j:
        continue
      tj = ts_map.get(str(evj.id))
      if tj is None:
        continue
      dt = abs(ti - tj)
      proximity = math.exp(-(dt * dt) / (2 * sigma * sigma))
      if proximity > 0.05:
        G.add_edge(f"event:{str(evi.id)}", f"event:{str(evj.id)}", type="time", weight=w_time * proximity)
        time_added += 1
  _log(debug, f"time_edges={time_added}")

  # Social edges (ego -> event), capped
  for ev in events:
    eid = str(ev.id)
    count = min(event_social.get(eid, 0), social_cap)
    if count > 0:
      G.add_edge(f"user:{ego.id}", f"event:{eid}", type="social", weight=w_social * count)

  # Personalization vector: ego + friends
  p: Dict[str, float] = {f"user:{ego.id}": 1.0}
  for fr in friends:
    p[f"user:{fr.id}"] = 0.3
    G.add_node(f"user:{fr.id}", type="person", label=(fr.username or f"u{fr.id}"), ring=-1)
  for k in list(p.keys()):
    if k not in G:
      G.add_node(k, type="person", label=k, ring=-1)
  p = _normalize(p)

  # PPR
  scores = nx.pagerank(G, alpha=alpha, personalization=p, weight="weight")

  # Collect nodes and edges
  nodes: List[GraphNode] = []
  for nid, data in G.nodes(data=True):
    if data.get("type") == "event":
      eid = nid.split(":", 1)[1]
      nodes.append(GraphNode(
        id=nid,
        type="event",
        label=str(data.get("label", "")),
        ring=int(data.get("ring", 2)),
        topic=(data.get("topic") or None),
        starts_at=(data.get("starts_at") or None),
        score=float(scores.get(nid, 0.0)),
        social_count=int(event_social.get(eid, 0)),
      ))
    else:
      nodes.append(GraphNode(
        id=nid,
        type=str(data.get("type", "person")),
        label=str(data.get("label", "")),
        ring=int(data.get("ring", -1)),
        score=float(scores.get(nid, 0.0)),
      ))

  edges: List[GraphEdge] = []
  for u, v, ed in G.edges(data=True):
    edges.append(GraphEdge(
      source=u,
      target=v,
      type=str(ed.get("type", "rel")),
      weight=float(ed.get("weight", 1.0)),
    ))

  # Explanations
  explanations: Dict[str, Explanation] = {}
  for n in nodes:
    if n.type != "event":
      continue
    reasons: List[str] = []
    if n.social_count > 0:
      reasons.append(f"{n.social_count} friends interested/going")
    if n.ring == 0:
      reasons.append("happening today")
    elif n.ring == 1:
      reasons.append("coming this week")
    if n.topic:
      reasons.append(f"matches topic: {n.topic}")
    explanations[n.id] = Explanation(reasons=reasons)

  # Trim to top-K events
  event_nodes = [n for n in nodes if n.type == "event"]
  event_nodes.sort(key=lambda x: x.score, reverse=True)
  topK = 30
  top_ids = set(n.id for n in event_nodes[:topK])
  filtered_nodes = [n for n in nodes if (n.type != "event") or (n.id in top_ids)]
  filtered_edges = [e for e in edges if (e.source in top_ids or e.target in top_ids)]

  _log(debug, f"top_events={len(top_ids)} total_nodes={len(filtered_nodes)} edges={len(filtered_edges)}")

  return GraphResponse(
    nodes=filtered_nodes,
    edges=filtered_edges,
    scores={n.id: n.score for n in event_nodes[:topK]},
    explanations=explanations,
  )

# ---------- Route ----------
@router.get("/recommendations", response_model=GraphResponse)
async def get_graph_recommendations(
  user_id: str = Query(...),
  debug: bool = Query(False, description="Enable verbose debug logs for this request"),
  session: AsyncSession = Depends(get_async_session),
):
  debug = bool(debug or ENABLE_GRAPH_DEBUG)
  ego = await fetch_user(session, user_id)
  events = await fetch_events_for_user(session, user_id)
  # Filter out events that already ended
  now = datetime.now(timezone.utc)
  filtered_events = []
  for ev in events:
    end_dt = _parse_iso(getattr(ev, "ends_at", None))
    # Keep if no valid end time is provided, or if it ends in the future
    if (end_dt is None) or (end_dt > now):
      filtered_events.append(ev)
  events = filtered_events
  friends = await fetch_user_friends(session, user_id)
  if not events:
    raise HTTPException(status_code=404, detail="No upcoming events found")
  return build_graph_and_rank(
    ego,
    events,
    friends,
    debug=debug,
  )
