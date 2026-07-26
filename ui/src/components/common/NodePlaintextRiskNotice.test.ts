import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import NodePlaintextRiskNotice from './NodePlaintextRiskNotice.vue'

describe('NodePlaintextRiskNotice', () => {
  it('只展示简短的加密参数建议', () => {
    const wrapper = mount(NodePlaintextRiskNotice)

    expect(wrapper.get('[role="alert"]').text()).toBe('敏感信息建议使用加密参数。')
  })
})
