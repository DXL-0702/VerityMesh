# 对象存储选型

## 文档定位

本文件只记录对象存储产品及其产品级形态选型；详细设计以架构与安全文档为准。

当前 `platform-api` 已通过 AWS SDK for Java v2 的 S3-compatible API 接入 Source Storage Adapter；本地使用 MinIO 验证同一协议，生产仍指向已选的阿里云 OSS。Adapter 负责服务端生成 Source Zone key、短期预签名 PUT、HEAD 元数据读取和流式 SHA-256 校验，领域层不依赖供应商 SDK 类型。生产 Region、Bucket、账号拆分、云权限和生命周期参数仍未冻结。

## 外部依赖选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 对象存储服务 | 保存权威内容、不可变 Revision、治理产物和发布资产 | 阿里云 OSS | Bucket、账号、安全域、存储级别、版本与生命周期参数未定 | `SELECTED` | Source、Governance、Published Knowledge 和恢复资产 | 1A | 独立备份或归档服务可作为恢复能力补充 | 与主云一致，提供托管对象存储、版本和生命周期能力 | 冻结 Bucket/账号拆分、Region、存储级别及恢复相关产品参数 |
