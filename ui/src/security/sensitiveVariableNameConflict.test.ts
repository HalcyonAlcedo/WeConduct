import { describe, expect, it } from 'vitest'

import { describeSensitiveVariableNameConflict } from './sensitiveVariableNameConflict'

describe('describeSensitiveVariableNameConflict', () => {
  it('将服务端同名冲突错误转换为可操作提示', () => {
    expect(describeSensitiveVariableNameConflict(
      new Error('sensitive_parameter.initial_variable_name_conflict: token, username'),
    )).toBe('初始变量“token、username”与加密参数同名，请修改其中一项后再保存。')
  })

  it('不处理无关错误', () => {
    expect(describeSensitiveVariableNameConflict(new Error('HTTP 400'))).toBeNull()
  })
})
