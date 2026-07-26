import { describe, expect, it } from 'vitest'

import { isSensitiveNodeConfigurationField } from './nodeSensitiveConfiguration'

describe('isSensitiveNodeConfigurationField', () => {
  it('只标记网络节点中的认证、代理和 TLS 私钥字段', () => {
    expect(isSensitiveNodeConfigurationField('control.jump_to_step', 'auth.token', 'secret')).toBe(false)
    expect(isSensitiveNodeConfigurationField('network.http_request', 'auth.token', 'secret')).toBe(true)
    expect(isSensitiveNodeConfigurationField('network.http_request', 'auth.type', 'bearer')).toBe(false)
    expect(isSensitiveNodeConfigurationField('network.http_request', 'proxy.password', 'secret')).toBe(true)
    expect(isSensitiveNodeConfigurationField('network.http_request', 'tls.client_key', 'key')).toBe(true)
    expect(isSensitiveNodeConfigurationField('network.http_request', 'headers.Authorization', 'Bearer secret')).toBe(true)
    expect(isSensitiveNodeConfigurationField('network.http_request', 'headers.X-Trace-Id', 'trace')).toBe(false)
  })
})
