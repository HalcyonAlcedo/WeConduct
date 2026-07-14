from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = ROOT / "data" / "weconduct-0.8.1" / "components.json"
DEFAULT_GROUPS_PATH = ROOT / "data" / "weconduct-0.8.1" / "component-groups.json"
EXPECTED_PRODUCT = "weconduct"
EXPECTED_VERSION = "0.8.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--groups", default=str(DEFAULT_GROUPS_PATH))
    parser.add_argument("--report")
    parser.add_argument("--list", action="store_true", dest="list_mode")
    parser.add_argument("--family")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    groups_path = Path(args.groups).resolve()
    selectors = parse_selectors(args.family)

    manifest = load_manifest(manifest_path)
    catalog = load_group_catalog(groups_path)
    validated = validate_catalog(manifest=manifest, catalog=catalog)
    filtered = filter_catalog(validated, selectors)

    if args.report:
        write_json(Path(args.report).resolve(), filtered)

    if args.list_mode:
        emit_list(filtered)
        return 0

    print(format_summary(filtered["summary"]))
    return 0


def parse_selectors(raw_value: str | None) -> set[str]:
    if raw_value is None:
        return set()
    return {part.strip() for part in raw_value.split(",") if part.strip()}


def load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"manifest must be a list: {path}")
    return payload


def load_group_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"groups payload must be an object: {path}")
    return payload


def validate_catalog(
    *,
    manifest: list[dict[str, Any]],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    product = catalog.get("product")
    version = catalog.get("version")
    if product != EXPECTED_PRODUCT:
        raise SystemExit(f"product mismatch: {product!r} expected {EXPECTED_PRODUCT!r}")
    if version != EXPECTED_VERSION:
        raise SystemExit(f"version mismatch: {version!r} expected {EXPECTED_VERSION!r}")

    groups = catalog.get("groups")
    assignments = catalog.get("assignments")
    if not isinstance(groups, list):
        raise SystemExit("groups must be a list")
    if not isinstance(assignments, dict):
        raise SystemExit("assignments must be an object")

    manifest_by_key: dict[str, dict[str, Any]] = {}
    for item in manifest:
        resource_key = item.get("resource_key")
        if not isinstance(resource_key, str) or not resource_key.strip():
            raise SystemExit("manifest contains invalid resource_key")
        if resource_key in manifest_by_key:
            raise SystemExit(f"duplicate manifest resource_key: {resource_key}")
        manifest_by_key[resource_key] = item

    group_rows: list[dict[str, Any]] = []
    group_ids: set[str] = set()
    index_paths: set[str] = set()
    detail_dirs: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            raise SystemExit("group entry must be an object")
        row = normalize_group(group)
        group_id = row["group_id"]
        if group_id in group_ids:
            raise SystemExit(f"duplicate group_id: {group_id}")
        if row["index_path"] in index_paths:
            raise SystemExit(f"duplicate index_path: {row['index_path']}")
        if row["detail_dir"] in detail_dirs:
            raise SystemExit(f"duplicate detail_dir: {row['detail_dir']}")
        group_ids.add(group_id)
        index_paths.add(row["index_path"])
        detail_dirs.add(row["detail_dir"])
        group_rows.append(row)

    assignment_keys = set(assignments)
    manifest_keys = set(manifest_by_key)
    if assignment_keys != manifest_keys:
        missing = sorted(manifest_keys - assignment_keys)
        extra = sorted(assignment_keys - manifest_keys)
        details: list[str] = []
        if missing:
            details.append(f"missing_assignments={missing}")
        if extra:
            details.append(f"unexpected_assignments={extra}")
        raise SystemExit("assignment key mismatch: " + "; ".join(details))

    assignment_rows: list[dict[str, Any]] = []
    page_paths: set[str] = set()
    for resource_key in sorted(manifest_keys):
        raw_assignment = assignments[resource_key]
        if not isinstance(raw_assignment, dict):
            raise SystemExit(f"assignment must be an object: {resource_key}")
        row = normalize_assignment(resource_key, raw_assignment)
        primary_group_id = row["primary_group_id"]
        if primary_group_id not in group_ids:
            raise SystemExit(
                f"assignment {resource_key} references unknown primary_group_id {primary_group_id}"
            )
        for related_group_id in row["related_group_ids"]:
            if related_group_id not in group_ids:
                raise SystemExit(
                    f"assignment {resource_key} references unknown related_group_id {related_group_id}"
                )
        if row["page_path"] in page_paths:
            raise SystemExit(f"duplicate page_path: {row['page_path']}")
        page_paths.add(row["page_path"])
        assignment_rows.append(
            {
                **row,
                "resource_key": resource_key,
                "display_name_zh": str(manifest_by_key[resource_key].get("display_name_zh", "")).strip(),
                "capability_domain": str(manifest_by_key[resource_key].get("capability_domain", "")).strip(),
                "component_library_visible": bool(
                    manifest_by_key[resource_key].get("component_library_visible")
                ),
                "compatibility_only": bool(manifest_by_key[resource_key].get("compatibility_only")),
            }
        )

    summary = build_summary(group_rows, assignment_rows)
    return {
        "product": EXPECTED_PRODUCT,
        "version": EXPECTED_VERSION,
        "groups": group_rows,
        "assignments": assignment_rows,
        "summary": summary,
    }


def normalize_group(group: dict[str, Any]) -> dict[str, str]:
    required_fields = ["group_id", "family", "title_zh", "description_zh", "index_path", "detail_dir"]
    normalized: dict[str, str] = {}
    for field_name in required_fields:
        value = group.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(f"group missing non-empty {field_name}")
        normalized[field_name] = value.strip()
    return normalized


def normalize_assignment(resource_key: str, assignment: dict[str, Any]) -> dict[str, Any]:
    primary_group_id = assignment.get("primary_group_id")
    page_path = assignment.get("page_path")
    related_group_ids = assignment.get("related_group_ids")
    if not isinstance(primary_group_id, str) or not primary_group_id.strip():
        raise SystemExit(f"assignment {resource_key} missing primary_group_id")
    if not isinstance(page_path, str) or not page_path.strip():
        raise SystemExit(f"assignment {resource_key} missing page_path")
    if not isinstance(related_group_ids, list):
        raise SystemExit(f"assignment {resource_key} missing related_group_ids list")
    normalized_related: list[str] = []
    for group_id in related_group_ids:
        if not isinstance(group_id, str) or not group_id.strip():
            raise SystemExit(f"assignment {resource_key} has invalid related_group_ids entry")
        normalized_related.append(group_id.strip())
    return {
        "primary_group_id": primary_group_id.strip(),
        "page_path": page_path.strip(),
        "related_group_ids": normalized_related,
    }


def build_summary(groups: list[dict[str, Any]], assignments: list[dict[str, Any]]) -> dict[str, int]:
    page_paths = [row["page_path"] for row in assignments]
    index_paths = [row["index_path"] for row in groups]
    return {
        "components": len(assignments),
        "groups": len(groups),
        "unassigned": 0,
        "duplicate_page_paths": count_duplicates(page_paths),
        "duplicate_index_paths": count_duplicates(index_paths),
    }


def count_duplicates(values: list[str]) -> int:
    counter = Counter(values)
    return sum(1 for count in counter.values() if count > 1)


def filter_catalog(catalog: dict[str, Any], selectors: set[str]) -> dict[str, Any]:
    if not selectors:
        return catalog

    filtered_groups = [
        group
        for group in catalog["groups"]
        if group["family"] in selectors or group["group_id"] in selectors
    ]
    allowed_group_ids = {group["group_id"] for group in filtered_groups}
    filtered_assignments = [
        assignment
        for assignment in catalog["assignments"]
        if assignment["primary_group_id"] in allowed_group_ids
    ]
    return {
        "product": catalog["product"],
        "version": catalog["version"],
        "groups": filtered_groups,
        "assignments": filtered_assignments,
        "summary": build_summary(filtered_groups, filtered_assignments),
    }


def emit_list(catalog: dict[str, Any]) -> None:
    family_by_group_id = {group["group_id"]: group["family"] for group in catalog["groups"]}
    for assignment in sorted(
        catalog["assignments"],
        key=lambda item: (family_by_group_id[item["primary_group_id"]], item["primary_group_id"], item["resource_key"]),
    ):
        row = [
            family_by_group_id[assignment["primary_group_id"]],
            assignment["primary_group_id"],
            assignment["resource_key"],
            assignment["display_name_zh"],
            assignment["page_path"],
        ]
        print("\t".join(row))


def format_summary(summary: dict[str, int]) -> str:
    return (
        f"{summary['components']} components, "
        f"{summary['groups']} groups, "
        f"{summary['unassigned']} unassigned, "
        f"{summary['duplicate_page_paths']} duplicate paths"
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.exit(0)
