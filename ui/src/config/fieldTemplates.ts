/** Shared field template config — consumed by MetadataEditorPanel and BaseNode inline editor */

export interface FieldTemplate {
  key: string
  type: 'string' | 'number' | 'boolean' | 'json' | 'object-map' | 'typed-value' | 'branch-list' | 'code' | 'component-schema'
  options?: string[]
}

export const PARAM_TEMPLATES: Record<string, FieldTemplate[]> = {
  'data.get_text':          [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }, { key: 'target_type', type: 'string', options: ['string', 'int', 'float', 'bool', 'json'] }],
  'data.get_attribute':     [{ key: 'selector', type: 'string' }, { key: 'attribute', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'data.get_value':         [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'data.get_element_count': [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'data.set_variables_batch': [{ key: 'variables', type: 'object-map' }],
  'data.set_variable':       [{ key: 'name', type: 'string' }, { key: 'value', type: 'typed-value' }],
  'data.convert_value':      [{ key: 'source_value', type: 'typed-value' }, { key: 'target_type', type: 'string', options: ['string', 'int', 'float', 'bool', 'json'] }, { key: 'variable_name', type: 'string' }, { key: 'in_place', type: 'boolean' }, { key: 'source_variable_name', type: 'string' }],
  'data.increment_variable': [{ key: 'variable_name', type: 'string' }, { key: 'step', type: 'number' }],
  'data.decrement_variable': [{ key: 'variable_name', type: 'string' }, { key: 'step', type: 'number' }],
  'data.list_index':         [{ key: 'variable_name', type: 'string' }, { key: 'value', type: 'typed-value' }, { key: 'output_variable_name', type: 'string' }],
  'browser.inject_js':       [{ key: 'script', type: 'code' }],
  'browser.run_js':          [{ key: 'script', type: 'code' }, { key: 'variable_name', type: 'string' }],
  'python.run':              [{ key: 'code', type: 'code' }],
  'browser.extract_web_table': [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'browser.extract_web_table_to_excel': [{ key: 'selector', type: 'string' }, { key: 'path', type: 'string' }, { key: 'sheet_name', type: 'string' }],
  'session.apply_auth_session': [{ key: 'cookies', type: 'json' }, { key: 'local_storage', type: 'object-map' }],
  'dialog.switch_dialog_mode': [{ key: 'mode', type: 'string' }],
  'dialog.watch_dialogs':      [{ key: 'timeout', type: 'number' }, { key: 'variable_name', type: 'string' }],
  'dialog.handle_dialogs':     [{ key: 'clear_after', type: 'boolean' }],
  'dialog.set_agent_config':   [{ key: 'default_action', type: 'string' }, { key: 'prompt_text', type: 'string' }],
  'graph.call_subgraph':       [{ key: 'subgraph_id', type: 'string' }, { key: 'inputs', type: 'object-map' }, { key: 'outputs', type: 'object-map' }],
  'flow.start':                [{ key: 'initial_variables', type: 'object-map' }],
  'message.emit':              [{ key: 'message', type: 'string' }, { key: 'severity', type: 'string', options: ['info', 'warning', 'error', 'fatal'] }],
  'control.parallel_fork':     [{ key: 'branches', type: 'branch-list' }],
  'control.join':              [{ key: 'branches', type: 'branch-list' }],
  'component.input':           [{ key: 'inputs', type: 'component-schema' }, { key: 'share_parent_variables', type: 'boolean' }],
  'component.output':          [{ key: 'outputs', type: 'component-schema' }],
  'network.http_request': [{ key: 'context_strategy', type: 'string', options: ['inherit', 'new', 'anonymous', 'fork', 'switch', 'reset'] }, { key: 'switch_context_id', type: 'string' }, { key: 'method', type: 'string' }, { key: 'url', type: 'string' }, { key: 'headers', type: 'object-map' }, { key: 'query', type: 'object-map' }, { key: 'body', type: 'typed-value' }, { key: 'timeout', type: 'number' }, { key: 'retry_policy', type: 'json' }, { key: 'auth', type: 'json' }, { key: 'tls', type: 'json' }, { key: 'proxy', type: 'json' }, { key: 'base_url', type: 'string' }, { key: 'response_limits', type: 'json' }],
  'network.upload': [{ key: 'context_strategy', type: 'string', options: ['inherit', 'new', 'anonymous', 'fork', 'switch', 'reset'] }, { key: 'url', type: 'string' }, { key: 'file_path', type: 'string' }, { key: 'field_name', type: 'string' }, { key: 'file_name', type: 'string' }, { key: 'multipart', type: 'boolean' }, { key: 'multipart_fields', type: 'object-map' }, { key: 'media_type', type: 'string' }, { key: 'checksum_sha256', type: 'string' }, { key: 'max_upload_bytes', type: 'number' }, { key: 'headers', type: 'object-map' }, { key: 'query', type: 'object-map' }, { key: 'timeout', type: 'number' }, { key: 'auth', type: 'json' }, { key: 'tls', type: 'json' }, { key: 'proxy', type: 'json' }, { key: 'base_url', type: 'string' }, { key: 'response_limits', type: 'json' }],
  'network.download': [{ key: 'context_strategy', type: 'string', options: ['inherit', 'new', 'anonymous', 'fork', 'switch', 'reset'] }, { key: 'method', type: 'string' }, { key: 'url', type: 'string' }, { key: 'headers', type: 'object-map' }, { key: 'query', type: 'object-map' }, { key: 'timeout', type: 'number' }, { key: 'auth', type: 'json' }, { key: 'tls', type: 'json' }, { key: 'proxy', type: 'json' }, { key: 'base_url', type: 'string' }, { key: 'response_limits', type: 'json' }],
  'network.response_assert': [{ key: 'expected_status_codes', type: 'json' }, { key: 'required_headers', type: 'object-map' }, { key: 'body_contains', type: 'string' }, { key: 'json_path_equals', type: 'object-map' }, { key: 'json_schema', type: 'json' }, { key: 'expected_final_url', type: 'string' }, { key: 'require_no_graphql_errors', type: 'boolean' }, { key: 'max_duration_ms', type: 'number' }, { key: 'max_size_bytes', type: 'number' }],
  'network.graphql_request': [{ key: 'context_strategy', type: 'string', options: ['inherit', 'new', 'anonymous', 'fork', 'switch', 'reset'] }, { key: 'endpoint', type: 'string' }, { key: 'query', type: 'code' }, { key: 'operation_name', type: 'string' }, { key: 'variables', type: 'object-map' }, { key: 'extensions', type: 'json' }, { key: 'headers', type: 'object-map' }, { key: 'timeout', type: 'number' }, { key: 'auth', type: 'json' }, { key: 'tls', type: 'json' }, { key: 'proxy', type: 'json' }, { key: 'base_url', type: 'string' }, { key: 'response_limits', type: 'json' }],
  'network.sse_connect': [{ key: 'context_strategy', type: 'string', options: ['inherit', 'new', 'anonymous', 'fork', 'switch', 'reset'] }, { key: 'action', type: 'string', options: ['connect', 'receive', 'close'] }, { key: 'connection_id', type: 'string' }, { key: 'url', type: 'string' }, { key: 'headers', type: 'object-map' }, { key: 'query', type: 'object-map' }, { key: 'timeout_seconds', type: 'number' }, { key: 'max_queue_size', type: 'number' }, { key: 'auth', type: 'json' }, { key: 'tls', type: 'json' }, { key: 'proxy', type: 'json' }, { key: 'base_url', type: 'string' }, { key: 'response_limits', type: 'json' }],
  'network.websocket_connect': [{ key: 'context_strategy', type: 'string', options: ['inherit', 'new', 'anonymous', 'fork', 'switch', 'reset'] }, { key: 'action', type: 'string', options: ['connect', 'send', 'receive', 'ping', 'close'] }, { key: 'connection_id', type: 'string' }, { key: 'url', type: 'string' }, { key: 'message', type: 'typed-value' }, { key: 'headers', type: 'object-map' }, { key: 'subprotocols', type: 'json' }, { key: 'timeout_seconds', type: 'number' }, { key: 'auth', type: 'json' }, { key: 'tls', type: 'json' }, { key: 'proxy', type: 'json' }, { key: 'base_url', type: 'string' }, { key: 'response_limits', type: 'json' }],
  'network.batch_request': [{ key: 'context_strategy', type: 'string', options: ['inherit', 'new', 'anonymous', 'fork', 'switch', 'reset'] }, { key: 'requests', type: 'json' }, { key: 'max_concurrency', type: 'number' }],
}

/** Known object-map field keys for detection */
export const OBJECT_MAP_KEYS = new Set(['initial_variables', 'variables', 'inputs', 'outputs', 'local_storage', 'headers', 'query', 'multipart_fields', 'required_headers', 'json_path_equals'])
