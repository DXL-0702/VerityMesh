# 数据源 Connector 选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 无边界通用 Connector 平台 | 以统一市场方式连接任意企业数据源 | 第一阶段不建设 | 通用 Connector 市场 | `REJECTED` | 不进入第一阶段架构 | 后期重新立项才评审 | 上传、批量导入、签名 Push API 和已审批的具体 Connector | 数据权限、网络、删除和增量语义无法用一个无边界平台统一假定 | 出现明确规模收益且治理模型成熟后重新立项 |
| 具体数据源 Connector | 将一个已审批数据源同步到 Source Zone | 未选择，逐数据源登记 | 专用 Connector 或经批准的现成连接器 | `UNSELECTED` | Source 接入层 | 按项目逐个引入 | 上传、批量导入、签名 Push API | 每个数据源的权限、Cursor、限流、删除与审计语义不同 | 首个数据源确定后建立独立 Decision ID 和 PoC |
| 项目业务 API Connector / Tool Executor | 经用户与对象授权读取实时业务数据或执行受限操作 | 暂不引入 | 受控 Tool Adapter | `DEFERRED` | Assistant Tool Runtime | 第二阶段 | 只返回知识库 Evidence，不调用实时业务 API | 属于业务工具生态，不应混入第一阶段通用知识索引 | 第二阶段另行评审 Tool Contract 与 OAuth 边界 |
