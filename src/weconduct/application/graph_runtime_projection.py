from __future__ import annotations


class GraphRuntimeProjectionBuilder:
    def build_live_from_snapshot(
        self,
        *,
        preview: dict,
        events: list[dict],
        paused: bool,
    ) -> dict:
        paused_node_id = self._current_node_id(preview) if paused else None
        return self.build_live_projection(
            node_states=self._node_states(preview, paused_node_id=paused_node_id),
            active_paths=self._active_paths(preview),
            paused_node_id=paused_node_id,
            record_frame_node_ids=self._marker_node_ids(
                events,
                event_kind="record_frame.hit",
            ),
            skipped_node_ids=self._marker_node_ids(
                events,
                event_kind="node.skipped",
            ),
        )

    def build_history_from_snapshot(
        self,
        *,
        preview: dict,
        events: list[dict],
        paused: bool,
        event_index: int,
        keyframe_id: str | None,
    ) -> dict:
        paused_node_id = self._current_node_id(preview) if paused else None
        return self.build_history_projection(
            keyframe={
                "node_status_by_id": {
                    item["node_id"]: item["node_status"]
                    for item in self._node_states(preview, paused_node_id=paused_node_id)
                },
                "active_paths": self._active_paths(preview),
                "paused_node_id": paused_node_id,
                "record_frame_node_ids": self._marker_node_ids(
                    events,
                    event_kind="record_frame.hit",
                    max_event_index=event_index,
                ),
                "skipped_node_ids": self._marker_node_ids(
                    events,
                    event_kind="node.skipped",
                    max_event_index=event_index,
                ),
            },
            event_index=event_index,
            keyframe_id=keyframe_id,
        )

    def build_live_projection(
        self,
        *,
        node_states: list[dict],
        active_paths: list[list[str]],
        paused_node_id: str | None,
        record_frame_node_ids: list[str],
        skipped_node_ids: list[str],
    ) -> dict:
        return {
            "mode": "live",
            "node_status_by_id": {
                str(item["node_id"]): str(item["node_status"]) for item in node_states
            },
            "active_paths": [list(path) for path in active_paths],
            "paused_node_id": paused_node_id,
            "record_frame_node_ids": [
                node_id for node_id in record_frame_node_ids if isinstance(node_id, str)
            ],
            "skipped_node_ids": [
                node_id for node_id in skipped_node_ids if isinstance(node_id, str)
            ],
        }

    def build_history_projection(
        self,
        *,
        keyframe: dict,
        event_index: int,
        keyframe_id: str | None = None,
    ) -> dict:
        return {
            "mode": "history",
            "history_event_index": event_index,
            "history_keyframe_id": keyframe_id,
            "node_status_by_id": dict(keyframe.get("node_status_by_id", {})),
            "active_paths": [list(path) for path in keyframe.get("active_paths", [])],
            "paused_node_id": (
                keyframe.get("paused_node_id")
                if isinstance(keyframe.get("paused_node_id"), str)
                else None
            ),
            "record_frame_node_ids": [
                node_id
                for node_id in keyframe.get("record_frame_node_ids", [])
                if isinstance(node_id, str)
            ],
            "skipped_node_ids": [
                node_id
                for node_id in keyframe.get("skipped_node_ids", [])
                if isinstance(node_id, str)
            ],
        }

    @staticmethod
    def _current_node_id(preview: dict) -> str | None:
        current_node = preview.get("current_node")
        node_id = current_node.get("node_id") if isinstance(current_node, dict) else None
        return node_id if isinstance(node_id, str) and node_id.strip() else None

    @staticmethod
    def _active_paths(preview: dict) -> list[list[str]]:
        return [
            list(path)
            for path in preview.get("active_paths", [])
            if isinstance(path, list)
        ]

    @staticmethod
    def _node_states(preview: dict, *, paused_node_id: str | None) -> list[dict]:
        node_status_by_id: dict[str, str] = {}
        executed_node_ids = preview.get("executed_node_ids")
        if isinstance(executed_node_ids, list):
            for node_id in executed_node_ids:
                if isinstance(node_id, str) and node_id.strip():
                    node_status_by_id[node_id] = "completed"
        queued_node_ids = preview.get("queued_node_ids")
        if isinstance(queued_node_ids, list):
            for node_id in queued_node_ids:
                if (
                    isinstance(node_id, str)
                    and node_id.strip()
                    and node_id not in node_status_by_id
                ):
                    node_status_by_id[node_id] = "waiting"
        current_node_id = GraphRuntimeProjectionBuilder._current_node_id(preview)
        if current_node_id is not None:
            node_status_by_id[current_node_id] = "running"
        if paused_node_id is not None:
            node_status_by_id[paused_node_id] = "paused"
        return [
            {"node_id": node_id, "node_status": node_status}
            for node_id, node_status in node_status_by_id.items()
        ]

    @staticmethod
    def _marker_node_ids(
        events: list[dict],
        *,
        event_kind: str,
        max_event_index: int | None = None,
    ) -> list[str]:
        marker_node_ids: list[str] = []
        for event in events:
            if not isinstance(event, dict) or event.get("event_kind") != event_kind:
                continue
            if (
                isinstance(max_event_index, int)
                and isinstance(event.get("event_index"), int)
                and event["event_index"] > max_event_index
            ):
                continue
            node_id = event.get("node_id")
            if isinstance(node_id, str) and node_id.strip() and node_id not in marker_node_ids:
                marker_node_ids.append(node_id)
        return marker_node_ids
