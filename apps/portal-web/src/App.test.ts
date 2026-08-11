import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App', () => {
  it('renders the VerityMesh product identity', () => {
    const wrapper = mount(App)

    expect(wrapper.get('.product-name').text()).toBe('VerityMesh')
    expect(wrapper.get('h1').text()).toBe('受治理的知识，可信的回答。')
  })
})
