import { describe, expect, it } from 'vitest'

import { resolveApiUrl } from '../api'

describe('resolveApiUrl', () => {
  it('uses explicit VITE_API_URL first', () => {
    expect(resolveApiUrl({ VITE_API_URL: 'https://api.example.com', DEV: false })).toBe('https://api.example.com')
  })

  it('uses localhost during dev when no API URL is set', () => {
    expect(resolveApiUrl({ DEV: true })).toBe('http://127.0.0.1:8000')
  })

  it('uses same-origin requests in production when no API URL is set', () => {
    expect(resolveApiUrl({ DEV: false })).toBe('')
  })
})
