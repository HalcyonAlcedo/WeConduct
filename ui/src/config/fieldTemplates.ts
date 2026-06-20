/** Shared field template config — consumed by MetadataEditorPanel and BaseNode inline editor */

export interface FieldTemplate {
  key: string
  type: 'string' | 'number' | 'boolean' | 'json' | 'object-map' | 'typed-value' | 'branch-list' | 'code'
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
  'browser.extract_web_table': [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'browser.extract_web_table_to_excel': [{ key: 'selector', type: 'string' }, { key: 'path', type: 'string' }, { key: 'sheet_name', type: 'string' }],
  'session.apply_auth_session': [{ key: 'cookies', type: 'json' }, { key: 'local_storage', type: 'object-map' }],
  'dialog.switch_dialog_mode': [{ key: 'mode', type: 'string' }],
  'dialog.watch_dialogs':      [{ key: 'timeout', type: 'number' }, { key: 'variable_name', type: 'string' }],
  'dialog.handle_dialogs':     [{ key: 'clear_after', type: 'boolean' }],
  'dialog.set_agent_config':   [{ key: 'default_action', type: 'string' }, { key: 'prompt_text', type: 'string' }],
  'graph.call_subgraph':       [{ key: 'subgraph_id', type: 'string' }, { key: 'inputs', type: 'object-map' }, { key: 'outputs', type: 'object-map' }],
  'flow.start':                [{ key: 'initial_variables', type: 'object-map' }],
  'control.parallel_fork':     [{ key: 'branches', type: 'branch-list' }],
  'control.join':              [{ key: 'branches', type: 'branch-list' }],
}

/** Known object-map field keys for detection */
export const OBJECT_MAP_KEYS = new Set(['initial_variables', 'variables', 'inputs', 'outputs', 'local_storage'])
