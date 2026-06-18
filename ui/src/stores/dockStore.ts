/** WeConduct — Dock Layout Store
 *  Manages dock zones (left/right/bottom/center), panel placement,
 *  split sizes, drag-and-drop docking, and tab groups within zones.
 */

import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'

export type DockZone = 'left' | 'right' | 'bottom' | 'center'

export interface DockPanel {
  id: string
  title: string
}

export interface ZoneState {
  panels: DockPanel[]
  activePanelId: string | null
}

export const useDockStore = defineStore('dock', () => {
  // Zone states — each zone is a tab group
  const zones = reactive<Record<DockZone, ZoneState>>({
    left:    { panels: [], activePanelId: null },
    right:   { panels: [], activePanelId: null },
    bottom:  { panels: [], activePanelId: null },
    center:  { panels: [], activePanelId: null },
  })

  // Split sizes (percentage of available space)
  const leftWidth = ref(18)   // % of total width
  const rightWidth = ref(18)
  const bottomHeight = ref(25) // % of total height

  // Drag state
  const draggingPanelId = ref<string | null>(null)
  const dropZone = ref<DockZone | null>(null)

  // All panels registered
  const allPanels = ref<DockPanel[]>([])

  function register(panel: DockPanel) {
    if (!allPanels.value.find(p => p.id === panel.id)) {
      allPanels.value.push(panel)
    }
  }

  function addToZone(panelId: string, zone: DockZone) {
    const panel = allPanels.value.find(p => p.id === panelId)
    if (!panel) return
    // Remove from all zones first
    for (const z of Object.values(zones)) {
      z.panels = z.panels.filter(p => p.id !== panelId)
    }
    const wasEmpty = zones[zone].panels.length === 0
    zones[zone].panels.push(panel)
    zones[zone].activePanelId = panelId

    // Auto-create zone with default size if it was empty
    if (wasEmpty) {
      if (zone === 'left' && leftWidth.value < 10) setLeftWidth(18)
      if (zone === 'right' && rightWidth.value < 10) setRightWidth(18)
      if (zone === 'bottom' && bottomHeight.value < 10) setBottomHeight(25)
    }
  }

  function removeFromZone(panelId: string) {
    for (const z of Object.values(zones)) {
      z.panels = z.panels.filter(p => p.id !== panelId)
      if (z.activePanelId === panelId) {
        z.activePanelId = z.panels[0]?.id ?? null
      }
    }
  }

  function activatePanel(panelId: string) {
    for (const zone of Object.values(zones)) {
      if (zone.panels.find(p => p.id === panelId)) {
        zone.activePanelId = panelId
        return
      }
    }
  }

  function isPanelVisible(panelId: string): boolean {
    return Object.values(zones).some(z => z.panels.some(p => p.id === panelId))
  }

  function findPanelZone(panelId: string): DockZone | null {
    for (const [key, z] of Object.entries(zones)) {
      if (z.panels.find(p => p.id === panelId)) return key as DockZone
    }
    return null
  }

  function movePanel(panelId: string, toZone: DockZone) {
    addToZone(panelId, toZone)
  }

  // Drag operations
  function startDrag(panelId: string) { draggingPanelId.value = panelId }
  function endDrag() { draggingPanelId.value = null; dropZone.value = null }
  function setDropZone(zone: DockZone | null) { dropZone.value = zone }

  function dropOnZone(zone: DockZone) {
    if (draggingPanelId.value) {
      movePanel(draggingPanelId.value, zone)
    }
    endDrag()
  }

  function closePanel(panelId: string) {
    removeFromZone(panelId)
  }

  function restorePanel(panelId: string, zone: DockZone = 'center') {
    if (!isPanelVisible(panelId)) {
      addToZone(panelId, zone)
    }
  }

  const visiblePanels = computed(() => {
    const ids = new Set<string>()
    for (const z of Object.values(zones)) {
      for (const p of z.panels) ids.add(p.id)
    }
    return [...ids]
  })

  // Resize
  function setLeftWidth(v: number) { leftWidth.value = Math.max(8, Math.min(35, v)) }
  function setRightWidth(v: number) { rightWidth.value = Math.max(8, Math.min(35, v)) }
  function setBottomHeight(v: number) { bottomHeight.value = Math.max(10, Math.min(50, v)) }

  return {
    zones, leftWidth, rightWidth, bottomHeight,
    draggingPanelId, dropZone, allPanels,
    register, addToZone, removeFromZone, activatePanel,
    isPanelVisible, findPanelZone, movePanel,
    startDrag, endDrag, setDropZone, dropOnZone,
    closePanel, restorePanel, visiblePanels,
    setLeftWidth, setRightWidth, setBottomHeight,
  }
})
