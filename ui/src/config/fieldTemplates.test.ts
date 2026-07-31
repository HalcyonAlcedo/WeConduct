import { describe, expect, it } from 'vitest'
import { PARAM_TEMPLATES } from './fieldTemplates'

describe('fieldTemplates', () => {
  it('defines editable message and severity fields for message.emit', () => {
    expect(PARAM_TEMPLATES['message.emit']).toEqual([
      { key: 'message', type: 'string' },
      { key: 'severity', type: 'string', options: ['info', 'warning', 'error', 'fatal'] },
    ])
  })
})
