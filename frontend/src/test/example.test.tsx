import { describe, it, expect } from 'vitest'

describe('Example Test', () => {
  it('should pass basic test', () => {
    expect(true).toBe(true)
  })
  
  it('should verify test framework is working', () => {
    const arr = [1, 2, 3]
    expect(arr).toContain(2)
  })
})
