# 本地集成环境

本目录提供第一阶段开发使用的 Docker Compose 依赖底座和两个独立 Migration Job。它只用于本地开发、合同联调和迁移验证，不代表生产部署编排，也不改变云托管产品的选型状态。

## 覆盖范围

| 服务 | 本地镜像 | 宿主端口 | 作用 |
| --- | --- | ---: | --- |
| MySQL | `mysql:8.4` | `13306` | Java 业务与控制状态 |
| PostgreSQL/pgvector | `pgvector/pgvector:pg16` | `15432` | Python Vector Projection |
| Kafka | `apache/kafka:3.9.1` | `19092` | 可重放领域事件；容器内使用 `kafka:29092` |
| Redis Online | `redis:7.4-alpine` | `16379` | Session、撤回和在线短期缓存 |
| Redis Celery | `redis:7.4-alpine` | `16380` | Celery Broker/短期 Result |
| Elasticsearch | `docker.elastic.co/elasticsearch/elasticsearch:8.17.0` | `19200` | 本地 BM25 投影验证 |
| OSS 兼容对象存储 | `minio/minio:RELEASE.2025-04-22T22-12-26Z` | `19000/19001` | Source 与治理资产 |
| `object-storage-init` | `minio/mc:RELEASE.2025-08-13T08-35-41Z` | — | 创建 Source bucket、最小对象读写身份并执行读写探针 |

Compose 目前不启动 `platform-api`、`assistant-runtime` 或 `batch-worker` Deployment：这些服务还没有本地运行镜像，本批次只建立它们依赖的真实协议底座和迁移入口。

## 启动与停止

在仓库根目录执行：

```sh
docker compose -f infra/local/compose.yaml config --quiet
docker compose -f infra/local/compose.yaml up -d \
  mysql postgres kafka redis-online redis-celery elasticsearch object-storage
```

首次使用或清空卷后，必须运行一次性对象存储初始化 Job：

```sh
docker compose -f infra/local/compose.yaml run --rm object-storage-init
```

该 Job 使用本地 MinIO root 身份创建 `veritymesh-source` bucket、绑定
`source-zone/*` 的最小 `GetObject`/`PutObject` 权限，并用应用身份完成一次写入和读取探针，最后由初始化身份清理探针对象。
`platform-api` 不应使用 MinIO root 凭据；本地启用真实 Adapter 时使用以下环境变量：

```sh
export VERITYMESH_SOURCE_STORAGE_ENABLED=true
export VERITYMESH_SOURCE_STORAGE_ENDPOINT=http://localhost:19000
export VERITYMESH_SOURCE_STORAGE_REGION=us-east-1
export VERITYMESH_SOURCE_STORAGE_BUCKET=veritymesh-source
export VERITYMESH_SOURCE_STORAGE_ACCESS_KEY=veritymesh-source
export VERITYMESH_SOURCE_STORAGE_SECRET_KEY=veritymesh-source-local-secret
export VERITYMESH_SOURCE_STORAGE_FORCE_PATH_STYLE=true
```

应用启动默认保持 fail-closed；未显式设置 `VERITYMESH_SOURCE_STORAGE_ENABLED=true` 时，上传预约继续返回
`source_storage_unavailable`。

查看健康状态：

```sh
docker compose -f infra/local/compose.yaml ps
```

停止容器但保留本地数据：

```sh
docker compose -f infra/local/compose.yaml down
```

如果要重新验证空库初始化，必须明确删除本地卷；该操作会丢弃本地集成数据：

```sh
docker compose -f infra/local/compose.yaml down -v
```

## 独立 Migration Job

迁移源仍归各服务所有，`infra/local` 不复制 SQL 或 Alembic Revision：

| Job | 迁移源 | 身份 | 目标 |
| --- | --- | --- | --- |
| `platform-api-migration` | `services/platform-api/src/main/resources/db/migration/` | `veritymesh_migration` | MySQL |
| `batch-worker-migration` | `services/batch-worker/migrations/` | `veritymesh_migration` | PostgreSQL/pgvector |

启动依赖后运行两个 Job：

```sh
docker compose -f infra/local/compose.yaml run --rm platform-api-migration
docker compose -f infra/local/compose.yaml run --rm batch-worker-migration
```

两个 Job 都可以重复执行。Flyway 会报告 Schema 已是最新版本，Alembic 会报告没有待执行 Revision；它们不应重新创建或破坏已存在的表。

## 身份边界

本地初始化脚本建立数据库身份，并由独立对象存储 Job 建立对象身份：

- `veritymesh_migration`：只供一次性 Migration Job 使用，拥有对应数据库的 DDL 权限；PostgreSQL Job 在每次迁移完成后把新建投影表的 DML 授权同步给 `veritymesh_app`。
- `veritymesh_app`：模拟应用运行身份。MySQL 只有数据库级 DML；PostgreSQL 只有 `public` Schema 的 DML，并显式撤销 `CREATE` 与临时表权限。

应用运行身份不应出现在 Migration Job 的连接串中。生产环境必须使用独立 Secret、最小权限账号和预部署 Job，不能复用这里的本地密码。

对象存储身份同样分离：`object-storage-init` 只在本地初始化时使用 MinIO root；`veritymesh-source`
只拥有 `veritymesh-source/source-zone/*` 对象读写权限，不拥有 bucket 管理权限。生产环境必须由云平台
Secret/Workload Identity 提供等价的最小权限角色，不能复用 root 或本地静态凭据。

## 一键验证

```sh
./tools/verify-local-integration.sh
```

验证脚本会检查 Compose 配置、启动依赖、运行对象存储初始化 Job、运行两个 Migration Job 两次，并以应用身份验证对象读写和数据库 DML 可用且 DDL 被拒绝。脚本不会自动删除数据卷；执行空库验证前请先手动运行 `docker compose ... down -v`。

本机 Docker daemon 未启动时，脚本会直接报告环境阻塞，不会把静态 Compose 检查冒充为容器集成通过。当前本地凭据均为一次性开发值，禁止用于云环境。
