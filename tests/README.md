# 跨服务测试

本目录负责必须跨越两个及以上组件才能验证的合同、端到端、密封评测、安全、性能和恢复测试。单个组件的单元测试与局部集成测试留在对应应用、服务或包中。

当前只建立跨服务测试所有权；非 Java Workspace 的组件烟雾测试和分层验证入口已经初始化，但跨服务夹具、合同测试、E2E 与全语言统一入口仍在 P1-00 创建。Java 工具链确定前不提供 `verify-all.sh`。第一阶段验收范围见 [`执行方案`](../docs/implementation-designs/0001-phase-1-execution-plan.md)，逐日验证入口见 [`七天执行路线`](../docs/implementation-designs/0002-phase-1-seven-day-execution-route.md)。
