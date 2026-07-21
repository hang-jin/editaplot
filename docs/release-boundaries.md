# 发布、隐私与许可边界

> 本页记录 EditaPlot 在 2026-07-21 首次开源发布时的公开边界与长期约束，不构成法律意见。

## 公开版是完整产品

公开仓库包含完整 Codex Skill、清理后的自包含 runtime、模板、确定性 CLI、测试、双语文档、中性合成示例、原创配色和 37 个经 Origin 生成并复核的 PNG。它不是功能受限版，也没有隐藏的“私人高级模板”。

本地私有层只保留不适合随源码传播的开发与验证证据，例如用户数据、绝对路径、开发日志、OPJU/PDF/TIF、RenderPlan 和对象反读报告。它们用于复核，不构成另一套产品能力。

| 公开 GitHub 仓库 | 开发者或用户本地 |
|---|---|
| Apache-2.0 项目源码与完整 Skill | `DEVELOPMENT_LEDGER.md`、内部计划、开发日志 |
| 清理后的 runtime、模板与依赖锁 | `.build-venv`、缓存、临时输出、EXE/安装包 |
| 中性合成 CSV 与原创视觉资产 | 用户原始数据、参考截图、未获许可的材料 |
| 复核并清理元数据的 PNG | OPJU/PDF/TIF、RenderPlan、readback、verification JSON |
| 测试、provenance 与 SHA-256 清单 | 本机绝对路径、凭据、token、证书与 `.env` |

OPJU/PDF/TIF 若以后作为 Release 附件公开，必须另行确认再分发权、元数据脱敏、文件体积和来源清单；它们不会直接进入源码历史。

## 默认拒绝式公开白名单

`release/public-release-policy.json` 定义唯一公开文件集合，`tools/verify_public_release.py` 在发布前和 CI 中强制检查：

1. Git 索引与工作树一致，防止检查安全文件却提交旧内容；
2. 跟踪文件全部命中白名单，禁止子模块、符号链接、LFS 指针和高风险扩展名；
3. 扫描绝对路径、旧品牌、常见密钥/token 形式、私人邮箱和禁止文件名；
4. 校验 Apache-2.0 正文、NOTICE、精确依赖锁与 runtime SHA-256 manifest；
5. 校验公开资产 provenance、生成器绑定、人工审核记录和 gallery 精确集合；
6. 解析 PNG chunk、CRC、结尾、EXIF 与压缩文本，拒绝尾随载荷和敏感元数据；
7. 限制单文件与仓库体积，并拒绝日志、缓存、环境目录和未审查输出。

因此，旧 GitHub 历史、私人作者邮箱和早期品牌也不会成为公开分支的祖先；首次公开分支从经过审核的单一根提交开始。

## 已确定的开源路线

- 主品牌、仓库名与 Skill ID：`EditaPlot` / `editaplot`，不把第三方商标作为产品品牌。
- 项目自有代码、文档、合成数据与原创资产：Apache-2.0。
- 完整 Skill 与清理后的 runtime 一并公开；不捆绑第三方应用或 Python wheel。
- 软件可免费使用、修改和再分发。维护者可另行提供咨询、定制、安装协助和支持，但这些服务不削减 Apache-2.0 权利，也不代客户运行托管或远程自动化。

## Origin 兼容与法律边界

- 只连接用户在本机自行合法安装、激活并许可的 Origin/OriginPro；不分发 Origin、许可证或激活组件。
- 不把 Origin Automation Server 暴露到公共网络，不提供云端绘图或 service-bureau 服务。
- “兼容 Origin”只描述互操作性，不表示 OriginLab 认可、赞助或提供本项目。
- 环境自动修复只安装项目级 Python 依赖，不安装、启动、修改或激活 Origin。

OriginLab 的 [External Python 文档](https://docs.originlab.com/externalpython/)要求本机 Windows 中存在 Origin 2021 或更高版本。发布审计还核对了官方安装程序附带的 Origin/OriginPro 2024b EULA（2024-04-17 修订，SHA-256 `664A74D769FD62F23729E620EF2A47DBE295017C258674AF29BB6E605F3EBA8B`）以及 Origin 10.1.5 可执行文件的有效 OriginLab Authenticode 签名。现行文本可在 [OriginLab EULA](https://www.originlab.com/Index.aspx?go=PURCHASE&pid=1775) 查看，但网页版本可能随产品更新。

当前项目采用中性品牌，只做免费开源、本地单用户互操作，不分发第三方软件、不提供远程或云服务，因此按此边界公开。若以后改为收费软件许可、代算、托管、多租户、远程 Automation Server，或把第三方商标用于产品名、Logo 与营销标题，必须重新审计适用条款并取得所需书面许可。

公共仓库产生的 fork 或本地副本无法通过改回 private 收回。参见 [GitHub 许可说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)与[可见性变更说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)。

## 后续发行门禁

1. 每次 release 重新扫描密钥、绝对路径、PHI、日志、缓存和禁止扩展名；
2. 更新精确依赖锁、依赖许可证清单、资产 provenance 和 runtime SHA-256 manifest；
3. 新 Origin 路线先查官方文档并隔离验证，再完成 OPJU、PNG/PDF/TIF、对象反读与视觉 QA；
4. 若分发含 PySide6/Qt DLL 的 EXE 或安装包，先完成 LGPLv3 全部义务或取得 Qt 商业许可；
5. 若商业模式、远程边界或品牌发生变化，重新执行 OriginLab 许可与商标审计。
