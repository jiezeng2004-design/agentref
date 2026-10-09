# 真实测试报告：2026-10-09

> 发布补充：本报告完成后，用户确认其余验收已由本人验证并授权发布 alpha.4。
> 人工确认与下方自动化实测分别记录；当时的失败和未发布状态作为测试快照保留。
> 发布候选与最终事实入口见 [当前验收表](CURRENT_ACCEPTANCE.md)。

## 结论

当前未发布 checkout 完成了受控 **Codex → DSH** 和 **DSH → Codex** 双向真实模型续做。
源模型真实写入第一阶段代码后，由控制器中断自己拥有的进程；接收模型消费当前 AgentRef
生成的上下文、读取工作区并补全 rollback。两个方向的三项固定测试在接收宿主及独立控制器
中全部通过。原始计划的 **Codex ↔ Claude** 仍未通过，Claude CLI 当前未登录。

基线：`main` / `a59f66f6b8a901adb8ffcca325abb31f6fcde251`，开始时已有 22 个
修改或未跟踪路径。没有提交、推送、发布或更新日常安装。测试日志、真实专用会话快照和截图
只保留在 ignored `demo-artifacts/real-1009` 及本轮临时目录，不进入公共测试夹具或包。

## 真实模型链

| 流程 | 结果 | 核对 |
| --- | --- | --- |
| Codex 0.147.0 → 新 Codex 接收任务 | 通过 | 真实中断与上下文读取；宿主及控制器各 3/3 |
| DSH 0.1.5-rc.2 → Codex 0.147.0 | 通过 | 真实 v3 zstd 来源；宿主及控制器各 3/3 |
| Codex 0.147.0 → DSH 0.1.5-rc.2 | 通过 | 真实 Codex rollout 来源；宿主及控制器各 3/3 |
| Claude Code 2.1.261 源阶段 | 阻塞 | 宿主返回 `Not logged in` / `/login`；没有代码产出 |
| Grok 1.0.30 源阶段 | 阻塞 | 宿主返回 `Not signed in`，刷新认证被拒绝 |
| OpenCode 1.18.16 默认模型源阶段 | 阻塞 | 宿主返回 xAI 刷新认证 `invalid_grant`；新会话 SQLite 读取成功 |

固定验收覆盖 register、移除已有键、忽略不存在的键。所有成功接收任务保留 register 的
原始文本，`test_registry.py` 和 `pause.py` 的 SHA-256 不变。两条成功中断源会话的
SHA-256 在读取和接收测试之后均不变；热刷新读入正文为 0 bytes。CLI 测试使用精确的
本轮测试会话或专用工作区目录，没有枚举私人正文、恢复旧会话或手工读取凭据。

这证明特定版本、默认配置和小型固定任务的真实可接续性；不证明任意项目或其它平台均能
成功续做。模型使用宿主正常配置，未指定新 provider/model，未关闭宿主沙箱。

## 真实宿主交互

| 层级 | 本轮结果 | 边界 |
| --- | --- | --- |
| 已安装 Codex app-server / MCP | 五种来源的扩展元数据、候选和选中资源读取全部通过 | 隔离配置与合成来源；没有 Desktop 可见菜单或模型 |
| app-server 故障来源 | Claude、Grok、Antigravity 不完整索引警告及选中资源诊断通过 | 额外损坏的合成来源；未改真实会话 |
| 当前 `@ganetref` MCP | 五个非 Codex 来源入口返回正确 | 入口元数据；没有自动选择会话 |
| DSH Web 0.2.0-rc.2 + Chromium | 官方 CLI 安装当前打包插件；原生 chip、取消、移除、发送时精确读取和来源失效阻止发送通过 | 独立 profile、官方 Session API 合成 v4 会话；发送在模型前拦截 |
| OpenCode 1.18.16 TUI + PTY | 当前插件装载；单一专用会话菜单、Enter 插入附件、Esc 保留草稿和已有附件通过 | 临时配置/数据目录；没有发送提示，未扩展到模型验证 |
| Antigravity runtime | 现有 loopback DevTools 端点不可连接 | 没有开启调试端口、修补程序或更改日常设置 |
| Codex Desktop | 尚待人工 | `computer-use` 技能明确禁止自动操作 Codex Desktop UI；协议验收不替代两次 Tab 菜单 |

DSH Web 的 HTTP 记录确认：候选浏览、选中 chip、移除 chip 之前正文读取为 0；成功发送时
读取所选 ref 一次。选中后暂时移走本轮合成源，第二次发送没有到达被拦截的提示接口，
草稿保留且显示来源不可用。随后恢复合成源，SHA-256 相同。页面错误为 0，截图已视觉核对。
自有浏览器和 CLI 已退出，loopback 监听已关闭。

## 测试发现及修复

1. 初始 Codex `pause.py` 检查点失败：独立 Windows 沙箱身份不能访问测试文件。
   保留失败记录；改用“第一阶段文件已验证且源进程仍运行”的检查点实施真实中断。
   接收测试仅在专用合成工作区添加临时共享 ACL，正常宿主沙箱保持启用。测试后撤销新增
   Users 权限；访问规则与原始基线等价。
2. 首次 DSH CMD 入口丢失多行代码片段，模型未写代码。随后使用同一安装的 Node CLI
   入口传递完整 argv，真实源阶段通过。没有把首次失败算作成功。
3. 日常 DSH 写出的正式 `session.v3.jsonl.zstd` 被 v0/v4 适配器拒绝。对照安装中的官方
   Session 0.1.5-rc.2 和 Persistence 0.1.5-rc.2，补上 v3 读取：v3 使用现代 surface
   序号/压缩引用和嵌入流，但工具结果仍为旧内容块包装；v4 使用直接 toolCallId message。
   未对未知代际回退，未对源实施迁移或修复。元数据插件事件仍会显示未知记录警告。

新增五项回归覆盖 v3 结果/未完成调用、压缩源不变、compaction 引用和影子目标排除、非法
header/顶层旧流拒绝、v3→v4 重选与未知未来代际拒绝。v0/v4 既有回归保留。

## 当前回归与收尾

- DSH 定向回归：35 项，34 通过、1 项符号链接能力跳过。
- Python 3.14.6 全量：298 项，296 通过、2 项符号链接能力跳过。
- Node 24.18.1：DSH / OpenCode / Antigravity 44/44。
- 本轮自有模型进程、OpenCode TUI 和 DSH Web 均已结束，未保持测试服务常驻。
- 未执行跨平台 CI、生产验证或发布。没有自动登录、复制认证状态、改 provider 路由、
  安装日常插件或重载日常宿主；CLI 正常启动留下本轮专用测试会话及其宿主正常运行记录。

回退范围仅为本轮 `agentref/adapters/dsh.py` 的 v3 增量、`tests/test_dsh_v3.py` 和本轮
文档改动。保留此前 DSH v4、核心优化与用户改动，避免 reset/clean/stash 整个工作区。
后续完整原始验收需要恢复 Claude 登录、Grok/OpenCode 正常认证，并人工完成 Codex Desktop
两次 Tab。Antigravity 需要可用的已有调试端点；没有自动改变这些外部条件。
