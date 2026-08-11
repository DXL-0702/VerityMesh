# platform-api

| 属性 | 内容 |
| --- | --- |
| 类型 | Java/Spring Boot 模块化单体 Deployment |
| 权威数据 | MySQL 业务与控制状态 |
| 工具链 | Temurin Java 21、Maven Wrapper、Spring Boot 4.1 |
| 当前状态 | 工程与 CI 基线已初始化；业务模块尚未实现 |

本目录负责 `public-api`、`project-catalog`、`identity-access`、`session-thread`、`knowledge-control`、`release-control`、`audit-usage` 和 `outbox-projection` 模块。模块通过显式应用服务和领域事件协作，不通过共享表绕过所有权。

当前基线采用 Spring MVC 与 Embedded Tomcat 处理入站请求，WebClient 只用于调用 Python 服务和消费上游流；JWT 验证使用 Spring Security OAuth2 Resource Server 与 Nimbus。API 文档使用 SpringDoc，不引入 WebFlux Server、JJWT 或 Knife4j。

Flyway Migration 归本服务所有，但应用进程默认禁用 Flyway，只允许独立预部署 Migration Job 执行。当前还没有业务 API、Entity、Migration 或正式安全策略；这些从 `P1-00` 开始交付。完整技术栈见 [`技术栈与外部选型总览`](../../docs/technology-selection/technology-selection.md)，职责边界见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。

在仓库根目录验证本服务：

```sh
./tools/verify-java.sh
```
