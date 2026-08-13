# platform-api

| 属性 | 内容 |
| --- | --- |
| 类型 | Java/Spring Boot 模块化单体 Deployment |
| 权威数据 | MySQL 业务与控制状态 |
| 工具链 | Temurin Java 21、Maven Wrapper、Spring Boot 4.1 |
| 当前状态 | P1-00/P1-01 最小知识接入基座、本地 MySQL/Flyway Migration Job 与 S3-compatible Source Storage Adapter 已实现；真实 MySQL 业务连接、Kafka 和 Outbox Publisher 仍待集成 |

本目录负责 `public-api`、`project-catalog`、`identity-access`、`session-thread`、`knowledge-control`、`release-control`、`audit-usage` 和 `outbox-projection` 模块。模块通过显式应用服务和领域事件协作，不通过共享表绕过所有权。

当前基线采用 Spring MVC 与 Embedded Tomcat 处理入站请求，WebClient 只用于调用 Python 服务和消费上游流；JWT 验证使用 Spring Security OAuth2 Resource Server 与 Nimbus。API 文档使用 SpringDoc，不引入 WebFlux Server、JJWT 或 Knife4j。

Flyway Migration 归本服务所有，但应用进程默认禁用 Flyway，只允许独立预部署 Migration Job 执行。本地 Job 位于 [`infra/local/compose.yaml`](../../infra/local/compose.yaml)，直接使用本目录的迁移源；应用身份与迁移身份分离。当前已建立 Project/SourceObject/SourceRevision/ProcessingTask/Outbox 的 MySQL V1 基线、上传预约/完成入口和幂等校验；`S3SourceStorage` 通过 AWS SDK for Java v2 的 S3-compatible API 生成短期预签名 PUT URL，并在完成确认时 HEAD + 流式 GET 计算 SHA-256，`UnavailableSourceStorage` 仍在未启用配置时 fail closed。本地 MinIO bucket 与最小对象身份由 [`object-storage-init`](../../infra/local/compose.yaml) 独立 Job 创建。真实 MySQL 业务连接、Kafka Outbox Publisher、身份授权和业务模块仍待后续批次实现。完整技术栈见 [`技术栈与外部选型总览`](../../docs/technology-selection/technology-selection.md)，职责边界见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。

在仓库根目录验证本服务：

```sh
./tools/verify-java.sh
```

本地只做编译/测试时如果默认 Maven 用户目录不可写，可将 `MAVEN_USER_HOME` 和 `-Dmaven.repo.local` 指向临时目录；这不会改变仓库锁定版本。Flyway SQL 的离线审计由仓库验证入口负责，真实数据库执行需要独立 Migration Job 和已授权数据库。
