# portal-web

| 属性 | 内容 |
| --- | --- |
| 类型 | 独立 Web Deployment |
| 技术边界 | Vue 3 + TypeScript + Vite |
| 当前状态 | Node/pnpm 工程基线已初始化；门户业务功能尚未实现 |

本目录负责企业门户、项目知识页、知识治理与发布控制台，并复用 [`../../packages/assistant-ui/`](../../packages/assistant-ui/) 和 [`../../packages/typescript-client/`](../../packages/typescript-client/)。它不计算授权范围，也不允许客户端指定 Project Execution Context、Release、Access Segment 或模型。

具体交付范围见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。当前只提供可构建入口和框架烟雾测试，版本与验证方式见 [`非 Java 工作区工具链基线`](../../docs/implementation-designs/0003-non-java-workspace-toolchain-baseline.md)；项目列表、知识空间、上传和任务状态仍在 Day 1 实现。
