import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import NodePlaintextRiskNotice from './NodePlaintextRiskNotice.vue'

describe('NodePlaintextRiskNotice', () => {
  it('持续提示节点配置中的明文敏感数据风险和安全替代入口', () => {
    const wrapper = mount(NodePlaintextRiskNotice)

    expect(wrapper.get('[role="alert"]').text()).toContain('节点配置会随项目保存')
    expect(wrapper.text()).toContain('待输入')
    expect(wrapper.text()).toContain('加密初始参数')
  })
})
