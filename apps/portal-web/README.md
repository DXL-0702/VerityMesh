# portal-web

| 属性 | 内容 |
| --- | --- |
| 类型 | 独立 Web Deployment |
| 技术边界 | Vue 3 + TypeScript + Vite |
| 当前状态 | 仅建立目录边界，应用工程尚未初始化 |

本目录负责企业门户、项目知识页、知识治理与发布控制台，并复用 [`../../packages/assistant-ui/`](../../packages/assistant-ui/) 和 [`../../packages/typescript-client/`](../../packages/typescript-client/)。它不计算授权范围，也不允许客户端指定 Project Execution Context、Release、Access Segment 或模型。

具体交付范围见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。前端包管理器、Node 版本和工作区清单在开工前工具版本检查关闭后创建。
