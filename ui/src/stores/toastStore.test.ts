import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useToastStore } from './toastStore'

describe('toastStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts with no toasts', () => {
    const store = useToastStore()
    expect(store.toasts).toHaveLength(0)
  })

  it('adds a success toast', () => {
    const store = useToastStore()
    store.success('Done')
    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0].type).toBe('success')
    expect(store.toasts[0].title).toBe('Done')
  })

  it('adds an error toast with message', () => {
    const store = useToastStore()
    store.error('Failed', 'Something went wrong')
    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0].type).toBe('error')
    expect(store.toasts[0].message).toBe('Something went wrong')
  })

  it('removes a toast by id', () => {
    const store = useToastStore()
    store.info('Info')
    const id = store.toasts[0].id
    store.remove(id)
    expect(store.toasts).toHaveLength(0)
  })

  it('assigns unique ids', () => {
    const store = useToastStore()
    store.success('A')
    store.error('B')
    expect(store.toasts[0].id).not.toBe(store.toasts[1].id)
  })
})
