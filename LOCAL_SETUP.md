# 本机已配置的使用入口

> 本文是维护者机器上的历史验证记录，不代表读者安装后的状态。新安装请从
> [README](README.md) 和 [Codex 集成说明](integrations/codex/README.md) 开始。

## 当前新增入口：DSH `@` 会话引用（2026-09-08）

DSH 的 `web` profile 已加入本地链接插件 `dsh-agentref`。在 DSH 的对话输入框
输入 `@claude`、`@codex`、`@grok`、`@opencode` 或 `@antigravity`，从弹出的本地
历史会话列表中点选一条，再继续输入本次任务并发送。可用
`@claude:关键词`（替换来源名称）按会话标题、工作区或 ref 前缀筛选。

点选后输入框会显示 **AgentRef 会话** 标记；在发送当前消息前，插件才把这一条
已明确选择会话的受限续接上下文附加到消息中。候选浏览只读取元数据，不会自动
选择、恢复或修改外部会话。该消息仍会按 DSH 当前模型/Provider 的普通数据策略
发送；AgentRef 插件本身没有云端、模型或来源会话写入能力。

已验证：本地链接安装、DSH `web` 组合启动、浏览器端认证边界、AgentRef 命令解析
与 Claude 候选元数据读取。尚未做真实认证 DSH 页面上的点击/标记画面或真实模型
续接验收，不能把启动与协议验证说成完整 UI/生产 E2E 证明。

撤销仅此入口：`dsh plugin rm --profile web dsh-agentref`。这会移除 web profile
中的链接依赖，不会删除 AgentRef 源码、DSH 会话、原始 Claude/Codex/Grok/OpenCode/
Antigravity 会话或 Provider 配置。

## 当前新增入口：Grok / OpenCode / Antigravity（2026-09-05）

保留原有 Claude/Codex，新增三个来源；没有启用 Gemini CLI 或 Qoder。

Codex **新建任务**后输入 `@grok`、`@opencode` 或 `@antigravity`，
选择对应的“会话 · AgentRef”入口，展开按最近更新时间排列的会话名称，
选择具体会话后发送任务。已打开的任务可能不会热加载新增插件。

Claude Code 重开后输入对应 `@grok` / `@opencode` / `@antigravity`，
选带菱形的资源入口并按 Tab；也可输入 `@grok:agentref://session/`
（替换 agent 名称）展开候选。Store Claude Desktop 的同名 MCP 配置已加入，
需重开客户端加载。

本机元数据检查：Grok 60 个、OpenCode 34 个、Antigravity 35 个主会话。
Antigravity 同时发现 Desktop 与 CLI 存储，并排除了包含 subagent_spec 的轨迹。
这些是本次检查数量，后续会随使用变化。

Antigravity 是实验性支持：已解析用户/助手正文和命令证据；其他工具正文、
附件未完整解析，资源会保留警告。不能据此判定所有操作完成。

验证：新增插件均 installed/enabled；Claude 三个 MCP 均 Connected；
实际插件 MCP 元数据检查和三个隔离 Codex app-server 合成会话的候选/资源读取
检查通过。未完成新增入口的真实 Desktop 点击/chip 画面与真实模型续写验收。
没有把用户私人会话作为模型续写测试样本。

配置只新增三个 `*@personal` 插件和现有 Claude 两个宿主中的同名 MCP 条目；
Codex 非 plugins 顶层值、原有插件、Claude 其他设置和 MCP 条目已比较保持。
插件源位于 `~/plugins/{grok,opencode,antigravity}`，仍使用本仓库 editable 安装。

撤销新增入口（保留旧 Claude/Codex 和所有原始会话）：
`python scripts/configure_extra_agents.py --apply --rollback`。
撤销会保留未启用的插件源码和市场条目；不恢复整个宿主配置。
复核安装入口：`python scripts/verify_extra_agents.py`（只读取元数据，不选择正文）。

以下为原有 Claude/Codex 入口和更早的安装记录。

## 当前入口：输入框内按时间选择（2026-09-05）

Codex：新任务输入 `@claude`，选中 **Claude 会话 · AgentRef** 的子菜单入口，
展开按会话更新时间从新到旧排列的候选。选中具体会话，再发送你的任务。
宿主调用 `search_mentions`，选择后插入资源引用；不是发送后才列列表。
工具通过本机客户端识别的 `openai/extensions: {mentions/search: {}}` 声明入口。
这是本机 Codex 26.901.5280.0 的客户端扩展契约，并非所有旧宿主的通用保证。

Claude Code：输入 `@codex`，用方向键选带 **◇** 的 `codex:agentref://session/`
入口，按 **Tab**；会在输入框下方显示按时间排序的会话名称，再用方向键
和 Tab 选中。第一层可能混有同名文件，选择有“按最近更新时间选择会话”说明的入口。
也可直接输入 `@codex:agentref://session/` 展开。每次动态补全刷新索引；普通资源
搜索会被 Claude 按相关性重排，所以本机使用 `--template-menu` 禁用静态候选混排。
Claude 最多显示 15 条补全；继续输入标题关键词可以筛选。
两端候选不显示日期或 ID。Claude 名称中的空格和标点会转成下划线以适配引用语法；
同名候选以 `_2`、`_3` 区分，名称与目标的绑定保存在 AgentRef 索引中。

验证：56 项测试通过；安装后的 Codex app-server 保留原生候选声明，成功完成
候选调用和所选资源读取；Claude Code 2.1.261 真实终端已验证菜单展开、时间顺序、
选择插入。测试使用合成会话。Claude 模型回答因 `Not logged in` 未通过。
用户截图已确认 Codex Desktop 会话子菜单；本轮名称简化后的 Desktop 画面尚未复核。

本次新增配置只涉及两个已有 `mcpServers.codex.args` 的 `--template-menu` 参数，
并更新 Codex 的 `claude@personal` 插件。没有改 Provider、登录、权限或原始会话。
撤销本次 Claude 参数：`python scripts/enable_native_menus.py --apply --rollback`。
Codex 插件仍保留 `pick_session` 对话降级入口。

以下为此前安装与验证的历史记录，不代表当前菜单实现状态。

## 历史记录：桌面端 picker 问题修正

用户实际 Desktop 任务 `Locate Claude 会话内容` 调用了 pick_session，但约
0.7 秒即返回取消；不能据 CLI 表单成功推断 Desktop 表单可用。
现已默认关闭 MCP 原生弹窗，改为立即返回具体会话候选，供当前 agent 展示编号。
38 项测试通过，真实本地 MCP 调用返回 29 个候选且不请求弹窗。
`--native-picker` 仅供已经验证兼容的宿主显式启用。客户端错误不再当作用户取消。

**仍未实现：输入框 @ 自动补全菜单直接列出每一条历史会话。**
当前是 @ 插件 -> 发送 -> 对话列表 -> 选会话，不是用户原始目标的完全实现。
下文的原生表单记录仅为此前 CLI 验证，不能作为现在默认交互或 Desktop 证明。

本次已实际安装，用户不需要再编辑 JSON/TOML。

## Codex

打开一个新任务，输入 `@claude`，选择 **Claude 会话 · AgentRef**，发送。
插件会调用 `pick_session`，在支持的客户端显示原生会话选择表单。
选中后读取 continuation context，并核对当前项目；取消则不读取会话正文。

真实 Codex CLI 0.147.0 已验证：@ 菜单出现插件、发送后原生表单显示
29 个 Claude 会话、Esc 取消后工具返回取消结果。Desktop 读取同一安装配置，
但本次没有直接观察 Desktop 表单；已有任务不会热加载新增插件，需新任务。

## Claude

新开 Claude Code，输入 `@codex`，在补全菜单中选择带菱形的会话资源。
普通文件和目录也可能匹配 codex，注意选择 MCP 资源。
真实 Claude CLI 已看到资源菜单；`claude mcp get codex` 为 Connected。

Claude Desktop 的 Store 版配置也已新增相同服务，重开客户端后加载。
这里的 Desktop 指本机安装的 Claude Code/聊天 MCP 宿主，不是云端任务。

Claude 原生客户端当前显示未登录。`ocx claude` 当前报告
`config.claudeCode.enabled=false`。这些是既有模型接入状态，未修改。
因此 Claude 的模型续写仍不可用；Codex 读取 Claude 本地历史不受此影响。

## 安装内容与范围

- Codex：个人市场 `claude@personal`，installed=true，enabled=true。
- 插件源：`~/plugins/claude`。
- Claude 用户配置：新增 `mcpServers.codex`。
- Store Desktop：其 LocalCache/Roaming/Claude 下的
  `claude_desktop_config.json` 新增 `mcpServers.codex`。
- 可执行文件：本仓库 `.venv/Scripts/agentref.exe`，editable 安装。
- 工作区允许根：安装时明确配置的项目父目录。工具使用当前任务传入的绝对路径，
  不从外部 transcript 自动授权读取。其他路径会拒绝。
- 不启动被引用的 agent，不修改 foreign session，不执行历史命令。

新增配置时逐个比较顶层值摘要：Codex 仅 plugins 改变；Claude/桌面仅
mcpServers 改变。之后真实 Claude 启动自行更新了 numStartups、projects、
closedIssuesLastChecked；其中 projects 包含对本项目的工作区信任确认。
未改变模型、Provider、登录或权限模式。未复制或输出凭据。

## 已验证

36 个自动化测试通过，包括原生选择的协议交互、取消、客户端不支持时降级、
workspace allowlist。插件官方校验脚本通过。安装后 MCP 真实子进程无协议错误。
本次创建的真实 Claude demo 会话可通过 context 读取并核对当前 workspace；
源 session SHA-256 不变。未选取私人会话做续写测试。

仍未完成：Desktop 实际 UI、Claude 模型可用性、双向真实中断续写最终测试。

## 精确撤销方式（仅在需要时执行）

```powershell
codex plugin remove claude@personal
claude mcp remove codex -s user
```

Desktop 只移除其 `mcpServers.codex` 条目，保留其他键。个人市场和插件源可保留，
不会自动启用。不要还原整个宿主配置文件，不要删除原始 Claude/Codex 会话。
