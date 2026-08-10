# VerityMesh

本文件只提供仓库入口，不复制架构、选型或实施事实。

| 需要了解的内容 | 唯一入口 |
| --- | --- |
| 项目目标、领域边界与系统约束 | [`tech-plan.md`](tech-plan.md) |
| 端到端开发架构图 | [`architecture.md`](architecture.md) |
| 外部依赖选择与决策状态 | [`technology-selection/technology-selection.md`](technology-selection/technology-selection.md) |
| 改变架构边界的重大决策 | [`adr/`](adr/) |
| 组件设计、接口、状态机与交付拆分 | [`implementation-designs/`](implementation-designs/) |
| PoC 证据与限制 | [`poc-reports/`](poc-reports/) |
| 部署、升级、恢复与排障步骤 | [`runbooks/`](runbooks/) |

## 仓库验证

提交前运行：

```sh
./tools/verify-repository.sh
```

该命令检查 Markdown 本地链接、`architecture.md` 的有向连通性，并运行文本检索 PoC 的单元测试和本地合同验证。云端 PoC 需要显式配置和批准，不属于默认仓库验证。

协作与提交规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
