# typescript-client

| 属性 | 内容 |
| --- | --- |
| 类型 | TypeScript 复用包 |
| 输入事实 | 版本化 OpenAPI 与 SSE 合同 |
| 当前状态 | 仅建立目录边界，包工程尚未初始化 |

本目录负责 OpenAPI Client、SSE Parser/State Machine，以及 Session、Thread、Message、Project Selection 和 Feedback API。生成代码不得手工修改，生成方式和前端包管理器在开工前工具版本检查关闭后固定。

跨语言合同统一位于 [`../../contracts/`](../../contracts/)，详细交付范围见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。
