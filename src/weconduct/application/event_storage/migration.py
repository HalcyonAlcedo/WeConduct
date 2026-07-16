"""Legacy debug-history migration (design §8, migration plan §5).

Converts old monolithic ``{session_id}.msgpack`` full-document files into the
append-only session store. Also provides the shared event/keyframe
normalization so both migrated and freshly-appended payloads carry stable
``event_id`` / ``event_index`` / ``keyframe_id`` (matching the pre-0.8.2
``_normalize_session_payload`` contract the API/UI depend on).
"""
from __future__ import annotations

from pathlib import Path

from weconduct.application.event_storage.session_store import EventSessionStore
from weconduct.packaging.msgpack_codec import unpackb

# Keys that are metadata (manifest), everything else stays as-is.
_ARRAY_KEYS = ("events", "keyframes", "snapshots")


def normalize_payload(payload: dict) -> dict:
    """Backfill stable event/keyframe identifiers on a full-document payload."""
    debug_session = payload.get("debug_session")
    session_id = (
        debug_session.get("session_id")
        if isinstance(debug_session, dict) and isinstance(debug_session.get("session_id"), str)
        else "debug-session"
    )
    object_index = payload.get("object_index")
    graph_model_id = (
        object_index.get("graph_model_id")
        if isinstance(object_index, dict) and isinstance(object_index.get("graph_model_id"), str)
        else None
    )
    started_at = debug_session.get("started_at") if isinstance(debug_session, dict) else None

    events = payload.get("events")
    if isinstance(events, list):
        normalized_events: list[dict] = []
        for event_index, event in enumerate(events):
            if not isinstance(event, dict):
                continue
            node_id = event.get("node_id")
            instance_path = event.get("instance_path")
            if not isinstance(instance_path, list):
                instance_path = [
                    item for item in (graph_model_id, node_id)
                    if isinstance(item, str) and item.strip()
                ]
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id.strip():
                event_id = f"{session_id}:event:{event_index:08d}"
            recorded_at = event.get("recorded_at")
            if not isinstance(recorded_at, str) or not recorded_at.strip():
                recorded_at = started_at
            normalized_events.append(
                {
                    **event,
                    "event_id": event_id,
                    "event_index": event_index,
                    "recorded_at": recorded_at,
                    "session_id": session_id,
                    "instance_path": list(instance_path),
                    "iteration_stack": list(event["iteration_stack"])
                    if isinstance(event.get("iteration_stack"), list)
                    else [],
                }
            )
        payload["events"] = normalized_events

    keyframes = payload.get("keyframes")
    if isinstance(keyframes, list):
        normalized_events = payload.get("events") if isinstance(payload.get("events"), list) else []
        event_index_by_id = {
            event.get("event_id"): event.get("event_index")
            for event in normalized_events
            if isinstance(event, dict)
            and isinstance(event.get("event_id"), str)
            and isinstance(event.get("event_index"), int)
        }
        normalized_keyframes: list[dict] = []
        for keyframe_index, keyframe in enumerate(keyframes):
            if not isinstance(keyframe, dict):
                continue
            event_index = keyframe.get("event_index")
            if not isinstance(event_index, int):
                event_index = event_index_by_id.get(keyframe.get("event_id"))
            if not isinstance(event_index, int):
                event_index = len(normalized_events) + keyframe_index
            keyframe_id = keyframe.get("keyframe_id")
            if not isinstance(keyframe_id, str) or not keyframe_id.strip():
                keyframe_id = f"{session_id}:keyframe:{event_index:08d}:{keyframe_index:04d}"
            normalized_keyframes.append(
                {**keyframe, "keyframe_id": keyframe_id, "event_index": event_index}
            )
        payload["keyframes"] = normalized_keyframes
    return payload


def split_metadata(payload: dict) -> dict:
    """Return manifest metadata (payload minus the heavy arrays)."""
    return {key: value for key, value in payload.items() if key not in _ARRAY_KEYS}


def migrate_legacy_file(
    legacy_path: Path,
    session_id: str,
    store: EventSessionStore,
) -> dict | None:
    """Convert one legacy full-document msgpack into the append store.

    Returns the reconstructed payload on success. On failure raises; the
    caller keeps the legacy file and marks the session ``legacy_readonly``
    (migration plan §5.3).
    """
    raw = legacy_path.read_bytes()
    payload = unpackb(raw)
    if not isinstance(payload, dict):
        raise ValueError("legacy history payload is not an object")
    payload = normalize_payload(payload)
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    keyframes = payload.get("keyframes") if isinstance(payload.get("keyframes"), list) else []
    store.write_metadata(session_id, split_metadata(payload))
    store.append_events(session_id, [dict(item) for item in events if isinstance(item, dict)])
    store.append_checkpoints(
        session_id, [dict(item) for item in keyframes if isinstance(item, dict)]
    )
    return store.load_payload(session_id)


def read_legacy_readonly(legacy_path: Path) -> dict | None:
    """Read a legacy file without migrating (fallback path)."""
    if not legacy_path.exists():
        return None
    payload = unpackb(legacy_path.read_bytes())
    if not isinstance(payload, dict):
        return None
    return normalize_payload(payload)
