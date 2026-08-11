# typescript-client

| 属性 | 内容 |
| --- | --- |
| 类型 | TypeScript 复用包 |
| 输入事实 | 版本化 OpenAPI 与 SSE 合同 |
| 当前状态 | TypeScript 包工程基线已初始化；API Client 尚未生成 |

本目录负责 OpenAPI Client、SSE Parser/State Machine，以及 Session、Thread、Message、Project Selection 和 Feedback API。当前入口保持空导出，不伪造尚未冻结的 API；生成代码不得手工修改，Java 侧工具链与跨语言生成方式确定后再固定生成配置。

跨语言合同统一位于 [`../../contracts/`](../../contracts/)，详细交付范围见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)，当前工具边界见 [`非 Java 工作区工具链基线`](../../docs/implementation-designs/0003-non-java-workspace-toolchain-baseline.md)。
