const NETWORK_NODE_KINDS = new Set([
  'network.http_request',
  'network.graphql_request',
  'network.sse_connect',
  'network.websocket_connect',
])

const SENSITIVE_HEADER_NAMES = new Set([
  'authorization',
  'cookie',
  'proxy-authorization',
  'x-api-key',
  'x-auth-token',
])

const SENSITIVE_FIELD_PATHS = new Set([
  'auth.token',
  'auth.password',
  'auth.client_secret',
  'auth.refresh_token',
  'proxy.username',
  'proxy.password',
  'tls.client_key',
  'tls.client_key_password',
])

export function isSensitiveNodeConfigurationField(
  nodeKind: string,
  fieldPath: string,
  value: unknown,
): boolean {
  if (!NETWORK_NODE_KINDS.has(nodeKind)) return false

  const normalizedPath = fieldPath.trim().toLowerCase()
  if (SENSITIVE_FIELD_PATHS.has(normalizedPath)) return true

  if (normalizedPath.startsWith('headers.')) {
    return SENSITIVE_HEADER_NAMES.has(normalizedPath.slice('headers.'.length))
  }

  return (
    normalizedPath === 'proxy.url'
    && typeof value === 'string'
    && /:\/\/[^/\s@]+@/.test(value)
  )
}
