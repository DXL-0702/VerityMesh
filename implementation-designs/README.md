# 实施设计目录

本目录用于保存已经完成技术选型后的具体接入与实现方案。

正文可包含组件职责、接口、Schema、状态机、数据流、失败语义、迁移步骤、容量设计和交付拆分；不得在本目录重新决定外部依赖产品。产品选择及其状态统一引用 [`../technology-selection/technology-selection.md`](../technology-selection/technology-selection.md)。

## 当前草案

| 状态 | 文档 | 说明 |
| --- | --- | --- |
| `DRAFT` | [`0001-phase-1-execution-plan.md`](0001-phase-1-execution-plan.md) | 将第一阶段 `1A + 1B + 1C` 按前端、Java 后端、在线 AI、知识批处理、数据基础设施和验收门禁拆分，供审阅 |

草案可以声明外部选型的关闭时点，但不能改变选型状态。方案获批且相应依赖完成选型或进入 PoC 后，再按交付批次编写更细的接口、Schema、状态机和运行设计。
