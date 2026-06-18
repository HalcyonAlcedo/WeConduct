from __future__ import annotations

from copy import deepcopy


GRAPH_NODE_DRAFT_DEFINITIONS: dict[str, dict] = {
    "flow.start": {
        "lowered_kind": "control",
        "expansion_role": "flow:start",
        "ports": [
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:variables",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.variables",
            }
        ],
        "node_config": {
            "initial_variables": {},
            "browser_config": {
                "headless": True,
                "slow_mo_ms": 0,
            },
        },
        "parameter_schema": {
            "initial_variables": {
                "type": "object",
                "required": False,
                "editor_kind": "key_value_map",
                "path_kind": None,
            },
            "browser_config": {
                "type": "object",
                "required": False,
                "editor_kind": "object",
                "path_kind": None,
            },
        },
    },
    "control.if": {
        "lowered_kind": "control",
        "expansion_role": "control:if",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "condition",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.condition",
            },
            {
                "port_id": "true",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.true",
            },
            {
                "port_id": "false",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.false",
            },
        ],
        "node_config": {
            "expression": "",
        },
    },
    "control.switch": {
        "lowered_kind": "control",
        "expansion_role": "control:switch",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "case:default",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.default",
            },
        ],
        "node_config": {
            "selector": "",
            "expression": "",
        },
    },
    "control.parallel_fork": {
        "lowered_kind": "control",
        "expansion_role": "control:parallel_fork",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "branch:left",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.branch:left",
            },
            {
                "port_id": "branch:right",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.branch:right",
            },
        ],
        "node_config": {
            "branches": [
                {"key": "left", "label": "Left"},
                {"key": "right", "label": "Right"},
            ],
        },
        "parameter_schema": {
            "branches": {
                "type": "array",
                "required": True,
                "editor_kind": "branch_list",
                "path_kind": None,
            },
        },
    },
    "control.join": {
        "lowered_kind": "control",
        "expansion_role": "control:join",
        "ports": [
            {
                "port_id": "in:left",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.branch:left",
            },
            {
                "port_id": "in:right",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.branch:right",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "branches": [
                {"key": "left", "label": "Left"},
                {"key": "right", "label": "Right"},
            ],
            "mode": "all",
            "quorum": None,
        },
        "parameter_schema": {
            "branches": {
                "type": "array",
                "required": True,
                "editor_kind": "branch_list",
                "path_kind": None,
            },
            "mode": {
                "type": "string",
                "required": True,
                "editor_kind": "select",
                "path_kind": None,
            },
            "quorum": {
                "type": "integer",
                "required": False,
                "editor_kind": "number",
                "path_kind": None,
            },
        },
    },
    "control.while": {
        "lowered_kind": "control",
        "expansion_role": "control:while",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "condition",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.condition",
            },
            {
                "port_id": "loop",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.loop",
            },
            {
                "port_id": "done",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.done",
            },
        ],
        "node_config": {
            "expression": "",
        },
    },
    "control.retry": {
        "lowered_kind": "control",
        "expansion_role": "control:retry",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "attempt",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.attempt",
            },
            {
                "port_id": "exhausted",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.exhausted",
            },
        ],
        "node_config": {
            "max_attempts": 3,
            "success_expression": "",
        },
    },
    "control.failover": {
        "lowered_kind": "control",
        "expansion_role": "control:failover",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "primary",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.primary",
            },
            {
                "port_id": "fallback:backup",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.fallback:backup",
            },
            {
                "port_id": "failed",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.failed",
            },
        ],
        "node_config": {
            "fallback_expression": "",
        },
    },
    "browser.navigate": {
        "lowered_kind": "execution",
        "expansion_role": "action:navigate",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:url",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.url",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "url": "",
        },
    },
    "browser.fill": {
        "lowered_kind": "execution",
        "expansion_role": "action:fill",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
            "value": "",
        },
    },
    "browser.click": {
        "lowered_kind": "execution",
        "expansion_role": "action:click",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
        },
    },
    "browser.wait_for_element": {
        "lowered_kind": "execution",
        "expansion_role": "action:wait_for_element",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
            "timeout": 10000,
        },
    },
    "browser.screenshot": {
        "lowered_kind": "execution",
        "expansion_role": "action:screenshot",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "save_file",
            },
        },
    },
    "browser.hover": {
        "lowered_kind": "execution",
        "expansion_role": "action:hover",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
        },
    },
    "browser.select_option": {
        "lowered_kind": "execution",
        "expansion_role": "action:select_option",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
            "value": "",
        },
    },
    "browser.wait_for_navigation": {
        "lowered_kind": "execution",
        "expansion_role": "action:wait_for_navigation",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:url_pattern",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.url_pattern",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "url_pattern": "",
            "timeout": 15000,
        },
    },
    "browser.wait_for_timeout": {
        "lowered_kind": "execution",
        "expansion_role": "action:wait_for_timeout",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "timeout": 0,
        },
    },
    "browser.recognize_captcha": {
        "lowered_kind": "execution",
        "expansion_role": "action:recognize_captcha",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "in:image_bytes_base64",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.image_bytes_base64",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:text",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.text",
            },
        ],
        "node_config": {
            "selector": "",
            "image_bytes_base64": "",
            "target_variable": "",
            "model_name": "",
            "runtime_root": "",
        },
    },
    "browser.switch_to_frame": {
        "lowered_kind": "execution",
        "expansion_role": "action:switch_to_frame",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
            "name": "",
            "url_contains": "",
            "index": -1,
        },
    },
    "browser.switch_to_parent_frame": {
        "lowered_kind": "execution",
        "expansion_role": "action:switch_to_parent_frame",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {},
    },
    "browser.switch_to_default_content": {
        "lowered_kind": "execution",
        "expansion_role": "action:switch_to_default_content",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {},
    },
    "browser.open_frame_page": {
        "lowered_kind": "execution",
        "expansion_role": "action:open_frame_page",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
            "name": "",
            "url_contains": "",
            "index": -1,
        },
    },
    "http.request": {
        "lowered_kind": "execution",
        "expansion_role": "action:request",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:url",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.url",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:body",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.body",
            },
        ],
        "node_config": {
            "method": "GET",
            "url": "",
            "headers": {},
            "timeout": 30,
            "body": None,
        },
    },
    "data.set_variable": {
        "lowered_kind": "execution",
        "expansion_role": "action:set_variable",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "name": "",
            "value": None,
        },
        "parameter_schema": {
            "name": {
                "type": "string",
                "required": True,
                "editor_kind": "text",
                "path_kind": None,
            },
            "value": {
                "type": "any",
                "required": False,
                "editor_kind": "value",
                "path_kind": None,
            },
        },
    },
    "data.get_variable": {
        "lowered_kind": "execution",
        "expansion_role": "action:get_variable",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "name": "",
        },
    },
    "data.get_text": {
        "lowered_kind": "execution",
        "expansion_role": "action:get_text",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "selector": "",
            "variable_name": "",
        },
    },
    "data.map": {
        "lowered_kind": "execution",
        "expansion_role": "action:map",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:source",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.source",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "source": None,
            "variable_name": "",
            "mode": "map",
        },
    },
    "data.get_attribute": {
        "lowered_kind": "execution",
        "expansion_role": "action:get_attribute",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "in:attribute",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.attribute",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "selector": "",
            "attribute": "",
            "variable_name": "",
        },
    },
    "data.get_value": {
        "lowered_kind": "execution",
        "expansion_role": "action:get_value",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "selector": "",
            "variable_name": "",
        },
    },
    "data.get_element_count": {
        "lowered_kind": "execution",
        "expansion_role": "action:get_element_count",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "selector": "",
            "variable_name": "",
        },
    },
    "data.set_variables_batch": {
        "lowered_kind": "execution",
        "expansion_role": "action:set_variables_batch",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "variables": {},
        },
    },
    "data.increment_variable": {
        "lowered_kind": "execution",
        "expansion_role": "action:increment_variable",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "step": 1,
        },
    },
    "data.decrement_variable": {
        "lowered_kind": "execution",
        "expansion_role": "action:decrement_variable",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "step": 1,
        },
    },
    "data.evaluate_expression": {
        "lowered_kind": "execution",
        "expansion_role": "action:evaluate_expression",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:expression",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.expression",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "expression": "",
            "variable_name": "",
        },
    },
    "data.regex_replace": {
        "lowered_kind": "execution",
        "expansion_role": "action:regex_replace",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:text",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.text",
            },
            {
                "port_id": "in:pattern",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.pattern",
            },
            {
                "port_id": "in:replacement",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.replacement",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "text": "",
            "pattern": "",
            "replacement": "",
            "variable_name": "",
        },
    },
    "data.create_list": {
        "lowered_kind": "execution",
        "expansion_role": "action:create_list",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "items": [],
        },
    },
    "data.list_append": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_append",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "value": None,
        },
    },
    "data.list_extend": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_extend",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:items",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.items",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "items": [],
        },
    },
    "data.list_get": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_get",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:index",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.index",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "index": 0,
            "output_variable_name": "",
        },
    },
    "data.list_set": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_set",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:index",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.index",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "index": 0,
            "value": None,
        },
    },
    "data.list_index": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_index",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "value": None,
            "output_variable_name": "",
        },
    },
    "data.list_length": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_length",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "output_variable_name": "",
        },
    },
    "data.list_insert": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_insert",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:index",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.index",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "index": 0,
            "value": None,
        },
    },
    "data.list_remove": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_remove",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:index",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.index",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "index": None,
            "value": None,
        },
    },
    "data.list_slice": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_slice",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:start",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.start",
            },
            {
                "port_id": "in:end",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.end",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
            "start": 0,
            "end": None,
            "output_variable_name": "",
        },
    },
    "data.list_sort": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_sort",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
        },
    },
    "data.list_reverse": {
        "lowered_kind": "execution",
        "expansion_role": "action:list_reverse",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "variable_name": "",
        },
    },
    "file.read_text_file": {
        "lowered_kind": "execution",
        "expansion_role": "action:read_text_file",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:text",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.text",
            },
        ],
        "node_config": {
            "path": "",
            "encoding": "utf-8",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
            "encoding": {
                "type": "string",
                "required": False,
                "editor_kind": "text",
                "path_kind": None,
            },
        },
    },
    "file.write_text_file": {
        "lowered_kind": "execution",
        "expansion_role": "action:write_text_file",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:content",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.content",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
            "encoding": "utf-8",
            "content": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "save_file",
            },
            "encoding": {
                "type": "string",
                "required": False,
                "editor_kind": "text",
                "path_kind": None,
            },
            "content": {
                "type": "string",
                "required": False,
                "editor_kind": "textarea",
                "path_kind": None,
            },
        },
    },
    "file.read_csv_cell": {
        "lowered_kind": "execution",
        "expansion_role": "action:read_csv_cell",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "path": "",
            "encoding": "utf-8",
            "has_header": True,
            "row_index": 0,
            "column": None,
            "variable_name": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "file.read_csv_row": {
        "lowered_kind": "execution",
        "expansion_role": "action:read_csv_row",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:row",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.row",
            },
        ],
        "node_config": {
            "path": "",
            "encoding": "utf-8",
            "has_header": True,
            "row_index": 0,
            "variable_name": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "file.read_csv_table": {
        "lowered_kind": "execution",
        "expansion_role": "action:read_csv_table",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:rows",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.rows",
            },
        ],
        "node_config": {
            "path": "",
            "encoding": "utf-8",
            "has_header": True,
            "variable_name": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "excel.read_cell": {
        "lowered_kind": "execution",
        "expansion_role": "action:read_excel_cell",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "cell": "",
            "variable_name": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "excel.read_row": {
        "lowered_kind": "execution",
        "expansion_role": "action:read_excel_row",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:row",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.row",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "row_index": 1,
            "variable_name": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "excel.read_table": {
        "lowered_kind": "execution",
        "expansion_role": "action:read_excel_table",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:rows",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.rows",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "has_header": True,
            "variable_name": "",
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "excel.write_cell": {
        "lowered_kind": "execution",
        "expansion_role": "action:write_excel_cell",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:value",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.value",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "cell": "",
            "value": None,
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "excel.write_row": {
        "lowered_kind": "execution",
        "expansion_role": "action:write_excel_row",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:data",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.data",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "row_index": 1,
            "data": [],
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "excel.write_table": {
        "lowered_kind": "execution",
        "expansion_role": "action:write_excel_table",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:data",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.data",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "data": [],
            "has_header": True,
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "excel.write_file": {
        "lowered_kind": "execution",
        "expansion_role": "action:write_excel_file",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "rows": [],
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "save_file",
            },
            "sheet_name": {
                "type": "string",
                "required": False,
                "editor_kind": "text",
                "path_kind": None,
            },
            "rows": {
                "type": "array",
                "required": False,
                "editor_kind": "array",
                "path_kind": None,
            },
        },
    },
    "excel.update_cells": {
        "lowered_kind": "execution",
        "expansion_role": "action:update_excel_cells",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "updates": [],
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
            "sheet_name": {
                "type": "string",
                "required": False,
                "editor_kind": "text",
                "path_kind": None,
            },
            "updates": {
                "type": "array",
                "required": False,
                "editor_kind": "array",
                "path_kind": None,
            },
        },
    },
    "excel.update_batch": {
        "lowered_kind": "execution",
        "expansion_role": "action:update_excel_batch",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "path": "",
            "sheet_name": "Sheet1",
            "condition": "",
            "updates": {},
        },
        "parameter_schema": {
            "path": {
                "type": "string",
                "required": True,
                "editor_kind": "path",
                "path_kind": "open_file",
            },
        },
    },
    "browser.extract_web_table": {
        "lowered_kind": "execution",
        "expansion_role": "action:extract_web_table",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:rows",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.rows",
            },
        ],
        "node_config": {
            "selector": "",
            "variable_name": "",
        },
    },
    "browser.extract_web_table_to_excel": {
        "lowered_kind": "execution",
        "expansion_role": "action:extract_web_table_to_excel",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:selector",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.selector",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "selector": "",
            "path": "",
            "sheet_name": "Sheet1",
        },
    },
    "browser.inject_js": {
        "lowered_kind": "execution",
        "expansion_role": "action:inject_js",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:script",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.script",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "script": "",
        },
    },
    "browser.run_js": {
        "lowered_kind": "execution",
        "expansion_role": "action:run_js",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "in:script",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.script",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:value",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.value",
            },
        ],
        "node_config": {
            "script": "",
            "variable_name": "",
        },
    },
    "python.run": {
        "lowered_kind": "execution",
        "expansion_role": "action:python_run",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "code": "",
        },
        "parameter_schema": {
            "code": {
                "type": "string",
                "required": True,
                "editor_kind": "code",
                "path_kind": None,
            },
        },
    },
    "graph.call_subgraph": {
        "lowered_kind": "execution",
        "expansion_role": "action:call_subgraph",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "subgraph_id": "",
            "inputs": {},
            "outputs": {},
        },
    },
    "control.foreach": {
        "lowered_kind": "control",
        "expansion_role": "control:foreach",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "items",
                "direction": "input",
                "relation_layer": "data",
                "semantic_slot": "in.items",
            },
            {
                "port_id": "loop",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.loop",
            },
            {
                "port_id": "done",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.done",
            },
        ],
        "node_config": {
            "variable": "",
            "item_var": "item",
            "index_var": "index",
        },
    },
    "control.jump_to_step": {
        "lowered_kind": "control",
        "expansion_role": "control:jump_to_step",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "target_node_id": "",
            "target_step": None,
            "condition": "true",
            "max_jumps": -1,
        },
    },
    "control.end_foreach": {
        "lowered_kind": "control",
        "expansion_role": "control:end_foreach",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {},
    },
    "control.foreach_continue": {
        "lowered_kind": "control",
        "expansion_role": "control:foreach_continue",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "condition": "true",
            "level": 1,
        },
    },
    "control.foreach_break": {
        "lowered_kind": "control",
        "expansion_role": "control:foreach_break",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "condition": "true",
            "level": 1,
        },
    },
    "call_blueprint": {
        "lowered_kind": "execution",
        "expansion_role": "action:call_blueprint",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "blueprint_id": "",
            "inputs": {},
            "outputs": {},
        },
    },
    "session.apply_auth_session": {
        "lowered_kind": "execution",
        "expansion_role": "action:apply_auth_session",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "cookies": [],
            "local_storage": {},
        },
    },
    "dialog.switch_dialog_mode": {
        "lowered_kind": "execution",
        "expansion_role": "action:switch_dialog_mode",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "mode": "auto",
        },
    },
    "dialog.watch_dialogs": {
        "lowered_kind": "execution",
        "expansion_role": "action:watch_dialogs",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:dialogs",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.dialogs",
            },
        ],
        "node_config": {
            "timeout": 0,
            "variable_name": "",
        },
    },
    "dialog.handle_dialogs": {
        "lowered_kind": "execution",
        "expansion_role": "action:handle_dialogs",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "clear_after": False,
        },
    },
    "dialog.set_agent_config": {
        "lowered_kind": "execution",
        "expansion_role": "action:set_agent_config",
        "ports": [
            {
                "port_id": "in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "in.control",
            },
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
        ],
        "node_config": {
            "default_action": "accept",
            "prompt_text": "",
        },
    },
}


def get_graph_node_draft_definition(resource_key: str) -> dict | None:
    definition = GRAPH_NODE_DRAFT_DEFINITIONS.get(resource_key)
    if definition is None:
        return None
    return deepcopy(definition)
