from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

import build_document_catalog


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_ROOT = ROOT / "docs"
DEFAULT_MANIFEST_PATH = ROOT / "data" / "weconduct-0.8.1" / "components.json"
DEFAULT_GROUPS_PATH = ROOT / "data" / "weconduct-0.8.1" / "component-groups.json"
REQUIRED_COMPONENT_SECTIONS = [
    "功能说明",
    "适用场景",
    "前置条件与权限",
    "端口说明",
    "配置参数",
    "输入、输出与副作用",
    "使用示例",
    "预期结果",
    "常见错误",
    "限制与注意事项",
    "相关节点",
]
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-root", default=str(DEFAULT_DOCS_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--groups", default=str(DEFAULT_GROUPS_PATH))
    parser.add_argument("--product")
    parser.add_argument("--family")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--json-report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    docs_root = Path(args.docs_root).resolve()
    selectors = build_document_catalog.parse_selectors(args.family)
    products = build_document_catalog.parse_selectors(args.product)
    validate_product_selectors(products)

    manifest = build_document_catalog.load_manifest(Path(args.manifest).resolve())
    group_catalog = build_document_catalog.load_group_catalog(Path(args.groups).resolve())
    catalog = build_document_catalog.validate_catalog(manifest=manifest, catalog=group_catalog)
    build_document_catalog.validate_family_selectors(catalog, selectors)
    filtered_catalog = build_document_catalog.filter_catalog(catalog, selectors)

    report = validate_pages(
        docs_root=docs_root,
        catalog=filtered_catalog,
        allow_incomplete=args.allow_incomplete,
        product_filters=products,
    )
    if args.json_report:
        write_json(Path(args.json_report).resolve(), report)

    for error in report["errors"]:
        print(f"ERROR: {error}", file=sys.stderr)
    print(format_summary(report))

    has_blocking_errors = bool(report["errors"])
    has_missing_pages = (
        report["summary"]["missing_component_pages"] > 0
        or report["summary"]["missing_group_pages"] > 0
    )
    if has_blocking_errors:
        return 1
    if has_missing_pages and not args.allow_incomplete:
        return 1
    return 0


def validate_pages(
    *,
    docs_root: Path,
    catalog: dict[str, Any],
    allow_incomplete: bool,
    product_filters: set[str],
) -> dict[str, Any]:
    page_records: list[dict[str, Any]] = []
    errors: list[str] = []
    doc_id_locations: Counter[str] = Counter()
    doc_id_to_paths: dict[str, list[str]] = {}

    for path in sorted(docs_root.rglob("*.md")):
        relative_path = path.relative_to(docs_root).as_posix()
        if product_filters and not matches_product_filter(relative_path, product_filters):
            continue
        page = parse_markdown_page(path, docs_root)
        page_records.append(page)
        if page["errors"]:
            errors.extend(page["errors"])
            continue
        doc_id = page["front_matter"]["doc_id"]
        doc_id_locations[doc_id] += 1
        doc_id_to_paths.setdefault(doc_id, []).append(relative_path)
        errors.extend(validate_page_scope(page))

    for doc_id, count in sorted(doc_id_locations.items()):
        if count > 1:
            errors.append(
                f"duplicate doc_id {doc_id} at {', '.join(sorted(doc_id_to_paths[doc_id]))}"
            )

    component_pages = {
        assignment["page_path"][len("docs/") :]: assignment
        for assignment in catalog["assignments"]
        if not product_filters or "weconduct" in product_filters
    }
    group_pages = {
        group["index_path"][len("docs/") :]: group
        for group in catalog["groups"]
        if not product_filters or "weconduct" in product_filters
    }
    pages_by_path = {page["relative_path"]: page for page in page_records}

    missing_component_pages = sorted(
        relative_path for relative_path in component_pages if relative_path not in pages_by_path
    )
    missing_group_pages = sorted(
        relative_path for relative_path in group_pages if relative_path not in pages_by_path
    )

    for relative_path, assignment in sorted(component_pages.items()):
        page = pages_by_path.get(relative_path)
        if page is None or page["errors"]:
            continue
        front_matter = page["front_matter"]
        expected_doc_id = f"component:{assignment['resource_key']}"
        if front_matter["doc_id"] != expected_doc_id:
            errors.append(
                f"{relative_path} doc_id mismatch: {front_matter['doc_id']!r} expected {expected_doc_id!r}"
            )
        headings = extract_headings(page["body"])
        missing_sections = [
            section for section in REQUIRED_COMPONENT_SECTIONS if section not in headings
        ]
        if missing_sections:
            errors.append(
                f"{relative_path} missing sections: {', '.join(missing_sections)}"
            )

    for relative_path, group in sorted(group_pages.items()):
        page = pages_by_path.get(relative_path)
        if page is None or page["errors"]:
            continue
        front_matter = page["front_matter"]
        expected_doc_id = f"component-group:{group['group_id']}"
        if front_matter["doc_id"] != expected_doc_id:
            errors.append(
                f"{relative_path} doc_id mismatch: {front_matter['doc_id']!r} expected {expected_doc_id!r}"
            )

    summary = {
        "pages": len(page_records),
        "missing_component_pages": len(missing_component_pages),
        "missing_group_pages": len(missing_group_pages),
        "errors": len(errors),
        "allow_incomplete": allow_incomplete,
    }
    return {
        "docs_root": docs_root.as_posix(),
        "summary": summary,
        "missing_component_pages": missing_component_pages,
        "missing_group_pages": missing_group_pages,
        "errors": sorted(errors),
    }


def validate_product_selectors(product_filters: set[str]) -> None:
    if not product_filters:
        return
    valid_products = {"weconduct", "weave"}
    unknown = sorted(product_filters - valid_products)
    if unknown:
        raise SystemExit(
            f"unknown --product selector(s): {', '.join(unknown)}; allowed: weconduct, weave"
        )


def matches_product_filter(relative_path: str, product_filters: set[str]) -> bool:
    if relative_path == "index.md":
        return "site" in product_filters
    if relative_path.startswith("weconduct/"):
        return "weconduct" in product_filters
    if relative_path.startswith("weave/"):
        return "weave" in product_filters
    return False


def parse_markdown_page(path: Path, docs_root: Path) -> dict[str, Any]:
    relative_path = path.relative_to(docs_root).as_posix()
    text = path.read_text(encoding="utf-8")
    front_matter, body, errors = split_front_matter(text, relative_path)
    return {
        "path": path,
        "relative_path": relative_path,
        "front_matter": front_matter,
        "body": body,
        "errors": errors,
    }


def split_front_matter(
    text: str,
    relative_path: str,
) -> tuple[dict[str, Any], str, list[str]]:
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---\n"):
        return {}, text, [f"{relative_path} missing front matter"]
    parts = text.split("---", 2)
    if len(parts) != 3:
        return {}, text, [f"{relative_path} malformed front matter delimiter"]
    try:
        front_matter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        return {}, parts[2], [f"{relative_path} malformed front matter: {exc}"]
    if not isinstance(front_matter, dict):
        return {}, parts[2], [f"{relative_path} front matter must be a mapping"]

    errors: list[str] = []
    for field_name in ("product", "version", "doc_id"):
        value = front_matter.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{relative_path} front matter missing {field_name}")
        else:
            front_matter[field_name] = value.strip()
    return front_matter, parts[2].strip(), errors


def validate_page_scope(page: dict[str, Any]) -> list[str]:
    relative_path = page["relative_path"]
    front_matter = page["front_matter"]
    product = front_matter["product"]
    version = front_matter["version"]
    doc_id = front_matter["doc_id"]
    errors: list[str] = []

    if relative_path == "index.md":
        if product != "site" or version != "latest" or doc_id != "site:index":
            errors.append(
                "index.md must declare product=site, version=latest, doc_id=site:index"
            )
        return errors

    if relative_path.startswith("weconduct/"):
        if product != "weconduct":
            errors.append(f"{relative_path} product mismatch: {product!r} expected 'weconduct'")
        if version != "0.8.1":
            errors.append(f"{relative_path} version mismatch: {version!r} expected '0.8.1'")
        return errors

    if relative_path.startswith("weave/"):
        if product != "weave":
            errors.append(f"{relative_path} product mismatch: {product!r} expected 'weave'")
        if version != "0.5.0":
            errors.append(f"{relative_path} version mismatch: {version!r} expected '0.5.0'")
        return errors

    if relative_path.startswith("reference/"):
        if product != "site":
            errors.append(f"{relative_path} product mismatch: {product!r} expected 'site'")
        if version != "latest":
            errors.append(f"{relative_path} version mismatch: {version!r} expected 'latest'")
        if not isinstance(doc_id, str) or not doc_id.startswith("site:reference:"):
            errors.append(
                f"{relative_path} doc_id mismatch: {doc_id!r} expected prefix 'site:reference:'"
            )
        return errors

    errors.append(f"{relative_path} is outside supported product roots")
    return errors


def extract_headings(body: str) -> set[str]:
    return {match.group("title").strip() for match in HEADING_RE.finditer(body)}


def format_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return (
        f"pages={summary['pages']}, "
        f"missing_component_pages={summary['missing_component_pages']}, "
        f"missing_group_pages={summary['missing_group_pages']}, "
        f"errors={summary['errors']}"
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
