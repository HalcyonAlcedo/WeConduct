<script setup lang="ts">
/** Dock Layout: left/center/right/bottom zones — always rendered.
 *  Empty zones act as thin drop targets. Zones auto-create on first panel drop. */
import { ref, computed } from 'vue'
import { useDockStore } from '@/stores/dockStore'
import type { DockZone } from '@/stores/dockStore'

const dock = useDockStore()

const resizing = ref<'left' | 'right' | 'bottom' | null>(null)

const leftHas = computed(() => dock.zones.left.panels.length > 0)
const rightHas = computed(() => dock.zones.right.panels.length > 0)
const bottomHas = computed(() => dock.zones.bottom.panels.length > 0)

function startResize(edge: 'left' | 'right' | 'bottom', e: MouseEvent) {
  resizing.value = edge; e.preventDefault()
  const startX = e.clientX; const startY = e.clientY
  const startLW = dock.leftWidth; const startRW = dock.rightWidth; const startBH = dock.bottomHeight
  const container = (e.target as HTMLElement).parentElement!

  function onMove(ev: MouseEvent) {
    if (edge === 'left') {
      dock.setLeftWidth(startLW + ((ev.clientX - startX) / container.getBoundingClientRect().width) * 100)
    } else if (edge === 'right') {
      dock.setRightWidth(startRW + ((startX - ev.clientX) / container.getBoundingClientRect().width) * 100)
    } else {
      dock.setBottomHeight(startBH + ((startY - ev.clientY) / container.getBoundingClientRect().height) * 100)
    }
  }
  function onUp() {
    resizing.value = null
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function onDragOverZone(zone: DockZone, e: DragEvent) { e.preventDefault(); dock.setDropZone(zone) }
function onDragLeaveZone() { dock.setDropZone(null) }
function onDropOnZone(zone: DockZone) { dock.dropOnZone(zone) }
function onPanelDragStart(panelId: string) { dock.startDrag(panelId) }
function onPanelDragEnd() { dock.endDrag() }

const maximizedPanel = ref<string | null>(null)
function toggleMaximize(panelId: string) {
  maximizedPanel.value = maximizedPanel.value === panelId ? null : panelId
}

</script>

<template>
  <!-- Maximized: single panel fills the workbench -->
  <div v-if="maximizedPanel" class="dl-root dl-maximized">
    <div class="dl-maximized-bar">
      <span class="dl-maximized-title">{{ dock.allPanels.find(p => p.id === maximizedPanel)?.title ?? '' }}</span>
      <span class="dl-tab-actions" style="margin-left:auto">
        <button class="dl-tab-btn" title="还原" @click="maximizedPanel = null">❐</button>
        <button class="dl-tab-btn" title="关闭" @click="dock.closePanel(maximizedPanel!); maximizedPanel = null">✕</button>
      </span>
    </div>
    <div class="dl-maximized-body">
      <slot :name="maximizedPanel" :zone="'center'" />
    </div>
  </div>

  <!-- Normal layout -->
  <div v-else class="dl-root" :class="{ 'dl-resizing': !!resizing }">
    <div class="dl-top-row">
      <!-- Left Zone — always rendered -->
      <div
        class="dl-zone dl-zone-side"
        :class="{
          'dl-zone-empty': !leftHas,
          'dl-zone-left': leftHas,
          'dl-drop-target': dock.dropZone === 'left'
        }"
        :style="leftHas ? { width: dock.leftWidth + '%' } : {}"
        @dragover="onDragOverZone('left', $event)"
        @dragleave="onDragLeaveZone"
        @drop="onDropOnZone('left')"
      >
        <template v-if="leftHas">
          <div class="dl-zone-tabs">
            <button v-for="p in dock.zones.left.panels" :key="p.id"
              :class="['dl-tab', { active: dock.zones.left.activePanelId === p.id }]"
              draggable="true" @click="dock.activatePanel(p.id)"
              @dragstart="onPanelDragStart(p.id)" @dragend="onPanelDragEnd"
            >{{ p.title }}</button>
            <span class="dl-tab-actions">
              <button class="dl-tab-btn" title="最大化" @click="toggleMaximize(dock.zones.left.activePanelId!)">□</button>
              <button class="dl-tab-btn" title="关闭" @click="dock.closePanel(dock.zones.left.activePanelId!)">✕</button>
            </span>
          </div>
          <div class="dl-zone-body">
            <slot :name="dock.zones.left.activePanelId ?? ''" :zone="'left'" />
          </div>
        </template>
      </div>

      <!-- Left Splitter -->
      <div v-if="leftHas" class="dl-splitter dl-splitter-v" @mousedown="startResize('left', $event)"></div>

      <!-- Center Zone -->
      <div
        class="dl-zone dl-zone-center"
        :class="{ 'dl-drop-target': dock.dropZone === 'center' }"
        @dragover="onDragOverZone('center', $event)"
        @dragleave="onDragLeaveZone"
        @drop="onDropOnZone('center')"
      >
        <div class="dl-zone-tabs" v-if="dock.zones.center.panels.length > 0">
          <button v-for="p in dock.zones.center.panels" :key="p.id"
            :class="['dl-tab', { active: dock.zones.center.activePanelId === p.id }]"
            draggable="true" @click="dock.activatePanel(p.id)"
            @dragstart="onPanelDragStart(p.id)" @dragend="onPanelDragEnd"
          >{{ p.title }}</button>
          <span class="dl-tab-actions">
            <button class="dl-tab-btn" title="最大化" @click="toggleMaximize(dock.zones.center.activePanelId!)">□</button>
            <button class="dl-tab-btn" title="关闭" @click="dock.closePanel(dock.zones.center.activePanelId!)">✕</button>
          </span>
        </div>
        <div class="dl-zone-body">
          <slot :name="dock.zones.center.activePanelId ?? ''" :zone="'center'" />
          <div v-if="dock.zones.center.panels.length === 0 && dock.visiblePanels.length > 0" class="dl-hint">
            拖拽面板到此处或从「视图」菜单添加
          </div>
        </div>
      </div>

      <!-- Right Splitter -->
      <div v-if="rightHas" class="dl-splitter dl-splitter-v" @mousedown="startResize('right', $event)"></div>

      <!-- Right Zone — always rendered -->
      <div
        class="dl-zone dl-zone-side"
        :class="{
          'dl-zone-empty': !rightHas,
          'dl-zone-right': rightHas,
          'dl-drop-target': dock.dropZone === 'right'
        }"
        :style="rightHas ? { width: dock.rightWidth + '%' } : {}"
        @dragover="onDragOverZone('right', $event)"
        @dragleave="onDragLeaveZone"
        @drop="onDropOnZone('right')"
      >
        <template v-if="rightHas">
          <div class="dl-zone-tabs">
            <button v-for="p in dock.zones.right.panels" :key="p.id"
              :class="['dl-tab', { active: dock.zones.right.activePanelId === p.id }]"
              draggable="true" @click="dock.activatePanel(p.id)"
              @dragstart="onPanelDragStart(p.id)" @dragend="onPanelDragEnd"
            >{{ p.title }}</button>
            <span class="dl-tab-actions">
              <button class="dl-tab-btn" title="最大化" @click="toggleMaximize(dock.zones.right.activePanelId!)">□</button>
              <button class="dl-tab-btn" title="关闭" @click="dock.closePanel(dock.zones.right.activePanelId!)">✕</button>
            </span>
          </div>
          <div class="dl-zone-body">
            <slot :name="dock.zones.right.activePanelId ?? ''" :zone="'right'" />
          </div>
        </template>
      </div>
    </div>

    <!-- Bottom Splitter -->
    <div v-if="bottomHas" class="dl-splitter dl-splitter-h" @mousedown="startResize('bottom', $event)"></div>

    <!-- Bottom Zone — always rendered -->
    <div
      class="dl-zone dl-zone-bottom-wrap"
      :class="{
        'dl-zone-empty': !bottomHas,
        'dl-zone-bottom': bottomHas,
        'dl-drop-target': dock.dropZone === 'bottom'
      }"
      :style="bottomHas ? { height: dock.bottomHeight + '%' } : {}"
      @dragover="onDragOverZone('bottom', $event)"
      @dragleave="onDragLeaveZone"
      @drop="onDropOnZone('bottom')"
    >
      <template v-if="bottomHas">
        <div class="dl-zone-tabs">
          <button v-for="p in dock.zones.bottom.panels" :key="p.id"
            :class="['dl-tab', { active: dock.zones.bottom.activePanelId === p.id }]"
            draggable="true" @click="dock.activatePanel(p.id)"
            @dragstart="onPanelDragStart(p.id)" @dragend="onPanelDragEnd"
          >{{ p.title }}</button>
          <span class="dl-tab-actions">
            <button class="dl-tab-btn" title="最大化" @click="toggleMaximize(dock.zones.bottom.activePanelId!)">□</button>
            <button class="dl-tab-btn" title="关闭" @click="dock.closePanel(dock.zones.bottom.activePanelId!)">✕</button>
          </span>
        </div>
        <div class="dl-zone-body">
          <slot :name="dock.zones.bottom.activePanelId ?? ''" :zone="'bottom'" />
        </div>
      </template>
    </div>

    <div v-if="dock.visiblePanels.length === 0" class="dl-empty">
      所有面板已关闭 · 通过「视图」菜单重新打开
    </div>

  </div>
</template>

<style scoped>
.dl-root { display: flex; flex-direction: column; height: 100%; overflow: hidden; background: var(--bg-app); }
.dl-root.dl-resizing { cursor: col-resize; user-select: none; }
.dl-top-row { display: flex; flex: 1; overflow: hidden; min-height: 0; }

.dl-zone {
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--bg-panel); border: 1px solid var(--border-subtle);
}
.dl-zone-side { min-width: 160px; }
.dl-zone-empty {
  min-width: 20px; width: 20px; border: 1px dashed var(--border-default);
  background: var(--bg-panel-header); flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  cursor: default;
}
.dl-zone-empty.dl-drop-target {
  border-color: var(--accent); background: var(--accent-light);
  min-width: 80px;
}
.dl-zone-center { flex: 1; min-width: 200px; border-left: none; border-right: none; }
.dl-zone-bottom-wrap { min-height: 20px; }
.dl-zone-bottom-wrap.dl-zone-empty {
  height: 20px; min-height: 20px; border: 1px dashed var(--border-default);
  background: var(--bg-panel-header); flex-shrink: 0;
}
.dl-zone-bottom-wrap.dl-zone-empty.dl-drop-target {
  border-color: var(--accent); background: var(--accent-light); min-height: 80px;
}

.dl-drop-target { outline: 2px dashed var(--accent); outline-offset: -2px; }

.dl-zone-tabs {
  display: flex; background: var(--bg-panel-header); border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0; overflow-x: auto;
}
.dl-tab {
  padding: 3px 12px; border: none; background: transparent;
  color: var(--text-secondary); font-size: var(--text-small); font-family: var(--font-ui);
  cursor: grab; white-space: nowrap; border-bottom: 2px solid transparent;
}
.dl-tab:active { cursor: grabbing; }
.dl-tab:hover { color: var(--text-primary); background: var(--bg-hover); }
.dl-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

.dl-zone-body { flex: 1; overflow: hidden; }

.dl-tab-actions { margin-left: auto; display: flex; align-items: center; gap: 1px; padding-right: 4px; }
.dl-tab-btn {
  width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
  border: none; background: transparent; color: var(--text-disabled); cursor: pointer;
  border-radius: var(--radius-sm); font-size: 11px; font-family: var(--font-ui);
}
.dl-tab-btn:hover { color: var(--text-primary); background: var(--bg-hover); }

.dl-maximized { flex-direction: column; }
.dl-maximized-bar {
  display: flex; align-items: center; padding: 4px 12px;
  background: var(--bg-panel-header); border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0; height: 30px;
}
.dl-maximized-title { font-size: var(--text-body); font-weight: 600; color: var(--text-primary); }
.dl-maximized-body { flex: 1; overflow: hidden; }

.dl-hint {
  display: flex; align-items: center; justify-content: center; height: 100%;
  font-size: var(--text-small); color: var(--text-disabled);
}

.dl-splitter { flex-shrink: 0; background: var(--border-subtle); transition: background 100ms; }
.dl-splitter:hover { background: var(--accent); }
.dl-splitter-v { width: 4px; cursor: col-resize; }
.dl-splitter-h { height: 4px; cursor: row-resize; }

.dl-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  font-size: var(--text-body); color: var(--text-disabled);
}
</style>
