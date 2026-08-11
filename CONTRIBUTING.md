# VerityMesh 仓库协作契约

## 分支模型

- `main` 是唯一长期分支，必须始终保持可验证。
- 基线建立后，变更使用短生命周期分支：`feat/*`、`fix/*`、`docs/*`、`chore/*` 或 `poc/*`。
- 不建立 `develop`，不采用 GitFlow；发布版本通过受验证提交上的 Tag 表达。
- 一个分支只承担一个可说明、可验证的目标，合入后删除。

## 提交规则

提交信息使用 Conventional Commits：

```text
<type>(<scope>): <imperative summary>
```

常用类型为 `feat`、`fix`、`docs`、`test`、`refactor`、`chore` 和 `build`。提交必须保持单一职责；架构事实、PoC 证据和生成缓存不能混成一个无法审计的提交。

不得提交真实凭据、未脱敏企业语料、本地 `.env`、云 PoC 私有配置、虚拟环境、依赖目录、编译产物或解释器缓存。可重复的 PoC 报告只有在数据边界、环境、版本、指标和限制均明确时才进入 `docs/poc-reports/`。

## 验证规则

提交前分别运行：

```sh
./tools/verify-repository.sh
./tools/verify-frontend.sh
./tools/verify-python.sh
./tools/verify-java.sh
```

默认验证不得访问云资源或修改外部状态。四个入口分别覆盖仓库边界、前端、Python 和 Java 工程基线；它们通过不代表真实云产品、模型或第一阶段验收门禁已经关闭。需要真实 Provider、Elasticsearch 或 OpenSearch 的 PoC 必须使用独立配置显式执行，并把证据边界写入报告。

文档所有权与目录边界以 [`docs/README.md`](docs/README.md) 为准；实现细节不得反向覆盖 `docs/tech-plan.md`、ADR 或技术选型状态。
