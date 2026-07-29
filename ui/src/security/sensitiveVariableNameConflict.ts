const CONFLICT_PREFIX = 'sensitive_parameter.initial_variable_name_conflict:'

export function describeSensitiveVariableNameConflict(error: unknown): string | null {
  const message = error instanceof Error ? error.message : ''
  if (!message.startsWith(CONFLICT_PREFIX)) return null
  const parameterNames = message.slice(CONFLICT_PREFIX.length).trim()
  if (!parameterNames) return '初始变量与加密参数同名，请修改其中一项后再保存。'
  return `初始变量“${parameterNames.split(',').map(name => name.trim()).filter(Boolean).join('、')}”与加密参数同名，请修改其中一项后再保存。`
}
