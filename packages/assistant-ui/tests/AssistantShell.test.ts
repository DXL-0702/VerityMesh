import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AssistantShell from '../src/AssistantShell.vue'

describe('AssistantShell', () => {
  it('preserves consumer content inside the package boundary', () => {
    const wrapper = mount(AssistantShell, {
      slots: {
        default: 'assistant content',
      },
    })

    expect(wrapper.get('[data-veritymesh-assistant-shell]').text()).toBe('assistant content')
  })
})
