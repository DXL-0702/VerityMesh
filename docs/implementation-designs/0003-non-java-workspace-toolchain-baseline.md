# 非 Java 工作区工具链基线

| 属性 | 内容 |
| --- | --- |
| 状态 | `ACCEPTED` |
| 决策范围 | Node/pnpm 前端工作区、Python/uv 工作区、跨语言合同格式和对应 CI |
| 明确排除 | Java 构建工具、JDK、Spring Boot/Flyway 具体版本、Java Schema 生成器和 Java CI |
| 项目执行影响 | 只关闭非 Java 工具链的仓库初始化，不表示开工前检查全部通过，也不启动七天倒计时 |
| 关联执行路线 | [`0002-phase-1-seven-day-execution-route.md`](0002-phase-1-seven-day-execution-route.md) |
| 最后更新 | 2026-08-11 |

本文固定可独立于 Java 工具链建立的工作区基线，使前端和 Python 目录能够在干净 Checkout 中安装、静态检查、测试和构建。它不创建第一阶段业务合同、正式服务入口、数据库 Migration 或用户功能；这些仍从 `P1-00` 开始交付。

## 1. Node 与前端工作区

| 项目 | 固定版本或形态 | 仓库事实源 |
| --- | --- | --- |
| Node | `24.19.0` | [`.node-version`](../../.node-version) 与根 `package.json` Engine |
| pnpm | `10.33.0` | 根 `package.json` 的 `packageManager` 与 Engine |
| Vue | `3.5.41` | `pnpm-workspace.yaml` Catalog |
| TypeScript | `5.9.3` | `pnpm-workspace.yaml` Catalog |
| Vite | `7.3.6` | `pnpm-workspace.yaml` Catalog |
| Vitest | `4.1.10` | `pnpm-workspace.yaml` Catalog |
| Playwright | `1.62.1` | `pnpm-workspace.yaml` Catalog；浏览器与 E2E 夹具留到 `P1-00` |
| ESLint / Prettier | `9.39.5` / `3.9.6` | `pnpm-workspace.yaml` Catalog |
| 工作区 | 单一 pnpm Workspace，成员为 `apps/*` 与 `packages/*` | `pnpm-workspace.yaml` 与 `pnpm-lock.yaml` |

选择 Node 24 和 pnpm 10 是为了使用成熟的 LTS/主版本组合，不把当前机器上的 Node 25 或刚进入新主版本周期的包管理器隐式变成项目基线。第一阶段不引入 Nx、Turborepo 或 Bazel；当前三个前端成员不需要额外任务编排层。

`portal-web` 只提供可构建的 Vue 入口和框架烟雾测试；`assistant-ui` 只提供最小 Slot Shell；`typescript-client` 保持空导出，直到 `contracts/` 中出现已审核的 OpenAPI/SSE 合同。空导出不能被解释为正式 Client 已交付。

## 2. Python 与 uv 工作区

| 项目 | 固定版本或形态 | 仓库事实源 |
| --- | --- | --- |
| Python | `3.12.13`，解释器范围限定为 `3.12.x` | [`.python-version`](../../.python-version) 与根 `pyproject.toml` |
| uv | `0.11.13` | 根 `pyproject.toml` 的 `required-version` |
| Workspace | 单一 uv Workspace | 根 `pyproject.toml` 与 `uv.lock` |
| 在线 AI 包 | `services/assistant-runtime`，FastAPI/Pydantic/Uvicorn 依赖边界 | 成员 `pyproject.toml` |
| 批处理包 | `services/batch-worker`，Celery/Redis/Alembic/SQLAlchemy/psycopg/pgvector 依赖边界 | 成员 `pyproject.toml` |
| Python 检查 | Ruff、mypy strict、pytest/coverage | 根 `pyproject.toml` 与 `tools/verify-python.sh` |

两个成员当前只建立可安装、可导入、可静态检查的包边界。没有创建 FastAPI 正式路由、Celery Task、Kafka Dispatcher、Alembic Revision 或 Vector Schema；存在依赖和锁文件只证明工程基座可复现，不证明对应 `P1-00` 或生产门禁已经完成。

直接 Python 依赖按当前锁定基线固定如下：

| 范围 | 直接依赖版本 |
| --- | --- |
| Workspace 检查 | Ruff `0.15.21`、mypy `1.20.2`、pytest `9.1.1`、pytest-cov `7.1.0` |
| 构建后端 | Hatchling `1.31.0` |
| `assistant-runtime` | FastAPI `0.139.0`、Pydantic `2.13.4`、Uvicorn `0.51.0` |
| `batch-worker` | Celery `5.6.3`、Redis Client `7.4.1`、Alembic `1.18.5`、SQLAlchemy `2.0.51`、psycopg `3.3.4`、pgvector Python Client `0.5.0` |

Python 直接依赖以 2026-07-11 为发布时间上限解析，避免把冻结当日刚发布的版本直接升为工程基线。这里的 `pgvector` 是 Python 类型与 SQLAlchemy 集成包，不是 PostgreSQL Server Extension 的生产版本决定。托管 PostgreSQL、Server Extension、索引参数、容量与迁移门禁仍以技术选型文档为准。

## 3. 跨语言合同格式

第一阶段合同采用 OpenAPI 3.1、JSON Schema 2020-12 和 AsyncAPI 3。这里只固定语言独立的交换格式，不创建尚未审核的字段，也不选择代码生成器。TypeScript、Python 和 Java 的生成方式必须消费同一版本化 Schema，但 Java 侧生成器需要等 Java 工具链评审后再确定。

## 4. Java 工具链保留边界

Java/Spring Boot `platform-api` 的运行时方向和 MySQL/Flyway Schema 所有权继续沿用现有架构决策，但以下项目保持 `UNSELECTED`：

- JDK 发行版与具体版本。
- Maven 或 Gradle，以及 Wrapper 和多模块构建形态。
- Spring Boot、Flyway 和 Java 测试工具的具体版本。
- OpenAPI、JSON Schema、AsyncAPI 的 Java 代码生成器与生成方式。
- Java 构建缓存、镜像和 CI Job。

因此本轮不创建 `pom.xml`、`build.gradle`、`settings.gradle`、Maven/Gradle Wrapper、`.java-version` 或 Java CI。仓库守卫会在这些文件未经新决策就出现时失败；Java 工具链确定后，应在同一变更中更新本基线、守卫、工程清单和 CI。

## 5. 安装与验证入口

```sh
./tools/verify-repository.sh
./tools/verify-frontend.sh
./tools/verify-python.sh
```

三个入口分别验证仓库/文档、Node/pnpm Workspace 和 Python/uv Workspace。当前不提供名为 `verify-all.sh` 的统一通过信号，因为 Java 工具链和 Java 工程尚未建立；把三个非 Java 检查通过写成“整个 Monorepo 已验证”会制造虚假的完成状态。

`pnpm-lock.yaml` 和 `uv.lock` 是当前 Checkout 的依赖解析事实。更新直接依赖时必须同步更新对应 Manifest、锁文件和本基线；锁文件存在不关闭真实云产品、模型、迁移、安全、容量或合同门禁。

## 6. 与七天路线的关系

本基线只完成开工前“工具版本”检查中的非 Java 部分。Java 工具链、Schema 生成方式以及其余九类开工条件仍未全部通过，所以第一阶段项目状态保持 `NOT_STARTED`，Day 1 起始日期为空，`P1-00` 的合同与测试基座也尚未开始计时。
