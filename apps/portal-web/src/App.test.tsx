import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the VerityMesh product identity', () => {
    const container = document.createElement('div')
    document.body.append(container)
    const root: Root = createRoot(container)

    act(() => {
      root.render(<App />)
    })

    expect(container.querySelector('.product-name')?.textContent).toBe('VerityMesh')
    expect(container.querySelector('h1')?.textContent).toBe('受治理的知识，可信的回答。')

    root.unmount()
    container.remove()
  })
})
