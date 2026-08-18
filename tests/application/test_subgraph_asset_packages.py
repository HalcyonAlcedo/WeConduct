from __future__ import annotations

import hashlib
import json
import shutil
from zipfile import ZipFile

import pytest

from weconduct.application import CompilationWorkbenchService
from weconduct.application.graph_upgrades import CURRENT_GRAPH_DATA_VERSION


def test_export_subgraph_asset_writes_root_resource_and_checksums(tmp_path) -> None:
    service = CompilationWorkbenchService()
    service.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    created = service.create_empty_custom_node_graph_resource(resource_name="可共享子图")
    resource_id = created["resource"]["resource_id"]
    output_path = tmp_path / "shared-component.wcsubgraph"

    exported = service.export_subgraph_asset_package(
        resource_id=resource_id,
        output_path=output_path,
    )

    assert exported["status"] == "exported"
    assert exported["output_path"] == str(output_path)
    assert output_path.is_file()

    with ZipFile(output_path) as archive:
        names = set(archive.namelist())
        resource_prefix = f"resources/{resource_id}"
        assert {
            "manifest.json",
            "graphs/root.graph.json",
            f"{resource_prefix}/manifest.json",
            f"{resource_prefix}/graph.json",
            "meta/checksums.json",
        } <= names

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["asset_schema_version"] == 1
        assert manifest["root_resource_id"] == resource_id
        assert manifest["asset_file_extension"] == ".wcsubgraph"

        checksums = json.loads(archive.read("meta/checksums.json"))
        entries = {entry["path"]: entry for entry in checksums["entries"]}
        assert "meta/checksums.json" not in entries
        for path, entry in entries.items():
            payload = archive.read(path)
            assert entry == {
                "path": path,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }


def test_export_subgraph_asset_collects_referenced_custom_node_graphs(tmp_path) -> None:
    service = CompilationWorkbenchService()
    service.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    inner = service.create_empty_custom_node_graph_resource(resource_name="内层子图")["resource"]
    outer = service.create_empty_custom_node_graph_resource(resource_name="外层子图")["resource"]

    outer_document = service.get_graph_document(document_id=outer["resource_id"])
    outer_graph = outer_document["graph_model"].model_dump(mode="json")
    outer_graph["document_id"] = outer["resource_id"]
    outer_graph["nodes"].append(
        {
            "node_id": "call-inner",
            "lowered_kind": "execution",
            "source_anchor_ref": "call-inner-anchor",
            "expansion_role": "action:custom_node_graph",
            "display_name": "调用内层子图",
            "node_kind": inner["resource_key"],
            "position": {"x": 180, "y": 120},
            "ports": [],
            "node_config": {"inputs": {}, "outputs": {}},
        }
    )
    service.save_graph_document(outer_graph)

    output_path = tmp_path / "nested-component.wcsubgraph"
    service.export_subgraph_asset_package(
        resource_id=outer["resource_id"],
        output_path=output_path,
    )

    with ZipFile(output_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["custom_node_graph_dependencies"] == [
            {
                "resource_id": inner["resource_id"],
                "resource_key": inner["resource_key"],
                "resource_type": "custom_node_graph",
            }
        ]
        assert f"resources/{inner['resource_id']}/manifest.json" in archive.namelist()
        assert f"resources/{inner['resource_id']}/graph.json" in archive.namelist()


def test_export_subgraph_asset_collects_referenced_builtin_components(tmp_path) -> None:
    service = CompilationWorkbenchService()
    service.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    component = service.create_empty_custom_node_graph_resource(
        resource_name="含内置组件子图"
    )["resource"]
    component_document = service.get_graph_document(document_id=component["resource_id"])
    component_graph = component_document["graph_model"].model_dump(mode="json")
    component_graph["document_id"] = component["resource_id"]
    component_graph["nodes"].append(
        {
            "node_id": "map-data",
            "lowered_kind": "execution",
            "source_anchor_ref": "map-data-anchor",
            "expansion_role": "transform:map",
            "display_name": "映射数据",
            "node_kind": "data.map",
            "position": {"x": 180, "y": 120},
            "ports": [],
            "node_config": {"mode": "map"},
        }
    )
    service.save_graph_document(component_graph)

    output_path = tmp_path / "builtin-dependency.wcsubgraph"
    service.export_subgraph_asset_package(
        resource_id=component["resource_id"],
        output_path=output_path,
    )

    with ZipFile(output_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["builtin_component_dependencies"] == [
        {
            "resource_id": "builtin:data.map",
            "resource_key": "data.map",
            "resource_type": "builtin_component",
        }
    ]


def test_export_subgraph_asset_includes_project_embedded_resources(tmp_path) -> None:
    service = CompilationWorkbenchService()
    service.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    embedded_path = tmp_path / "assets" / "instructions.txt"
    embedded_path.parent.mkdir()
    embedded_path.write_text("可共享资源", encoding="utf-8")
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["resource_policy"]["embedded_resources"] = ["assets/instructions.txt"]
    service.update_project_settings(project_settings=project_settings)
    component = service.create_empty_custom_node_graph_resource(
        resource_name="含嵌入资源子图"
    )["resource"]
    output_path = tmp_path / "embedded-resource.wcsubgraph"

    service.export_subgraph_asset_package(
        resource_id=component["resource_id"],
        output_path=output_path,
    )

    with ZipFile(output_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert archive.read("resources/embedded/assets/instructions.txt") == "可共享资源".encode(
            "utf-8"
        )

    assert manifest["embedded_resources"] == [
        {
            "relative_path": "assets/instructions.txt",
            "archive_path": "resources/embedded/assets/instructions.txt",
            "size": len("可共享资源".encode("utf-8")),
        }
    ]


def test_preflight_subgraph_asset_reports_embedded_resources_without_mutation(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source_root = tmp_path / "source"
    source_root.mkdir()
    source.save_project_as(project_path=source_root / "source-project.weconduct.json")
    embedded_path = source_root / "assets" / "instructions.txt"
    embedded_path.parent.mkdir()
    embedded_path.write_text("可共享资源", encoding="utf-8")
    project_settings = source.get_project_settings_document()["project_settings"]
    project_settings["resource_policy"]["embedded_resources"] = ["assets/instructions.txt"]
    source.update_project_settings(project_settings=project_settings)
    component = source.create_empty_custom_node_graph_resource(
        resource_name="预检嵌入资源子图"
    )["resource"]
    package_path = source_root / "embedded-resource.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=component["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target_root = tmp_path / "target"
    target_root.mkdir()
    target.save_project_as(project_path=target_root / "target-project.weconduct.json")
    target_package_path = target_root / package_path.name
    shutil.copy2(package_path, target_package_path)
    before = target.get_resource_registry_document()["registry_revision"]

    preflight = target.preflight_subgraph_asset_import(import_path=target_package_path)

    assert preflight["embedded_resources"] == [
        {
            "relative_path": "assets/instructions.txt",
            "archive_path": "resources/embedded/assets/instructions.txt",
            "size": len("可共享资源".encode("utf-8")),
        }
    ]
    assert target.get_resource_registry_document()["registry_revision"] == before
    assert not (target_root / "resources" / "embedded" / "assets" / "instructions.txt").exists()


def test_commit_subgraph_asset_import_materializes_embedded_resources(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source_root = tmp_path / "source"
    source_root.mkdir()
    source.save_project_as(project_path=source_root / "source-project.weconduct.json")
    embedded_path = source_root / "assets" / "instructions.txt"
    embedded_path.parent.mkdir()
    embedded_path.write_text("可共享资源", encoding="utf-8")
    source_settings = source.get_project_settings_document()["project_settings"]
    source_settings["resource_policy"]["embedded_resources"] = ["assets/instructions.txt"]
    source.update_project_settings(project_settings=source_settings)
    component = source.create_empty_custom_node_graph_resource(
        resource_name="导入嵌入资源子图"
    )["resource"]
    source_package_path = source_root / "embedded-resource.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=component["resource_id"],
        output_path=source_package_path,
    )

    target = CompilationWorkbenchService()
    target_root = tmp_path / "target"
    target_root.mkdir()
    target.save_project_as(project_path=target_root / "target-project.weconduct.json")
    target_package_path = target_root / source_package_path.name
    shutil.copy2(source_package_path, target_package_path)

    imported = target.commit_subgraph_asset_import(import_path=target_package_path)

    target_resource_path = target_root / "resources" / "embedded" / "assets" / "instructions.txt"
    assert imported["embedded_resources"] == [
        {
            "relative_path": "resources/embedded/assets/instructions.txt",
            "size": len("可共享资源".encode("utf-8")),
        }
    ]
    assert target_resource_path.read_text(encoding="utf-8") == "可共享资源"
    target_settings = target.get_project_settings_document()["project_settings"]
    assert target_settings["resource_policy"]["embedded_resources"] == [
        "resources/embedded/assets/instructions.txt"
    ]


def test_commit_subgraph_asset_import_rolls_back_when_embedded_resource_staging_fails(
    tmp_path,
    monkeypatch,
) -> None:
    source = CompilationWorkbenchService()
    source_root = tmp_path / "source"
    source_root.mkdir()
    source.save_project_as(project_path=source_root / "source-project.weconduct.json")
    embedded_path = source_root / "assets" / "instructions.txt"
    embedded_path.parent.mkdir()
    embedded_path.write_text("可共享资源", encoding="utf-8")
    source_settings = source.get_project_settings_document()["project_settings"]
    source_settings["resource_policy"]["embedded_resources"] = ["assets/instructions.txt"]
    source.update_project_settings(project_settings=source_settings)
    component = source.create_empty_custom_node_graph_resource(
        resource_name="嵌入资源回滚子图"
    )["resource"]
    source_package_path = source_root / "embedded-resource.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=component["resource_id"],
        output_path=source_package_path,
    )

    target = CompilationWorkbenchService()
    target_root = tmp_path / "target"
    target_root.mkdir()
    target.save_project_as(project_path=target_root / "target-project.weconduct.json")
    target_package_path = target_root / source_package_path.name
    shutil.copy2(source_package_path, target_package_path)
    before_revision = target.get_resource_registry_document()["registry_revision"]
    before_settings = target.get_project_settings_document()["project_settings"]
    original_write_bytes = type(embedded_path).write_bytes

    def fail_staging_write(path, data):
        if path.name == "instructions.txt":
            raise OSError("embedded resource staging write failed")
        return original_write_bytes(path, data)

    monkeypatch.setattr(type(embedded_path), "write_bytes", fail_staging_write)

    with pytest.raises(OSError, match="staging write failed"):
        target.commit_subgraph_asset_import(import_path=target_package_path)

    assert target.get_resource_registry_document()["registry_revision"] == before_revision
    assert target.get_project_settings_document()["project_settings"] == before_settings
    assert not (
        target_root / "resources" / "embedded" / "assets" / "instructions.txt"
    ).exists()


def test_commit_subgraph_asset_import_rolls_back_when_settings_persistence_fails(
    tmp_path,
    monkeypatch,
) -> None:
    source = CompilationWorkbenchService()
    source_root = tmp_path / "source"
    source_root.mkdir()
    source.save_project_as(project_path=source_root / "source-project.weconduct.json")
    embedded_path = source_root / "assets" / "instructions.txt"
    embedded_path.parent.mkdir()
    embedded_path.write_text("可共享资源", encoding="utf-8")
    source_settings = source.get_project_settings_document()["project_settings"]
    source_settings["resource_policy"]["embedded_resources"] = ["assets/instructions.txt"]
    source.update_project_settings(project_settings=source_settings)
    component = source.create_empty_custom_node_graph_resource(
        resource_name="设置回滚子图"
    )["resource"]
    source_package_path = source_root / "embedded-resource.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=component["resource_id"],
        output_path=source_package_path,
    )

    target = CompilationWorkbenchService()
    target_root = tmp_path / "target"
    target_root.mkdir()
    target.save_project_as(project_path=target_root / "target-project.weconduct.json")
    target_package_path = target_root / source_package_path.name
    shutil.copy2(source_package_path, target_package_path)
    target.update_project_settings(
        project_settings=target.get_project_settings_document()["project_settings"]
    )
    before_revision = target.get_resource_registry_document()["registry_revision"]
    before_settings = target.get_project_settings_document()["project_settings"]
    target_settings_path = (
        target._resolve_project_storage_root(target_root / "target-project.weconduct.json")
        / "project-settings.json"
    )
    before_settings_file = target_settings_path.read_bytes()

    def fail_settings_persistence() -> None:
        raise OSError("project settings persistence failed")

    monkeypatch.setattr(target, "_persist_project_settings_file_if_bound", fail_settings_persistence)

    with pytest.raises(OSError, match="settings persistence failed"):
        target.commit_subgraph_asset_import(import_path=target_package_path)

    assert target.get_resource_registry_document()["registry_revision"] == before_revision
    assert target.get_project_settings_document()["project_settings"] == before_settings
    assert target_settings_path.read_bytes() == before_settings_file
    assert not (
        target_root / "resources" / "embedded" / "assets" / "instructions.txt"
    ).exists()


def test_export_subgraph_asset_rejects_missing_custom_node_graph_dependency(tmp_path) -> None:
    service = CompilationWorkbenchService()
    service.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    outer = service.create_empty_custom_node_graph_resource(resource_name="外层子图")["resource"]

    outer_document = service.get_graph_document(document_id=outer["resource_id"])
    outer_graph = outer_document["graph_model"].model_dump(mode="json")
    outer_graph["document_id"] = outer["resource_id"]
    outer_graph["nodes"].append(
        {
            "node_id": "call-missing",
            "lowered_kind": "execution",
            "source_anchor_ref": "call-missing-anchor",
            "expansion_role": "action:custom_node_graph",
            "display_name": "调用缺失子图",
            "node_kind": "custom_node_graph:missing",
            "position": {"x": 180, "y": 120},
            "ports": [],
            "node_config": {"inputs": {}, "outputs": {}},
        }
    )
    service.save_graph_document(outer_graph)

    with pytest.raises(ValueError, match="custom node graph dependency not found"):
        service.export_subgraph_asset_package(
            resource_id=outer["resource_id"],
            output_path=tmp_path / "missing-dependency.wcsubgraph",
        )


def test_preflight_subgraph_asset_reports_importable_package_without_mutation(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="待导入子图"
    )["resource"]
    package_path = tmp_path / "shareable.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    preflight = target.preflight_subgraph_asset_import(import_path=package_path)

    assert preflight["can_import"] is True
    assert preflight["root_resource"]["resource_id"] == exported_resource["resource_id"]
    assert preflight["conflicts"] == []
    assert preflight["diagnostics"] == []
    assert target.get_resource_registry_document()["registry_revision"] == before


def test_preflight_subgraph_asset_reports_builtin_component_dependencies(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    component = source.create_empty_custom_node_graph_resource(
        resource_name="预检内置组件子图"
    )["resource"]
    component_document = source.get_graph_document(document_id=component["resource_id"])
    component_graph = component_document["graph_model"].model_dump(mode="json")
    component_graph["document_id"] = component["resource_id"]
    component_graph["nodes"].append(
        {
            "node_id": "map-data",
            "lowered_kind": "execution",
            "source_anchor_ref": "map-data-anchor",
            "expansion_role": "transform:map",
            "display_name": "映射数据",
            "node_kind": "data.map",
            "position": {"x": 180, "y": 120},
            "ports": [],
            "node_config": {"mode": "map"},
        }
    )
    source.save_graph_document(component_graph)
    package_path = tmp_path / "shareable.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=component["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")

    preflight = target.preflight_subgraph_asset_import(import_path=package_path)

    assert preflight["builtin_component_dependencies"] == [
        {
            "resource_id": "builtin:data.map",
            "resource_key": "data.map",
            "resource_type": "builtin_component",
        }
    ]


def test_preflight_subgraph_asset_rejects_checksum_mismatch_without_mutation(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="待校验子图"
    )["resource"]
    package_path = tmp_path / "original.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    tampered_path = tmp_path / "tampered.wcsubgraph"
    with ZipFile(package_path) as source_archive, ZipFile(tampered_path, mode="w") as target_archive:
        for name in source_archive.namelist():
            payload = source_archive.read(name)
            if name == "graphs/root.graph.json":
                payload = b'{"tampered":true}'
            target_archive.writestr(name, payload)

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    with pytest.raises(ValueError, match="checksum mismatch"):
        target.preflight_subgraph_asset_import(import_path=tampered_path)

    assert target.get_resource_registry_document()["registry_revision"] == before


def test_preflight_subgraph_asset_rejects_invalid_graph_document_without_mutation(
    tmp_path,
) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="图校验子图"
    )["resource"]
    package_path = tmp_path / "original.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    with ZipFile(package_path) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "meta/checksums.json"
        }
    graph_path = f"resources/{exported_resource['resource_id']}/graph.json"
    invalid_graph = json.loads(entries[graph_path])
    invalid_graph["nodes"] = "not-an-array"
    entries[graph_path] = json.dumps(invalid_graph, ensure_ascii=False).encode("utf-8")
    entries["meta/checksums.json"] = json.dumps(
        {
            "checksum_schema_version": 1,
            "algorithm": "sha256",
            "entries": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
                for name, payload in sorted(entries.items())
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    invalid_path = tmp_path / "invalid-graph.wcsubgraph"
    with ZipFile(invalid_path, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    with pytest.raises(ValueError, match="subgraph asset graph is invalid"):
        target.preflight_subgraph_asset_import(import_path=invalid_path)

    assert target.get_resource_registry_document()["registry_revision"] == before


def test_preflight_subgraph_asset_rejects_archive_path_traversal(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="安全子图"
    )["resource"]
    package_path = tmp_path / "original.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    unsafe_path = tmp_path / "unsafe-path.wcsubgraph"
    with ZipFile(package_path) as source_archive, ZipFile(unsafe_path, mode="w") as target_archive:
        for name in source_archive.namelist():
            target_archive.writestr(name, source_archive.read(name))
        target_archive.writestr("../escape.txt", b"must not be extracted")

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")

    with pytest.raises(ValueError, match="unsafe archive path"):
        target.preflight_subgraph_asset_import(import_path=unsafe_path)


def test_preflight_subgraph_asset_rejects_too_many_archive_entries_without_mutation(
    tmp_path,
) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="归档大小限制子图"
    )["resource"]
    package_path = tmp_path / "original.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    with ZipFile(package_path) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "meta/checksums.json"
        }
    for index in range(257):
        entries[f"payload/{index:03d}.bin"] = b""
    entries["meta/checksums.json"] = json.dumps(
        {
            "checksum_schema_version": 1,
            "algorithm": "sha256",
            "entries": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
                for name, payload in sorted(entries.items())
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    oversized_path = tmp_path / "too-many-files.wcsubgraph"
    with ZipFile(oversized_path, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    with pytest.raises(ValueError, match="too many files"):
        target.preflight_subgraph_asset_import(import_path=oversized_path)

    assert target.get_resource_registry_document()["registry_revision"] == before


def test_preflight_subgraph_asset_rejects_excessive_uncompressed_size_without_mutation(
    tmp_path,
) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="归档解压大小限制子图"
    )["resource"]
    package_path = tmp_path / "original.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    with ZipFile(package_path) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "meta/checksums.json"
        }
    entries["payload/large.bin"] = b"x" * (64 * 1024 * 1024 + 1)
    entries["meta/checksums.json"] = json.dumps(
        {
            "checksum_schema_version": 1,
            "algorithm": "sha256",
            "entries": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
                for name, payload in sorted(entries.items())
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    oversized_path = tmp_path / "too-large.wcsubgraph"
    with ZipFile(oversized_path, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    with pytest.raises(ValueError, match="uncompressed size exceeds"):
        target.preflight_subgraph_asset_import(import_path=oversized_path)

    assert target.get_resource_registry_document()["registry_revision"] == before


def test_preflight_subgraph_asset_rejects_incompatible_minimum_host_version(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="版本门禁子图"
    )["resource"]
    package_path = tmp_path / "original.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    with ZipFile(package_path) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "meta/checksums.json"
        }
    manifest = json.loads(entries["manifest.json"])
    manifest["minimum_host_version"] = "9.0.0"
    entries["manifest.json"] = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    entries["meta/checksums.json"] = json.dumps(
        {
            "checksum_schema_version": 1,
            "algorithm": "sha256",
            "entries": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
                for name, payload in sorted(entries.items())
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    incompatible_path = tmp_path / "incompatible.wcsubgraph"
    with ZipFile(incompatible_path, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")

    with pytest.raises(ValueError, match="minimum host version"):
        target.preflight_subgraph_asset_import(import_path=incompatible_path)


def test_preflight_subgraph_asset_rejects_unavailable_builtin_component_without_mutation(
    tmp_path,
) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="内置组件门禁子图"
    )["resource"]
    package_path = tmp_path / "original.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    with ZipFile(package_path) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "meta/checksums.json"
        }
    manifest = json.loads(entries["manifest.json"])
    manifest["builtin_component_dependencies"] = [
        {
            "resource_id": "builtin:not_available",
            "resource_key": "not_available",
            "resource_type": "builtin_component",
        }
    ]
    entries["manifest.json"] = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    entries["meta/checksums.json"] = json.dumps(
        {
            "checksum_schema_version": 1,
            "algorithm": "sha256",
            "entries": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
                for name, payload in sorted(entries.items())
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    invalid_path = tmp_path / "missing-builtin.wcsubgraph"
    with ZipFile(invalid_path, mode="w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    with pytest.raises(ValueError, match="builtin component dependency unavailable"):
        target.preflight_subgraph_asset_import(import_path=invalid_path)

    assert target.get_resource_registry_document()["registry_revision"] == before


def test_preflight_subgraph_asset_rejects_graph_compile_diagnostics_without_mutation(
    tmp_path,
) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="编译预检子图"
    )["resource"]
    graph_document = source.get_graph_document(document_id=exported_resource["resource_id"])
    graph = graph_document["graph_model"].model_dump(mode="json")
    graph["document_id"] = exported_resource["resource_id"]
    flow_start = {
        "node_id": "flow-start-1",
        "lowered_kind": "control",
        "source_anchor_ref": "flow-start-1-anchor",
        "expansion_role": "flow.start",
        "display_name": "流程入口",
        "node_kind": "flow.start",
        "position": {"x": 0, "y": 0},
        "ports": [],
        "node_config": {},
    }
    graph["nodes"] = [flow_start, {**flow_start, "node_id": "flow-start-2"}]
    source.save_graph_document(graph)
    package_path = tmp_path / "compile-invalid.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    preflight = target.preflight_subgraph_asset_import(import_path=package_path)

    assert preflight["can_import"] is False
    assert preflight["diagnostics"]
    assert any(
        diagnostic.get("stage") == "compile"
        for diagnostic in preflight["diagnostics"]
    )
    assert target.get_resource_registry_document()["registry_revision"] == before


def test_preflight_subgraph_asset_upgrades_legacy_graph_in_staging_only(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="旧版本图子图"
    )["resource"]
    graph_document = source.get_graph_document(document_id=exported_resource["resource_id"])
    graph = graph_document["graph_model"].model_dump(mode="json")
    graph["document_id"] = exported_resource["resource_id"]
    graph["root_metadata"]["graph_compatibility"] = {
        "graph_data_version": "0.5.2",
        "built_with_app_version": "0.5.2",
        "minimum_loader_app_version": "0.5.2",
        "last_upgraded_by_app_version": "0.5.2",
        "upgrade_history": [],
    }
    source.save_graph_document(graph)
    package_path = tmp_path / "legacy-graph.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    preflight = target.preflight_subgraph_asset_import(import_path=package_path)

    assert preflight["can_import"] is True
    assert preflight["graph_compatibility"][0]["upgraded"] is True
    assert preflight["graph_compatibility"][0]["from_version"] == "0.5.2"
    assert target.get_resource_registry_document()["registry_revision"] == before


def test_commit_subgraph_asset_import_persists_upgraded_legacy_graph(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="旧版本导入子图"
    )["resource"]
    graph_document = source.get_graph_document(document_id=exported_resource["resource_id"])
    graph = graph_document["graph_model"].model_dump(mode="json")
    graph["document_id"] = exported_resource["resource_id"]
    graph["root_metadata"]["graph_compatibility"] = {
        "graph_data_version": "0.5.2",
        "built_with_app_version": "0.5.2",
        "minimum_loader_app_version": "0.5.2",
        "last_upgraded_by_app_version": "0.5.2",
        "upgrade_history": [],
    }
    source.save_graph_document(graph)
    package_path = tmp_path / "legacy-graph.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")

    imported = target.commit_subgraph_asset_import(import_path=package_path)

    imported_graph = target.get_graph_document(
        document_id=imported["resource"]["resource_id"]
    )["graph_model"]
    assert imported_graph.root_metadata["graph_compatibility"]["graph_data_version"] == (
        CURRENT_GRAPH_DATA_VERSION
    )


def test_commit_subgraph_asset_import_registers_root_graph_in_one_revision(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="待导入子图"
    )["resource"]
    package_path = tmp_path / "shareable.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    imported = target.commit_subgraph_asset_import(import_path=package_path)

    assert imported["status"] == "imported"
    assert imported["resource"]["resource_id"] == exported_resource["resource_id"]
    assert target.get_resource_registry_document()["registry_revision"] == before + 1
    graph_document = target.get_graph_document(document_id=exported_resource["resource_id"])
    assert graph_document["graph_model"].graph_model_id == exported_resource["resource_id"]


def test_commit_subgraph_asset_import_registers_dependency_closure_atomically(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    inner = source.create_empty_custom_node_graph_resource(resource_name="内层子图")["resource"]
    outer = source.create_empty_custom_node_graph_resource(resource_name="外层子图")["resource"]
    outer_document = source.get_graph_document(document_id=outer["resource_id"])
    outer_graph = outer_document["graph_model"].model_dump(mode="json")
    outer_graph["document_id"] = outer["resource_id"]
    outer_graph["nodes"].append(
        {
            "node_id": "call-inner",
            "lowered_kind": "execution",
            "source_anchor_ref": "call-inner-anchor",
            "expansion_role": "action:custom_node_graph",
            "display_name": "调用内层子图",
            "node_kind": inner["resource_key"],
            "position": {"x": 180, "y": 120},
            "ports": [],
            "node_config": {"inputs": {}, "outputs": {}},
        }
    )
    source.save_graph_document(outer_graph)
    package_path = tmp_path / "nested.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=outer["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    before = target.get_resource_registry_document()["registry_revision"]

    imported = target.commit_subgraph_asset_import(import_path=package_path)

    assert imported["resource"]["resource_id"] == outer["resource_id"]
    registry = target.get_resource_registry_document()
    assert registry["registry_revision"] == before + 1
    assert {outer["resource_id"], inner["resource_id"]} <= {
        resource["resource_id"] for resource in registry["resources"]
    }
    imported_outer = target.get_graph_document(document_id=outer["resource_id"])
    assert imported_outer["graph_model"].nodes[0].node_kind == inner["resource_key"]


def test_preflight_subgraph_asset_reports_dependency_conflicts_for_abort(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    inner = source.create_empty_custom_node_graph_resource(resource_name="内层子图")["resource"]
    outer = source.create_empty_custom_node_graph_resource(resource_name="外层子图")["resource"]
    outer_document = source.get_graph_document(document_id=outer["resource_id"])
    outer_graph = outer_document["graph_model"].model_dump(mode="json")
    outer_graph["document_id"] = outer["resource_id"]
    outer_graph["nodes"].append(
        {
            "node_id": "call-inner",
            "lowered_kind": "execution",
            "source_anchor_ref": "call-inner-anchor",
            "expansion_role": "action:custom_node_graph",
            "display_name": "调用内层子图",
            "node_kind": inner["resource_key"],
            "position": {"x": 180, "y": 120},
            "ports": [],
            "node_config": {"inputs": {}, "outputs": {}},
        }
    )
    source.save_graph_document(outer_graph)
    package_path = tmp_path / "nested.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=outer["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    target.import_resource_from_record(inner)

    preflight = target.preflight_subgraph_asset_import(import_path=package_path)

    assert preflight["can_import"] is False
    assert preflight["conflicts"] == [
        {
            "resource_id": inner["resource_id"],
            "resource_key": inner["resource_key"],
            "resource_type": "custom_node_graph",
        }
    ]


def test_commit_subgraph_asset_rename_rewrites_nested_resource_reference(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    inner = source.create_empty_custom_node_graph_resource(resource_name="内层子图")["resource"]
    outer = source.create_empty_custom_node_graph_resource(resource_name="外层子图")["resource"]
    outer_document = source.get_graph_document(document_id=outer["resource_id"])
    outer_graph = outer_document["graph_model"].model_dump(mode="json")
    outer_graph["document_id"] = outer["resource_id"]
    outer_graph["nodes"].append(
        {
            "node_id": "call-inner",
            "lowered_kind": "execution",
            "source_anchor_ref": "call-inner-anchor",
            "expansion_role": "action:custom_node_graph",
            "display_name": "调用内层子图",
            "node_kind": inner["resource_key"],
            "position": {"x": 180, "y": 120},
            "ports": [],
            "node_config": {"inputs": {}, "outputs": {}},
        }
    )
    source.save_graph_document(outer_graph)
    package_path = tmp_path / "nested.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=outer["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    target.import_resource_from_record(inner)

    imported = target.commit_subgraph_asset_import(
        import_path=package_path,
        conflict_policy="rename",
    )

    renamed_inner_id = imported["resource_id_map"][inner["resource_id"]]
    assert renamed_inner_id != inner["resource_id"]
    assert target.get_graph_document(document_id=outer["resource_id"])["graph_model"].nodes[0].node_kind == renamed_inner_id
    assert target.get_graph_document(document_id=renamed_inner_id)["graph_model"].graph_model_id == renamed_inner_id


def test_commit_subgraph_asset_replace_replaces_compatible_existing_resource(tmp_path) -> None:
    source = CompilationWorkbenchService()
    source.save_project_as(project_path=tmp_path / "source-project.weconduct.json")
    exported_resource = source.create_empty_custom_node_graph_resource(
        resource_name="来源子图"
    )["resource"]
    package_path = tmp_path / "shareable.wcsubgraph"
    source.export_subgraph_asset_package(
        resource_id=exported_resource["resource_id"],
        output_path=package_path,
    )

    target = CompilationWorkbenchService()
    target.save_project_as(project_path=tmp_path / "target-project.weconduct.json")
    target.import_resource_from_record(
        {**exported_resource, "display_name": "现有子图"}
    )

    imported = target.commit_subgraph_asset_import(
        import_path=package_path,
        conflict_policy="replace",
    )

    assert imported["resource"]["resource_id"] == exported_resource["resource_id"]
    matching_resources = [
        resource
        for resource in target.get_resource_registry_document()["resources"]
        if resource["resource_id"] == exported_resource["resource_id"]
    ]
    assert len(matching_resources) == 1
    assert matching_resources[0]["display_name"] == "来源子图"
