# Vector Projection Migration

`migrations/` 是 `batch-worker` 唯一拥有的 PostgreSQL/pgvector Schema 迁移源。

- 只由独立预部署 Migration Job 执行，Worker 运行身份没有 DDL 权限。
- `projection_builds` 和 `vector_projection_chunks` 都是可由 Kafka/OSS Manifest 重建的投影，不是 MySQL 业务真相。
- Embedding 使用未固定维度的 `vector` 类型，具体 Embedding Space 与模型 Revision 写入行级元数据；正式索引维度必须在模型选型和评测门禁关闭后通过新的版本化迁移增加。
- 迁移通过 `VERITYMESH_VECTOR_DATABASE_URL` 注入连接串；禁止把凭据写入 `alembic.ini` 或仓库。

本地生成 SQL：

```sh
cd services/batch-worker
uv run alembic upgrade head --sql
```
