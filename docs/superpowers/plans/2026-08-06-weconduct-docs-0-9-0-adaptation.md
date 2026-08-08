# WeConduct Docs 0.9.0 Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Update the WeConduct user documentation repository so its version metadata, navigation, component catalog, user guidance, generated assets, and validation contracts describe the implemented 0.9.0 product surface without claiming deferred capabilities.

**Architecture:** Keep generated component pages and graph assets sourced from the 0.9.0 manifest. Keep manually authored guide pages responsible for workflow, security, external API, Debug, and deferred-scope explanations. Preserve historical 0.8.1 download assets and the old formal development documents outside this repository.

**Tech Stack:** MkDocs Material, Markdown, JSON graph assets, Python generation/validation tools, pytest, Vitest, Vite.

---

### Task 1: Establish the 0.9.0 catalog and site metadata

**Files:**
- Modify: `versions/weconduct.json`
- Modify: `mkdocs.yml`
- Modify: `docs/index.md`
- Modify: `docs/weconduct/index.md`
- Modify: `docs/weconduct/guide/component-library.md`
- Create: `data/weconduct-0.9.0/*` and generated component assets already staged in the worktree

- [x] Set the current WeConduct version to `0.9.0`, keep Weave at `0.5.0`, and expose the new network, input, security, and external API navigation entries.
- [x] Update the home and component-library descriptions to the generated 135-component, 26-group catalog.
- [x] Preserve historical 0.8.1 download files without linking current pages to them.

### Task 2: Add 0.9.0 workflow and boundary guides

**Files:**
- Create: `docs/weconduct/guide/network-automation.md`
- Create: `docs/weconduct/guide/encrypted-parameters-and-input.md`
- Create: `docs/weconduct/guide/external-api.md`

- [x] Document NetworkContext inheritance, anonymous/forked branches, port-overrides, HTTP/GraphQL Query/Mutation, upload/download/assert/batch, authentication, TLS, proxy, and cleanup.
- [x] Document encrypted initial parameters, pending input UI/CLI/API submission, sensitivity redaction, and timeout precedence.
- [x] Document only the externally verified API surface and mark unsupported GraphQL Subscription, plugin, public-network, and Debug API scope explicitly.

### Task 3: Align existing operational guides and component pages

**Files:**
- Modify: runtime, Debug, program/project settings, Python, graph editor, troubleshooting, security, Python, file-writing, and legacy HTTP pages under `docs/weconduct/`

- [x] Explain 0.9.0 startup recovery, diagnostics cleanup, Debug sensitive-value viewing, network restrictions, and the JSON/object text-file behavior.
- [x] Keep plaintext node secrets documented as possible but discouraged, and point users to encrypted parameters or input.request.
- [x] Keep the legacy `http.request` page as a migration notice to `network.http_request`.

### Task 4: Synchronize generators and validation contracts

**Files:**
- Modify: `tools/build_component_manifest.py`, `tools/build_component_pages.py`, `tools/build_document_catalog.py`, `tools/build_workflow_examples.py`, `tools/validate_pages.py`, `tools/validate_graph_examples.py`
- Modify: `tests/test_component_manifest.py`, `tests/test_component_page_generation.py`, `tests/test_document_catalog.py`, `tests/test_graph_examples.py`, `tests/test_page_contracts.py`, `tests/test_reference_content.py`, `tests/test_site_baseline.py`, `tests/test_workflow_examples.py`

- [x] Point tests at `data/weconduct-0.9.0`, expect 135 components and 26 groups, and retain semantic-version rather than fixed-version validation where specified.
- [x] Verify generated pages, graph assets, and example downloads all use the 0.9.0 catalog and current node keys.
- [x] Leave Weave version assertions and graph schema history assertions unchanged unless they directly describe the current WeConduct site.

### Task 5: Verify the documentation release surface

- [x] Run component/catalog generators and inspect their counts.
- [x] Run Python compilation, document pytest, graph tests/build, page validation, graph validation, and `mkdocs build --strict`.
- [x] Search for stale current-version claims, missing nav targets, unsupported 0.9.0 feature claims, and unintended secret examples.
- [x] Record the final command outputs and unresolved limitations in the handoff response.

## 6: Verification record (2026-08-07)

The final documentation pass was run against the current `0.9.0` source manifest.

```text
build_component_pages: groups=26 details=135 group_graphs=26 detail_graphs=135
build_workflow_examples: examples=10 graphs=10 downloads=10
build_document_catalog: 135 components, 26 groups, 0 unassigned, 0 duplicate paths
python -m pytest -q: 54 passed in 6.89s
npm run test:graph: 5 files passed, 15 tests passed
validate_pages.py: pages=238, missing_component_pages=0, missing_group_pages=0, errors=0
validate_graph_examples.py: files=176 errors=0
python -m compileall -q tools: exit 0
npm run build:graph: exit 0
python -m mkdocs build --strict: exit 0
```

The site build excludes `docs/superpowers/**` and treats generated component
detail pages as intentionally outside the explicit navigation tree. The
current release surface does not claim GraphQL Subscription, the scheme C
long-connection kernel, plugins, dynamic UI injection, or a public-network
deployment mode.
