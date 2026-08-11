# VerityMesh 文档目录

本目录集中保存跨组件、跨语言和跨阶段的项目事实源。根目录 [`README.md`](../README.md) 只负责项目展示和导航；组件目录中的 README 只说明本地所有权、构建入口和验证方式，不得重新定义全局架构。

| 需要维护的事实 | 唯一位置 |
| --- | --- |
| 系统目标、领域边界、安全不变量与服务目标 | [`tech-plan.md`](tech-plan.md) |
| 端到端用户交互与开发架构图 | [`architecture.md`](architecture.md) |
| 改变架构边界的重大决策与权衡 | [`adr/`](adr/) |
| 外部产品、服务、模型和第三方库的选型状态 | [`technology-selection/`](technology-selection/) |
| 接口、状态机、实施方案与执行路线 | [`implementation-designs/`](implementation-designs/) |
| PoC 数据、报告、限制与证据 | [`poc-reports/`](poc-reports/) |
| 部署、升级、恢复与排障步骤 | [`runbooks/`](runbooks/) |

## 根目录保留项

- [`../README.md`](../README.md)：仓库与项目展示入口。
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md)：协作、提交和验证契约。
- 各应用、服务与包的局部 README：只描述对应代码边界，不承担系统级事实源职责。

新增文档时先判断它回答的是架构、决策、实施、证据还是运行问题，再进入上表对应目录。不得在根目录新增平行的技术方案，也不得在组件 README 中复制整份全局边界。
