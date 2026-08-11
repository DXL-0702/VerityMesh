# typescript-client

| 属性 | 内容 |
| --- | --- |
| 类型 | TypeScript 复用包 |
| 输入事实 | 版本化 OpenAPI 与 SSE 合同 |
| 当前状态 | TypeScript 包工程基线已初始化；API Client 尚未生成 |

本目录负责 OpenAPI Client、SSE Parser/State Machine，以及 Session、Thread、Message、Project Selection 和 Feedback API。当前入口保持空导出，不伪造尚未冻结的 API；生成代码不得手工修改，跨语言生成方式由 `P1-00` 使用第一版正式 Schema 验证后固定。

跨语言合同统一位于 [`../../contracts/`](../../contracts/)，详细交付范围见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)，版本总览见 [`技术栈与外部选型总览`](../../docs/technology-selection/technology-selection.md)。
