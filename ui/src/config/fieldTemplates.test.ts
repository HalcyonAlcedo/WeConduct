import { describe, expect, it } from 'vitest'
import { PARAM_TEMPLATES } from './fieldTemplates'

describe('fieldTemplates', () => {
  it('defines editable message and severity fields for message.emit', () => {
    expect(PARAM_TEMPLATES['message.emit']).toEqual([
      { key: 'message', type: 'string' },
      { key: 'severity', type: 'string', options: ['info', 'warning', 'error', 'fatal'] },
    ])
  })

  it('defines reconnect controls for network long connection nodes', () => {
    expect(PARAM_TEMPLATES['network.sse_connect']).toEqual(expect.arrayContaining([
      { key: 'max_reconnect_attempts', type: 'number' },
      { key: 'reconnect_delay_seconds', type: 'number' },
      { key: 'reconnect_max_delay_seconds', type: 'number' },
    ]))
    expect(PARAM_TEMPLATES['network.websocket_connect']).toEqual(expect.arrayContaining([
      { key: 'max_reconnect_attempts', type: 'number' },
      { key: 'reconnect_delay_seconds', type: 'number' },
      { key: 'reconnect_max_delay_seconds', type: 'number' },
    ]))
  })

  it('defines the formal GraphQL Subscription actions and reconnect controls', () => {
    expect(PARAM_TEMPLATES['network.graphql_subscription']).toEqual(expect.arrayContaining([
      { key: 'action', type: 'string', options: ['connect', 'next_event', 'receive', 'unsubscribe', 'cancel', 'close'] },
      { key: 'max_reconnect_attempts', type: 'number' },
      { key: 'reconnect_delay_seconds', type: 'number' },
      { key: 'reconnect_max_delay_seconds', type: 'number' },
    ]))
  })
})
