import { describe, expect, it } from 'vitest'
import { resolveNodeCollisions, type LayoutNode } from './graphCollisionLayout'

function node(id: string, x: number, y: number, width: number, height: number): LayoutNode {
  return { id, position: { x, y }, dimensions: { width, height } }
}

describe('resolveNodeCollisions', () => {
  it('uses measured dynamic dimensions instead of a fixed node height', () => {
    const nodes = [
      node('tall', 0, 0, 180, 140),
      node('short', 0, 60, 180, 40),
    ]

    const result = resolveNodeCollisions(nodes, 16)

    expect(result.find(item => item.id === 'tall')?.position).toEqual({ x: 0, y: 0 })
    expect(result.find(item => item.id === 'short')?.position.y).toBe(156)
  })

  it('pushes a chain of overlapping nodes until every rectangle is clear', () => {
    const nodes = [
      node('a', 0, 0, 100, 50),
      node('b', 0, 20, 100, 50),
      node('c', 0, 40, 100, 50),
    ]

    const result = resolveNodeCollisions(nodes, 10)

    expect(result.map(item => item.position.y)).toEqual([0, 60, 120])
  })

  it('preserves positions when measured rectangles do not overlap', () => {
    const nodes = [
      node('a', 0, 0, 100, 50),
      node('b', 120, 0, 100, 50),
    ]

    expect(resolveNodeCollisions(nodes, 10)).toEqual(nodes)
  })

  it('returns the same result regardless of input order', () => {
    const nodes = [
      node('b', 0, 20, 100, 50),
      node('a', 0, 0, 100, 50),
    ]

    const result = resolveNodeCollisions(nodes, 10)

    expect(result).toEqual([
      node('b', 0, 60, 100, 50),
      node('a', 0, 0, 100, 50),
    ])
  })
})
