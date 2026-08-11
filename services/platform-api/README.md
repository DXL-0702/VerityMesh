# platform-api

| 属性 | 内容 |
| --- | --- |
| 类型 | Java/Spring Boot 模块化单体 Deployment |
| 权威数据 | MySQL 业务与控制状态 |
| 当前状态 | 仅建立目录边界，Java 工程尚未初始化 |

本目录负责 `public-api`、`project-catalog`、`identity-access`、`session-thread`、`knowledge-control`、`release-control`、`audit-usage` 和 `outbox-projection` 模块。模块通过显式应用服务和领域事件协作，不通过共享表绕过所有权。

Flyway Migration 归本服务所有，但必须由独立预部署 Migration Job 执行。Java 构建工具、JDK 与 Spring Boot 版本在开工前工具版本检查关闭后固定。具体边界见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。
