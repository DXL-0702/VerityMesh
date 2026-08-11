# assistant-ui

| 属性 | 内容 |
| --- | --- |
| 类型 | Vue 3 复用包与 Web Component |
| 发布形态 | 构建包，不是独立 Deployment |
| 当前状态 | Vue 包工程基线已初始化；正式聊天 UI 尚未实现 |

本目录负责消息状态、Citation、范围显示、项目切换、拒答、降级和 Embed 组件。品牌配置可以由项目覆盖，权限、协议和失败语义不能由宿主覆盖。

当前只导出用于验证包边界的 `AssistantShell` Slot，不代表消息状态机或 Web Component 已交付。具体交付范围见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)，工具版本见 [`非 Java 工作区工具链基线`](../../docs/implementation-designs/0003-non-java-workspace-toolchain-baseline.md)。
