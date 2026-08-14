import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'

import { ASSISTANT_SHELL_TAG_NAME, AssistantShell, defineAssistantShellElement } from '../src/index'

describe('AssistantShell', () => {
  beforeAll(() => {
    ;(
      globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = true
    defineAssistantShellElement()
  })

  afterEach(() => {
    document.body.replaceChildren()
  })

  it('preserves consumer content inside the package boundary', () => {
    const container = document.createElement('div')
    document.body.append(container)
    const root: Root = createRoot(container)

    act(() => {
      root.render(<AssistantShell>assistant content</AssistantShell>)
    })

    expect(container.querySelector('[data-veritymesh-assistant-shell]')?.textContent).toBe(
      'assistant content',
    )

    root.unmount()
  })

  it('publishes the same React shell through the Web Component boundary', async () => {
    const element = document.createElement(ASSISTANT_SHELL_TAG_NAME)
    element.textContent = 'assistant content'

    await act(async () => {
      document.body.append(element)
    })

    const shell = element.shadowRoot?.querySelector('[data-veritymesh-assistant-shell]')
    const slot = shell?.querySelector('slot')

    expect(shell).not.toBeNull()
    expect(
      slot
        ?.assignedNodes()
        .map((node) => node.textContent)
        .join(''),
    ).toBe('assistant content')
  })
})
