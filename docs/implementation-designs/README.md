# 实施设计目录

本目录保存技术选型完成后的接入、实现与执行方案。正文不得重新决定外部依赖产品；产品选择及其状态统一引用 [`../technology-selection/technology-selection.md`](../technology-selection/technology-selection.md)。

## 三阶段实施概览

| 阶段 | 需要搭建的功能 |
| --- | --- |
| 第一阶段：知识与问答平台 | 搭建知识导入、治理、审批、发布、回滚和撤回；企业门户、项目知识页、统一聊天 UI、Web Component、TypeScript Client、统一身份与 Session；单项目混合 RAG、Citation、Grounding、Global Router 和跨项目问答 |
| 第二阶段：登录用户业务工具 | 搭建项目业务 API Connector、受限 ToolPlan 与 Tool Executor，为已登录用户提供经过对象授权、确认、幂等和审计的实时查询与低风险业务操作 |
| 第三阶段：GraphRAG | 搭建项目范围知识图谱、Local 多跳检索、异步主题归纳和跨项目分别查询后聚合的图检索能力 |

## 实施文档

| 状态 | 文档 | 说明 |
| --- | --- | --- |
| `ACCEPTED` | [`0001-phase-1-execution-plan.md`](0001-phase-1-execution-plan.md) | 第一阶段分层职责、交付批次和验收门禁基线 |
| `ACCEPTED` | [`0002-phase-1-seven-day-execution-route.md`](0002-phase-1-seven-day-execution-route.md) | 第一阶段七天并行执行路线、每日产物和完成条件；开工前检查尚未核验 |
