import type { ReactNode } from 'react'

export interface AssistantShellProps {
  children?: ReactNode
}

export function AssistantShell({ children }: AssistantShellProps) {
  return (
    <section className="veritymesh-assistant-shell" data-veritymesh-assistant-shell>
      {children}
    </section>
  )
}
