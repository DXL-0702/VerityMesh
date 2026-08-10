# AI Gateway 选型

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Higress AI Gateway | 提供 Provider 协议转换、连接池、Token 统计、Endpoint 级限流/负载均衡和传输观测 | 暂不引入 | 后期可部署在 Model Access Service 下游；具体版本未定 | `DEFERRED` | Model Access Service 与外部 Provider Endpoint 之间 | 当前不引入；触发条件成立后 PoC | 继续使用 Model Access Service 的自研 Provider Adapter | 当前仅两个云 Provider，新增一跳的收益不足；Provider 增多、SSE 连接或密钥池复杂度上升时才可能产生价值 | 当生产 Provider 达到三个及以上，或连接、协议、密钥池维护成为主要瓶颈时启动专项 PoC |
| Higress 领域编排扩展 | 在 Higress 内启用 RAG、Memory、Prompt、Intent、Agent、MCP 或语义缓存 | 不采用 | Higress 相关插件或扩展能力 | `REJECTED` | 不进入平台链路 | 全阶段 | 由平台既有知识、Memory、Router、Prompt 和 Agent 边界承担 | 会形成第二套知识、路由、上下文和审计控制面，与项目隔离和不可变发布模型冲突 | 不再评审，除非平台领域架构正式重构 |
