# Grounding 模型选型

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 云端轻量语义验证主候选 | 高频判断 Claim 与 Evidence 的支持、矛盾、证据不足和部分支持关系 | 阿里云百炼 `qwen3.7-flash-2026-07-15` | 北京云 API；关闭思考；非流式 JSON Object | `PRIMARY_POC` | 在线 Grounding Light | M1 | StructBERT Base 自托管；方舟 `doubao-seed-2-0-mini-260428` | 固定日期版本、长上下文和较高公开额度，适合先打通云端语义验证；输出仍需服务端校验 | 完成企业 Claim-Evidence 数据集上的质量、格式稳定性、并发、延迟和成本 PoC |
| 自托管轻量语义验证挑战者 | 以专用中文 NLI 承载长期高频 Grounding Light | StructBERT Chinese NLI Base `v1.0.1` | ACK 自托管；Commit `17853efae08b969006cfa19f27323ee43cfed2df`；Apache-2.0 | `CHALLENGER_POC` | Grounding Light Shadow，达标后可成为长期主选 | M1.5 | 百炼 `qwen3.7-flash-2026-07-15` | 专用中文 NLI、可自托管并控制成本；需要企业领域微调、四分类扩展和阈值校准 | 选择推理运行时，完成领域微调、Shadow、容量和可用性验证 |
| 跨云轻量语义验证挑战者 | 在百炼不可用或跨云比较时提供轻量 Grounding | 火山方舟 `doubao-seed-2-0-mini-260428` | 北京云 API；关闭思考；严格结构化输出能力为 Beta | `CHALLENGER_POC` | Grounding Light 跨云备供 PoC | M1 | 百炼 Flash；ACK StructBERT Base | 固定日期版本、公开额度较高且支持结构化输出，可作为供应商级挑战者 | 核实结构化输出与容量保障限制，完成跨云合同、质量、延迟和成本评测 |
| 云端质量对照 | 建立 Grounding Light 的云端质量上界 | 阿里云百炼 `qwen3.7-plus-2026-05-26` | 北京云 API；关闭思考；支持严格结构化输出 | `BENCHMARK` | 离线评测 | M1 PoC | 不进入默认生产路由 | 固定版本且质量高于轻量候选，适合作为质量对照 | 用同一密封数据集完成对照，确认轻量候选的质量差距 |
| 自托管质量对照 | 评估更大 NLI 模型是否值得增加推理成本 | StructBERT Chinese NLI Large `v1.0.1` | ACK 自托管；Commit `4cea8270584a4563661ba05e2890022edc7931cf`；Apache-2.0 | `BENCHMARK` | 离线及 Shadow 对照 | M1.5 PoC | StructBERT Base | 通用 NLI 指标仅小幅高于 Base，需证明规模收益才能承担更高成本 | 比较 Base/Large 的领域质量、吞吐、资源和总成本 |
| 云端延迟对照 | 建立低成本、旧版本轻量模型的延迟基线 | 阿里云百炼 `qwen-turbo-2025-04-28` | 北京云 API；关闭思考；JSON Object | `BENCHMARK` | 离线性能对照 | M1 PoC | 不进入默认生产路由 | 固定版本且成本较低，可帮助判断延迟收益是否值得质量损失 | 重点验证否定、限定词、部分支持和证据不足的区分能力 |
| 强语义验证模型 | 处理多跳、多 Evidence、冲突、跨项目和高风险语义判断 | 未选 | 候选形态为复用 Generator 强模型或选择独立模型家族 Judge | `UNSELECTED` | 条件触发的 Grounding Strong | M2 | Evidence-only 或拒答；不以逐 Claim 大模型调用作为回退 | 应在轻量层灰区和高风险样本稳定后决策；独立 Judge 可降低同源错误相关性 | 基于真实灰区样本比较复用强模型与独立 Judge 的质量、延迟、成本和供应商风险 |
