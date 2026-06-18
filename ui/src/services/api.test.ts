import { describe, it, expect } from 'vitest'
import { ApiError } from './api'

describe('ApiError', () => {
  it('prioritizes body.message over body.error', () => {
    const err = new ApiError(400, { message: 'primary message', error: 'fallback' })
    expect(err.message).toBe('primary message')
  })

  it('falls back to body.error when no message', () => {
    const err = new ApiError(500, { error: 'internal_server_error' })
    expect(err.message).toBe('internal_server_error')
  })

  it('falls back to HTTP status when neither present', () => {
    const err = new ApiError(404, {})
    expect(err.message).toBe('HTTP 404')
  })

  it('handles non-object body', () => {
    const err = new ApiError(502, 'Bad Gateway')
    expect(err.message).toBe('HTTP 502')
  })

  it('preserves status and body', () => {
    const body = { message: 'not found', path: '/api/unknown' }
    const err = new ApiError(404, body)
    expect(err.status).toBe(404)
    expect(err.body).toBe(body)
  })
})
