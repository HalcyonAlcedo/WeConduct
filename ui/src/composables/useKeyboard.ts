/** WeConduct — Keyboard Shortcuts Composable
 *  Centralized keyboard shortcut management with conflict avoidance.
 */

import { onMounted, onUnmounted } from 'vue'

interface Shortcut {
  key: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  handler: (e: KeyboardEvent) => void
  /** If true, skips the shortcut when focus is in an input/textarea/contenteditable */
  ignoreInput?: boolean
}

const registered: Shortcut[] = []

/** Register a keyboard shortcut. Automatically cleaned up on component unmount. */
export function useKeyboard(shortcuts: Shortcut[]) {
  const localShortcuts = [...shortcuts]

  onMounted(() => {
    for (const s of localShortcuts) {
      registered.push(s)
    }
  })

  onUnmounted(() => {
    for (const s of localShortcuts) {
      const idx = registered.indexOf(s)
      if (idx >= 0) registered.splice(idx, 1)
    }
  })
}

// Global listener — registered once
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    for (const s of registered) {
      const ctrlOk = s.ctrl ? (e.ctrlKey || e.metaKey) : !e.ctrlKey && !e.metaKey
      const shiftOk = s.shift ? e.shiftKey : !e.shiftKey
      const altOk = s.alt ? e.altKey : !e.altKey
      const keyOk = e.key.toLowerCase() === s.key.toLowerCase()

      if (ctrlOk && shiftOk && altOk && keyOk) {
        if (s.ignoreInput && isEditingTarget(e.target as HTMLElement)) {
          return // Don't intercept when user is typing
        }
        e.preventDefault()
        e.stopPropagation()
        s.handler(e)
        return
      }
    }
  })
}

function isEditingTarget(el: HTMLElement | null): boolean {
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}
