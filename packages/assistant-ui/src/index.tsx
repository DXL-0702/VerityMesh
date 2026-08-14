import { createRoot, type Root } from 'react-dom/client'

import { AssistantShell } from './AssistantShell'

export { AssistantShell }
export type { AssistantShellProps } from './AssistantShell'

export const ASSISTANT_SHELL_TAG_NAME = 'veritymesh-assistant-shell'

export class AssistantShellElement extends HTMLElement {
  private root: Root | null = null

  connectedCallback() {
    if (this.root) {
      return
    }

    const shadowRoot = this.shadowRoot ?? this.attachShadow({ mode: 'open' })
    const mountPoint = document.createElement('div')
    shadowRoot.replaceChildren(mountPoint)

    this.root = createRoot(mountPoint)
    this.root.render(
      <AssistantShell>
        <slot />
      </AssistantShell>,
    )
  }

  disconnectedCallback() {
    this.root?.unmount()
    this.root = null
    this.shadowRoot?.replaceChildren()
  }
}

export function defineAssistantShellElement() {
  if (typeof customElements === 'undefined') {
    return
  }

  if (!customElements.get(ASSISTANT_SHELL_TAG_NAME)) {
    customElements.define(ASSISTANT_SHELL_TAG_NAME, AssistantShellElement)
  }
}

defineAssistantShellElement()
