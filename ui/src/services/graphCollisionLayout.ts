export interface LayoutPoint {
  x: number
  y: number
}

export interface LayoutDimensions {
  width: number
  height: number
}

export interface LayoutNode {
  id: string
  position: LayoutPoint
  dimensions: LayoutDimensions
}

interface PlacedLayoutNode extends LayoutNode {
  position: LayoutPoint
}

function overlaps(a: LayoutNode, b: LayoutNode, gap: number): boolean {
  return a.position.x < b.position.x + b.dimensions.width + gap
    && a.position.x + a.dimensions.width + gap > b.position.x
    && a.position.y < b.position.y + b.dimensions.height + gap
    && a.position.y + a.dimensions.height + gap > b.position.y
}

/**
 * 将重叠节点局部向下推开。输入节点不会被修改，输出顺序与输入一致。
 * 排序规则固定，确保同一组节点无论输入顺序如何都得到相同布局。
 */
export function resolveNodeCollisions(nodes: LayoutNode[], gap = 16): LayoutNode[] {
  const normalizedGap = Number.isFinite(gap) && gap >= 0 ? gap : 16
  const ordered = nodes
    .map((item) => ({
      ...item,
      position: { ...item.position },
      dimensions: {
        width: Math.max(1, item.dimensions.width),
        height: Math.max(1, item.dimensions.height),
      },
    }))
    .sort((a, b) => (
      a.position.y - b.position.y
      || a.position.x - b.position.x
      || a.id.localeCompare(b.id)
    ))

  const placed: PlacedLayoutNode[] = []
  for (const item of ordered) {
    const current: PlacedLayoutNode = { ...item, position: { ...item.position } }
    let guard = 0
    while (placed.some(other => overlaps(current, other, normalizedGap)) && guard < nodes.length + 1) {
      const colliding = placed.filter(other => overlaps(current, other, normalizedGap))
      const nextY = Math.max(...colliding.map(other => other.position.y + other.dimensions.height + normalizedGap))
      current.position.y = Math.max(current.position.y, nextY)
      guard++
    }
    placed.push(current)
  }

  const byId = new Map(placed.map(item => [item.id, item]))
  return nodes.map(item => {
    const resolved = byId.get(item.id)
    return resolved
      ? { ...item, position: { ...resolved.position } }
      : { ...item, position: { ...item.position } }
  })
}
