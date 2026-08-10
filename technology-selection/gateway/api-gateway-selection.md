# Public API Gateway 选型

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Public API Gateway 产品 | 承担公网 TLS、基础认证校验、流量保护、REST/OpenAPI 与 SSE 转发、入口观测及 WAF/DDoS 集成 | 未选 | 阿里云托管网关、ACK Ingress/API Gateway 或组合形态待形成短名单 | `UNSELECTED` | 浏览器、宿主后端和公开 API Client 到平台 Data Plane/Control Plane 的入口 | 1A 上线前 | 受控 ACK Ingress 作为候选回退形态 | 必须支持 SSE 长连接、连接排空、多维限流、配置版本化、多可用区、源站隐藏和标准协议退出路径；不允许浏览器直连模型 Provider | 冻结容量与安全输入，形成候选短名单，完成 SSE、认证、限流、故障、成本和退出 PoC |
