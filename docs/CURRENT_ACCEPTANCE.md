# 验收记录 — 更新于 2026-09-26

## 发布授权补充（2026-09-26）

用户已确认全部待发布改动纳入 alpha.3，并明确授权提交、推送、候选 CI 通过后
创建标签和 GitHub prerelease。下节是授权前的本地验收快照，保留当时未提交状态；
发布结果以 [alpha.3 Release](https://github.com/jiezeng2004-design/agentref/releases/tag/v0.1.0-alpha.3)
中的固定提交、CI 和附件摘要为准。真实宿主/模型验收仍是开放缺口，不因发布而关闭。
生成输出与个人数据不进入源码；不发布 PyPI/npm，也不重载已安装宿主。

## 发布前验收结论（2026-09-26，本轮复核）

**alpha.3 本地自动化门槛通过；尚未达到完整发布验收。** 候选未提交，不能用
alpha.2 的远端 CI 替代候选 CI，也不能用合成页面替代真实宿主/模型续做。
下方按日期保留历史过程；当前结论以本节为准。

- 基线：`main` / `1018072c89ce7e44bb4cc42ed1fe09cd7d5b9c9c`；开始时已有
  56 个已跟踪修改文件、18 个未跟踪文件，无暂存改动。它们不是本轮新实现。
- 版本一致：`pyproject.toml` 与 `agentref.__version__` 均为 `0.1.0a3`，
  DSH 为 `0.1.0-alpha.3` 且保持 `private: true`。本轮没有再次递增版本。

| 验收层级 | 本轮结果 | 边界 |
| --- | --- | --- |
| Python 3.14.6 | 共 268 项，266 通过、2 跳过 | 两项需要 Windows 目录符号链接能力 |
| Python 3.11.15 | 隔离环境安装声明的 zstandard 后，共 268 项，266 通过、2 跳过 | 裸解释器缺依赖时曾出现 3 项错误；未修改全局 Python |
| Node 24.18.1 | DSH / OpenCode / Antigravity broker 共 38 项全部通过；6 个 JS 文件语法检查通过 | 不是 CI 的 Node 22 实测 |
| DSH 分发文件 | 按构建脚本算法逐字节核对两个 lib 文件，与源码一致 | 未覆盖或重建用户文件 |
| 合成 demo / scale | 双向 demo 与六来源七场景通过；每场景 3 sessions / 3 turns / width 64 | 源哈希不变，最新证据保留，上下文有界；未调用模型 |
| 性能等价检查 | 开发检查清单中六个基准全部通过 | 临时合成数据；不是稳定性能承诺 |
| wheel | Python 3.11 / 3.14 均隔离构建、源码树外安装；16 项资源哈希及 CLI / MCP 通过 | wheel 为 0.1.0a3；临时产物已由检查脚本清理，不是待上传附件 |
| DSH Chromium fixture | 六来源、警告/空结果、一次明确读取、一次后续合成发送，零页面错误 | 不是已认证 DSH 应用 |
| Antigravity Chromium/CDP fixture | 六来源、取消/过期草稿、鼠标/键盘、前缀保留、不自动发送、helper 停止均通过 | 未连接真实 Antigravity 或模型 |
| Git / 远端 | diff 空白检查通过；只读核对远端 main 仍等于基线；alpha.2 非 draft、prerelease | 最新运行 34964321255 的 7 个作业成功，但不覆盖候选 |

DSH 本轮可回读浏览器证据：
`output/native-mentions/dsh-browser-dGHgXq/dsh-browser-result.json`；同目录保留截图。
浏览器断言通过，本轮未逐图进行视觉审阅。

本轮性能观察：12,000 行全来源 50 行分页参考/当前约 76.82/1.69 ms，关键词页
88.74/4.81 ms；无界全量列表约 69.43/71.81 ms，不能声称所有查询都更快。
41.1 MB JSONL 峰值内存约 40.89/0.20 MiB；50,001 条 DSH 事件约
31.72/0.13 MiB；上下文渲染、候选历史、工具结果索引均与参考输出等价。

### 发布前仍需完成

1. 在明确授权后冻结提交范围，将必要的新文件纳入候选提交（特别是当前 CI 引用的
   Antigravity runtime/test）；运行该提交的 Linux/macOS/Windows、Python 3.11/3.14
   和 Node 22 CI。未跟踪文件不能遗漏，旧 CI 不能复用为候选证据。
2. 对拟宣称支持的真实宿主执行明确选择 → 附加 → 取消/发送边界 → 模型续做的
   验收；使用专门测试会话，真实模型调用、宿主安装/重启另行确认范围。
3. 针对最终提交重新构建保留的发布附件，核对版本、内容清单与 SHA-256；取得发布
   授权后才能打标签、上传和公开，再核对远端标签/附件。保持 GitHub prerelease
   范围，不发布 PyPI/npm。

本轮只整理验收/开发/发布文档，保留既有产品改动；没有安装或重载宿主、读取私人
会话、调用模型、提交、推送、打标签或发布。撤销本轮整理时仅反向应用对应文档段，
不要还原整个文件或工作区。旧程序对 schema v4 缓存的降级兼容未验证；如需回退程序，
应另用隔离 `--data-dir`，不要覆盖当前索引、源会话或宿主配置。

## 最新本地复核（2026-09-24）

- checkout：`main` / `1018072c89ce7e44bb4cc42ed1fe09cd7d5b9c9c`。工作区当前有多项
  已修改和未跟踪文件；没有提交、推送或发布，本记录不把整份脏工作区归属到单一轮次。
- Python：`.venv` 全量 unittest **247 项通过、1 项跳过**。
- Node：DSH / OpenCode 整合测试 **30 项通过**。
- 六来源 synthetic scale：`--sessions 3 --turns 3 --width 64` 全部完成；源哈希不变、
  最新证据保留，上下文未超过预算；没有调用模型。
- wheel：源码目录外安装通过，16 项资源哈希、CLI 与 MCP 合成流程通过；不代表真实宿主加载。
- DSH 300 sessions / 200 turns synthetic scale：warm refresh 约 92.2 ms，menu 95.2 ms；
  source hash unchanged、latest evidence retained、model not called。仅为本地 scale observation。
- 同一 2,000 会话 DSH JSONL fixture 交错比较 snapshot path guard：当前 canonical-root fast path
  warm refresh 中位数约 638 ms，逐文件 `resolve()` reference path 约 943 ms（各 5 次，均无 errors）。
- Antigravity metadata projection 用单条 SELECT 读取 trajectory/workspace/首条 user/末条 state；
  300 会话 synthetic warm refresh 约 150.5 ms，source hash unchanged。
- Antigravity metadata worker 并发数交错复测，输出顺序/metadata 等价、坏 DB 仍隔离：2,000 个 DB
  中 8/4 workers warm median 约 626/655 ms（高负载单机样本）；300 个 DB 中 8/4 workers
  约 92/96 ms。默认 worker 数从 4 调到 8，阈值仍为32个 trajectory；串行对照旧样本约993 ms。
- DSH 2,000 条 JSONL header metadata-only 读取对照：串行中位数约 637 ms，4/8 workers
  约 609/620 ms，输出等价；约 4.5% 的峰值收益不足以抵消额外线程/错误处理复杂度，故保持串行。
- 高规模本地 synthetic stress（2026-09-24）：
  - JSONL 2,500 × 16 KiB（41.1 MB）解析等价；list/stream 峰值内存 40.89/0.20 MiB。
  - DSH 50,001 事件（2.78 MB）终态等价；list/stream 解析 1,156/456 ms，峰值内存
    32.10/0.13 MiB。
  - context render 50,000 行、输出 1,200 条等价，334/1.13 ms，峰值 5.58/0.03 MiB；
    evidence history 50,000 记录、1,000 unique tasks 等价，171/38.65 ms，峰值
    9.28/0.12 MiB；tool-call lookup 5,000 次等价，412/2.23 ms。
  - 索引查询 12,000 行结果与全量参考等价：50 行全来源页 74.92/25.18 ms，关键词页
    83.60/41.73 ms，无匹配页 165.85/34.67 ms，均为 reference/current 中位数。合成数据
    共用空 cwd，basename 缓存上限 1024；以上不测真实来源刷新、UI 或模型。
- 本轮未查询远端 CI / Release，也未验证运行中的 DSH、Codex 或其他宿主 UI。

## 追加复核（2026-09-25）

- Python 全量 unittest 再跑：**245 项通过、1 项跳过**。
- Node DSH/OpenCode 整合测试再次通过 30 项；wheel 再次源码树外安装，16 项资源哈希、CLI、
  MCP 合成读取通过；两项均未调用模型，不代表宿主运行状态。
- 超过 20,000 行的 alias inventory 使用 4,096 行 batches；25,000 条合成 sessions
  预留 alias 用时：unique/repeated 标题约 251/233 ms。tracemalloc retained/peak 分别约
  0.95/15.28 MiB 和 0.57/14.02 MiB；全部 25,000 个 alias 均写入 SQLite。没有读取真实
  用户会话或调用模型。
- DSH 2,000 条 JSONL 下，试验通用 per-source metadata cache（含 title projection signature）
  warm median 约 1,729 ms，完整扫描约 653 ms；因此 DSH 继续全扫描，不启用该缓存路径。
- 12,000 行阈值对比（5 次、每次新临时库）：整批 inventory 中位数约 121.05 ms，强制
  4,096 行 streaming 约 125.91 ms；20,000 阈值保留整批快路径，较大库转流式。
- 已有 25,000 个 alias、整库标题变更为同一重复标题后，inventory 重建约 392.87 ms；旧 alias
  均保留，新 suffix 连续分配，验证了跨 batch cursor 在历史 alias 库中的行为。
- 单会话标题变化后，warm alias inventory 只重算该 ref 的显示 alias；测试确认不调用全量
  `sessions()` 重载，Codex JSONL fixture 使用转义内容以验证真实解析路径。
- 25,000 条 synthetic snapshot rows 中单行标题更新：refresh 标记 1 行变化、0 错误，
  alias 缓存仍 current 且新标题 alias 已分配，约 214 ms（包含全来源 snapshot metadata scan）。
- OpenCode 2,000 会话 synthetic 数据库变化后 refresh 的 cProfile 约 71 ms；旧 snapshot 行
  只做 1 次 agent 级预取，无逐 sourcePath SELECT，变更写入分为 4 个 512 行批次。25,000
  行全量 time_updated 改写后 refresh 0 errors、25,000 changed；tracemalloc 下约 1.80 s，
  peak 22.65 MiB（该探针同时改写了全部行，不代表单会话更新）。
- alias 表为空的 streamed inventory 跨 batch 碰到 `same`、`same_2`、`same` 时仍分配
  `same`、`same_2`、`same_3`，防止批次边界改变全局 suffix 所有权。
- 历史 suffix 中 `_2` 与 `_4` 已占用、`_3` 空缺时，后续 ref 仍优先取得 `_3`，cursor 不跳过空号。

## 2026-09-25 后续路径检查优化

- Snapshot canonical-root guard 复用一次相对路径分段，不再逐文件重新探测已 resolve 的
  root，也不再构造并比较整条 `Path.parents` 链；leaf symlink 与 root 内每层目录的
  symlink/junction 拒绝保持不变，system-alias fallback 未改。DSH 扫描将已发现文件对应的
  configured root 传入 guard，省去逐文件重新搜索 root。
- 同一 2,000 条 DSH synthetic JSONL warm refresh 的 cProfile 观察由约 1.164 s 降至
  0.908 s；`is_symlink` 调用由 10,000 降到 8,000，Path 内部 `next()` 调用由 6,000 降到
  4,000。profile 开销和 Windows 文件系统负载会影响绝对时间，这组数据仅用于定位，不构成
  稳定性能承诺。
- 后续 DSH 扫描改为深度限定的 non-following `os.scandir`，枚举时拒绝 linked project/session
  folders 与 linked leaves；只把已证明位于配置 root 内的 regular file 交给 metadata reader，
  跳过逐文件 lstat 整个祖先链。link/scan-error sentinel 会触发 scan error，旧索引行保留。
  2,000 会话、3 turns、64 字符 synthetic warm refresh：JSONL/Zstandard 约 470/546 ms；源哈希未变。
- 后续将每条路径上的 `is_symlink()` 与 `is_junction()` 双重系统探测合并为一次 `lstat`，
  仍按 `S_ISLNK` 和 Windows mount-point reparse tag 拒绝符号链接/junction。1,000 个嵌套
  synthetic 路径交错 8 轮、丢弃前 2 轮后，路径 guard 中位数约 117.04 → 90.37 ms；
  该局部微基准不等于完整刷新收益。
- 1,000 条 synthetic 交错复测有明显环境抖动：旧路径三次样本约 3,737 / 2,668 / 447 ms，
  新路径约 353 / 318 / 329 ms；结果没有作为严谨的延迟承诺。DSH 2,000 条 profile 刷新
  `errors=[]`、`changed=0`。`test_extra_agents.py` 16 项通过、1 项跳过，额外覆盖文件符号链接拒绝。
- 六来源 300 会话、100 turns、128 字符 synthetic scale 全部通过：source hash 不变、最新
  evidence 保留、context 未超限、未调用模型。schema version 4、Grok cache 启用后的复跑
  warm refresh：Claude/Codex 4.0/4.2 ms，Grok 50.5 ms，OpenCode 1.0 ms，Antigravity 97.7 ms，
  DSH JSONL/Zstandard 67.3/103.7 ms。Antigravity 默认 metadata workers 调至 8；300 条对照中
  8/4 workers 约 92/96 ms。单次本机 observation 用于横向热点筛查；不能把来源间
  耗时差异归因于单一文件系统操作。
- Grok summary cache 默认启用，validity 用每 source 一次有序 sourcePath inventory 和内存二分区间
  匹配。300 个 synthetic sessions warm refresh scan/cache 约 51.1/36.1 ms；2,000 个会话约
  480.9/480.1 ms，结果一致。最新 300 会话交错复测 scan/cache 中位约 51.3/48.8 ms；summary 修改
  会重读、新增路径读取、删除路径清理旧索引，均有回归覆盖。
- DSH cache 在 sourcePath 检查批量化后重测仍未获益：2,000 条 warm refresh，JSONL 全扫/cache
  中位约 876.6/1,074.0 ms，Zstandard 约 1,000.4/1,096.4 ms，源哈希不变。DSH 保持默认全扫；
  session projection signature 仍有定向回归，避免将来显式启用时复用过期 title。
- DSH discovery 在 2,000 条 JSONL warm refresh 的 cProfile 约 0.59 s；2,000 会话、3 turns
  synthetic scale JSONL/Zstandard warm 约 470/546 ms，source hash 不变；链接目录拒绝及旧索引保留回归通过。
- 最终 Python 全量 unittest **258 项通过、2 项跳过**；DSH/OpenCode Node 整合测试 **30 项通过**；
  wheel 源码树外构建/安装、16 项资源哈希、CLI 和 MCP 合成读取通过；`git diff --check` 通过。
  没有 real-host、模型、CI 或发布验收。
- 另评估将无界全量 `sessions()` 的 Python 最终排序改为 SQLite 排序。12,000 行 synthetic
  在 6 次交错样本（先丢弃 2 次）中结果完全一致，但 Python 路径中位数约 61.95 ms，SQLite
  路径约 64.46 ms；因此不采用这项会让完整列表稍慢的改动。当前 profile 的 fetch/dict 和排序
  成本均属于必须返回全部行时的主要成本，分页接口仍使用 SQLite `LIMIT/OFFSET`。
- 为有界列表页和关键词页评估并升级 `sessions_agent` 索引：12,000 行合成数据的跨来源列表页
  约 24.84 → 1.69 ms，关键词页 38.28 → 14.70 ms；按单一来源关键词页 6.65 → 1.17 ms。
  `check_index_query.py` 在 version 4 独立复跑也确认全来源列表分页 74.91 → 1.70 ms、关键词页
  84.59 → 4.78 ms、无匹配页 140.08 → 41.32 ms、精确总数关键词页 146.77 → 45.62 ms。
  结果与原路径相同；`EXPLAIN QUERY PLAN`
  确认单来源分页去掉临时排序。索引 DB 文件约 +15%，1,000 次更新时间从约 7.30 增至 13.02 ms
  （绝对增量约 6 ms）。Index version 3 在事务中替换旧索引；version 4 增加 `sessionId` 单列索引。
  50,000 行 exact-miss existence probe 从旧 OR scan 约 37.815 ms 降到 indexed `UNION ALL` 约
  0.003 ms；`EXPLAIN QUERY PLAN` 不再建 OR/UNION 临时 B-tree，ref 使用主键、sessionId 使用单列索引。
  仅 sessionId 索引的临时 DB 比 v3 基线大约 1.07 MiB，1,000 次 sessionId 更新约 40.8 ms，
  无该索引约 29.6 ms。migration/self-heal 回归和 EXPLAIN 索引计划通过。全量 Python **254/1 skip**、Node **30**、
  wheel/CLI/MCP 合成流程均通过；不代表真实来源刷新、宿主、模型、CI 或发布验收。
- 接着优化多来源精确总数关键词页：先在同一只读 SQLite snapshot 计数，再按每个 source
  的 `(offset + limit)` top-K 取候选并合并排序，单来源仍用复合索引直接分页。12,000 行
  synthetic 查询参考/当前约 140.91/61.40 ms；先前单条 `COUNT(*) OVER()` 路径约 115.88 ms。
  页内容、总数、空结果、跨来源 ties 和 offset 与参考一致；迁移查询定向测试通过。source refresh
  未包含在该 probe。
- 50,000 行 synthetic 索引复测，所有返回行均与 reference 一致：全来源页 480.47/2.04 ms，
  关键词页 596.30/92.50 ms，无匹配关键词页 758.50/261.04 ms，精确总数关键词页 592.25/214.75 ms
  （reference/current）。全量 sessions 仍由 Python 排序快于 SQLite：382.9/441.8 ms。数据仅是
  临时合成库，不测真实来源刷新或宿主。
- FTS5 `detail=none` trigram prototype uses Python-casefolded query trigrams joined by AND; exact
  matching removes cross-field false positives. Samples cover `ß`, Kelvin, accents, emoji, NUL,
  whitespace and quotes. Integrated 50,000-row temp index build took about 214 ms and 1,358 temp pages
  (5.30 MiB); no persistent index files or conversation bodies are added.
- 将该原型接为只在大索引重复 keyword query 后创建的 connection-local FTS5 表：门槛为 20,000
  sessions；重复同一稀疏查询两次后可提前激活，未重复的查询组合仍需至少 8 次合格分页请求和
  2 次稀疏结果。`Index.refresh()` 仅当 ref/agent/sessionId/
  title/cwd 或会话集合变化时标脏，activity-only 元数据更新保留 FTS；其他 Index 连接提交后按
  `PRAGMA data_version` 失效。每次先做有界候选数
  探测，候选过多时退回复合索引路径，并在进程内缓存最多 128 个 dense query 判定，避免重复探测。
  高命中查询不会触发索引构建。FTS 候选对 query 长度不足 3
  或含 NUL 时不启用；非空 derived-title cache 和动态 Codex 标题走原来的精确 fallback。
- 50,000 行 casefold 交错对照（各 4 个计时样本，先各丢弃 2 次；schema version 4、临时 FTS 已构建）：
  无匹配 total query 约 90.1 → 0.6 ms，选择性 `Synthetic title 123` 约 104.4 → 16.8 ms；
  高命中 `Synthetic title` 约 144.4 → 159.1 ms，密集路径保留 exact fallback，首次候选探测仍有少量
  开销。内容和总数均与 fallback 相同。
  原默认阈值下，50,000 行连续无匹配序列第 10 次调用构建约 326 ms，之后 0.5–0.6 ms；
  后续按相同 sparse query 的重复情况调整触发路径，见 2026-09-25 记录。收益面向同一长寿命
  Index 进程中的重复搜索，不适用于一次性 CLI 搜索的建索引方式。
- `check_index_query.py --rows 50000 --repeats 5` 在默认策略下仍与 reference 等价：无匹配页
  750.27/289.97 ms，精确总数页 676.78/236.36 ms（reference/current）；测量包含本轮延迟的
  临时索引构建。600 行全匹配回归 12 次查询均确认不构建 FTS。
- 扩至 100,000 行（3 个 repeats）仍与 reference 等价：跨来源有界页 993.59/2.92 ms、关键词页
  1,242.19/8.56 ms、无匹配页 1,551.80/283.31 ms、精确总数关键词页 1,257.47/300.43 ms
  （reference/current）。独立 100,000 行无匹配序列显示第 10 次调用触发 FTS 构建约 820 ms，之后
  三次约 2 ms；构建仅在重复稀疏搜索后发生。
- 100,000 行无界全量 sessions 的 Python/SQLite 排序交错对照，行顺序与 overlay 结果完全一致；
  丢弃前两轮后中位数约 948.5/939.9 ms，但 SQLite 出现过约 6.6 s 的冷样本，稳态差异不足 1%。
  暂不引入按库大小切换的第二条排序路径。
- FTS 回归覆盖 casefold/引号、cwd basename、session-ID prefix、Codex overlay、derived-title、
  same-connection REPLACE/UPDATE 和另一 Index 实例写入后的 data-version 重建；活动记录追加且搜索
  字段不变时，索引行 rowid 更换仍保持 FTS ref join 有效。matcher 使用连接级 dispatcher；50,000
  行无匹配 FTS query 现在正常完成，不再在 callback 注销时抛 `Error creating function`。
- Unicode casefold trigram property check 覆盖 500 条合成文本、2,819 个真子串候选，0 false negatives。
  最终 Python unittest **258 项通过、2 项跳过**，Node **30 项通过**，六来源 scale 与源码树外 wheel/CLI/MCP
  合成读取通过。没有真实宿主、模型、CI 或发布验收。
- 六来源 scale 与 wheel 并行运行时，DSH Zstandard 单次出现约 1.46/1.87 s 的 refresh 抖动；
  随后单独复跑两次约 112/114 ms cold、114/106 ms warm，source hashes 均不变。该孤立高值
  归为并行磁盘负载异常，不据此改 DSH 路径。
- schema version 4 后的另一次 scale + wheel 并行运行中，DSH Zstandard 又出现约 183/737 ms
  cold/warm 和 1.19 s menu outlier；两次 isolated recheck 回到约 110/115 和 102/102 ms，
  source hashes 不变。继续按并行磁盘争用记录，不作为代码回归。
- 初版 per-row FTS refresh trigger 对 50,000 行临时库的 1,000/5,000 条替换写入明显变慢，
  因此移除；改由 `Index.refresh()` 在提交后一次性失效 FTS，避免每行 token 重建。activity-only
  更新仍复用 FTS；查询状态测试覆盖了新增会话/标题变更时的准确回退。
- 同一 50,000 行库的 1,000/5,000 条替换写入对照（FTS 已构建）：plain/FTS 写入中位约
  38.2/38.8 ms 和 147.3/120.6 ms。该 probe 在 FTS 情况下测到提交后 dirty 标记；下一次符合条件
  的搜索会丢弃旧 FTS 并走精确 fallback，索引重建成本不计入这组写入计时。
- FTS 50,000 行构建实现对照（各 5 次，含 3 个 casefold 字段）：Python 分批写入中位约
  271.9 ms，SQLite `INSERT ... SELECT` 加 casefold UDF 约 270.4 ms；行数与 trigram 命中数相同，
  差异不足 1%，保留现有分批实现。
- FTS 已建好时，50,000 行高命中 query 对照 dense-query decision cache：6 个交错样本中位约
  131.93 → 128.32 ms；缓存只保留至多 128 个 process-local query/source 组合，实际收益约 3.6 ms。

## 2026-09-25 后续性能候选复核

- 六来源 synthetic scale 以 300 sessions、200 turns、1,024 字符复跑：Claude/Codex/Grok/OpenCode/
  Antigravity/DSH JSONL/DSH Zstandard warm refresh 分别约 3.9/4.1/50.1/1.0/104.7/66.3/73.9 ms；
  所有 source hash 不变、最新 evidence 保留、context 未超限，未调用模型。结果是单次本机观察，
  不是跨机器延迟保证。
- Antigravity 2,000 个合成 DB 并发对照（每配置 4 次、丢弃首轮，metadata 完全相同）：4/8/16/32
  workers 中位数约 628/585/638/616 ms。8 workers 仍为本轮最佳；样本存在明显磁盘抖动，未调整默认值。
- Antigravity 调度候选复核后将大清单任务按最多 8 个 DB 分组。2,000 个合成 DB 的 Index warm refresh
  交错 5 次，未分组/分组中位数约 631/587 ms；各轮 0 errors、0 changed，2,000 个候选和 metadata
  顺序相同。255 个有效 DB 加 1 个坏 DB（坏库与有效库处于同一批次）的回归确认分组仍保持路径顺序、
  逐库错误隔离和源文件只读。
  该收益来自当前本机的合成数据库工作负载，不代表真实 Antigravity 库的延迟保证。
- Antigravity 分组扫描实现阶段的完整本地回归：Python unittest **258 项通过、2 项跳过**，
  DSH/OpenCode Node **23 项通过**。
  Antigravity 300 sessions / 200 turns / 1,024 字符 synthetic scale warm refresh 约 78.7 ms，0 errors，
  source hash unchanged、latest evidence retained；未调用模型。真实宿主、模型、CI 和发布仍未验证。
- `BaseAdapter.message()` 长 assistant 文本复用模块级 plan-marker regex。50,000 行 synthetic 消息、9 次
  交错测量且输出完全相同：无命中中位数由约 72.8 ms 降至 61.8 ms（约 15%）；稀疏命中也相同，
  但受任务对象分配与机器抖动影响，耗时样本更分散。新增回归覆盖大小写及中英文标记、仅 assistant
  提取的既有语义。更新后 Python 全量 unittest **259 项通过、2 项跳过**。
- 长 ASCII assistant 消息的全行 marker 预检候选没有改善：4 MiB 单行无命中约 136 ms（现有约 134），
  含 marker 单行约 96 ms（现有约 92），4 MiB 多行约 284 ms（现有约 255），峰值内存相同。保留
  当前逐行 split 与 compiled marker 扫描。
- 空查询（菜单列出最近会话）现在跳过逐行 keyword-match UDF，改用现有索引分页及同一只读快照中的
  精确总数查询。50,000 行 synthetic、六来源、limit=100：旧路径约 206 ms，新路径约 7.6 ms；结果页及
  total 完全等价，所有 benchmark 连接在返回后均无残留 transaction。新增回归覆盖多来源排序、总数、
  空 session ID 的 exact-match 优先级。更新后 Python 全量 unittest **260 项通过、2 项跳过**，
  DSH/OpenCode Node **23 项通过**。
- FTS5 触发器现在记录最多 128 个 sparse `(source set, query)` 组合：同一组合连续两次稀疏命中后，
  将构建挂到该查询下次执行，其他一次性 query 不会触发这条提前路径。50,000 行重复无匹配序列
  （12 次）由原默认路径约 2.31 s 降至约 0.67 s，第三次执行构建后后续查询约 0.5–0.7 ms；三条
  不同稀疏标题查询后接高命中查询没有构建 FTS，避免了把索引构建成本转嫁给不同的 dense query。
  两组候选结果和总数均与扫描参考一致，数据仅来自临时合成索引。实现后的 Python 全量 unittest
  **261 项通过、2 项跳过**，DSH/OpenCode Node **23 项通过**。
- Antigravity 2,000 DB cProfile（分批线程扫描后）中 protobuf `fields()` 共 13,999 次、累计约
  127 ms；单字节 varint 快路径与旧解码器对 10,000 个随机值及截断/超长输入错误等价，但 6 次
  2,000 DB warm-refresh 中位数仅由约 582.8 降至 578.7 ms（不足 1%，样本有抖动）。因此不改 wire
  parser；完整刷新仍以 SQLite/文件读取和线程等待为主，需找到更大的端到端收益再触碰解码路径。
- `BaseAdapter.message()` 长文本按行流式扫描候选均与 `str.splitlines()` 结果相同；compiled-boundary
  regex 在 50,000 / 100,000 行无命中文本约 115/340 ms，旧路径约 80/250 ms，虽将临时峰值从
  4.3/8.5 MiB 降至近零，但显著变慢。`StringIO` 迭代也更慢且峰值更高（50,000 行约 7.8 MiB）；
  保留当前 compiled-marker + `splitlines()` 实现。
- 当前解析路径下重跑六来源 300 sessions / 200 turns / 1,024 字符 synthetic scale：全部通过，源哈希
  不变、最新 evidence 保留、未调用模型。DSH JSONL warm refresh 约 75.8 ms；Zstandard 隔离复跑三次
  约 85.6/78.0/72.0 ms（中位 78.0 ms），并行 scale 中的 99 ms 样本没有重复。
- 全量 `Index.sessions()` 的 50,000 行临时索引 cProfile 为约 331 ms：SQLite `fetchall` 约 130 ms，
  Python 行结果装配及函数自身约 104 ms，最终排序约 72 ms，metadata overlay 约 25 ms。完整列表
  必须返回全部结果；排序路径已在 12,000–100,000 行与 SQLite 排序对照，当前实现总体持平或更快，
  因而没有找到新的稳健端到端收益。该 profile 有 profiler 开销，且合成行与 overlay 分布有限，
  仅作热点筛查，不代表真实来源或宿主延迟。
- DSH 50,001 条 passive event / 2.78 MB 合成会话的 selected-session cProfile 约 266 ms；
  JSONL envelope 解码约 102 ms（其中 `raw_decode` 约 37 ms），其余主要在会话解析循环。重复 header
  读取、边界检查和文件打开均低于 profile 的 1 ms 显示精度；JSON 解码已有复用 decoder 快路径，
  先前交错基准中直接 `json.loads(bytes)` 更慢，因此本次未发现值得增加解析器或状态复杂度的改动。
  该输入只含 passive events，且 profile 带测量开销，不代表消息密集会话或真实 DSH 宿主延迟。
- JSONL decode 候选在 250,000 行、约 19.4 MB synthetic 文件上的真实 `scan_jsonl()` 循环未获益：
  `utf-8-sig` 参考中位数约 1,519 ms，逐行检查 BOM 后 `utf-8` 解码约 1,551 ms。保留现有 decoder；
  测试额外覆盖非首行 BOM，确认旧兼容语义。
- `scan_jsonl()` 现在用 `remaining` 字节计数跟踪打开时记录的文件末尾，去掉热循环里的 `tell()`。
  250,000 条、约 17.9 MB synthetic JSONL 交错 7 次：旧 tell-loop / 新 cursor-loop 中位数约
  1,876 / 953 ms。记录数、offset 和 warnings 等价；新回归覆盖超长行跳过、半条尾记录和 offset 超过
  当前文件长度。环境样本有抖动，此值为本机合成读取，不代表真实会话库延迟。更新后的 Python
  全量 unittest **262 项通过、2 项跳过**，DSH/OpenCode Node **23 项通过**；六来源各 30 sessions /
  40 turns synthetic scale 通过，source hashes unchanged、latest evidence retained、model not called。
- DSH compact JSONL records now use a reusable `JSONDecoder.raw_decode` fast path. On 50,001 events / 2.78 MB,
  seven interleaved reads returned identical `SessionIR`: direct `json.loads(bytes)` median about 132.1 ms,
  fast path about 84.8 ms. BOM, CRLF, and spaced lines still take the compatibility fallback; DSH tests cover
  BOM/CRLF and spaced records. Data are synthetic and do not measure a live DSH host.
- DSH event-envelope validation now reads the `data` map once and reuses the local reference. An 11-round
  50,000-event dictionary-loop probe fell from 13.12 to 10.96 ms with identical results; the full reader's
  nine local 50,001-event samples had an 80.5 ms median after the change. The whole-reader value is a local
  observation, not a paired baseline.
- DSH event-kind membership now reuses module-level `frozenset`s. On the same 50,001-event synthetic fixture,
  11 interleaved full reads with tuple/set configurations produced identical `SessionIR`; median fell from
  83.3 to 80.4 ms (about 3.5%). After the decoder/event-loop changes, Python unittest **263 passed, 2 skipped**;
  DSH/OpenCode Node **23 passed**.
- DSH surface storage now retains `(seq, type, data)` tuples instead of whole message-event dictionaries.
  On 20,001 events / 20,000 visible messages, seven paired runs preserved identical `SessionIR`; median
  read time fell from 174.2 to 155.8 ms, and tracemalloc peak from 34.33 to 28.65 MiB. Existing compaction,
  tool-result, and read-only tests cover the dependent semantics; all rows are synthetic. Current full tests:
  Python **263 passed, 2 skipped** and DSH/OpenCode Node **23 passed**.
- Sorted DSH surface histories now locate compaction endpoints with `bisect`; if a middle replacement breaks
  sequence ordering, later lookups retain the linear fallback. On 58,082 synthetic events with 80 tail
  compactions, paired reads had identical `SessionIR`; median fell from 340.4 to 191.4 ms. The regression suite
  includes two non-tail replacements to exercise fallback ordering. Latest full local validation: Python
  **265 passed, 2 skipped**, DSH/OpenCode Node **23 passed**.
- Pending DSH tool-call storage now keeps only `(seq, name, arguments)` for each call ID. On 20,000 pending
  calls, seven paired reads preserved identical `SessionIR`; median fell from 133.6 to 108.6 ms and peak
  memory from 24.42 to 18.47 MiB. A regression confirms duplicate call IDs continue to use the latest payload.
  After the DSH storage changes, Python full unittest **264 passed, 2 skipped** and DSH/OpenCode Node **23 passed**.
- Large `build_context()` histories now share evidence lists for unannotated records during internal read-only
  reconciliation, while still copying lists before adding `supersededBy`; public history helpers retain their
  independent-copy default. A 25,000 command + 25,000 file-operation + 25,000 tool-call synthetic context had
  identical output: median fell from 153.1 to 117.5 ms and peak from 26.06 to 24.24 MiB. Latest full local
  regression: Python **268 passed, 2 skipped**, DSH/OpenCode Node **23 passed**.
- When `build_context()` has no workspace root, file-operation history now avoids per-entry file-inspection
  setup and directly records the same UNCERTAIN evidence. A 25,000 file-operation / command synthetic context
  had identical rendered output in nine interleaved runs; median fell from about 100.3 to 94.2 ms. Local-only.
- A paired reconciliation probe on 25,000 file operations + commands compared the previous `inspect_operation(None, …)`
  call path against inline UNCERTAIN-record construction. Rendered output was identical; `build_context()` median
  fell from about 121.3 to 93.3 ms over nine interleaved runs. After the change, Python full unittest
  **268 passed, 2 skipped** and DSH/OpenCode Node **23 passed**.
- Represented evidence is now built from `chain(work, superseded)`, avoiding a concatenated temporary list. A
  paired 25,000 file-operation + 25,000 command `build_context()` probe rendered identical output; median fell
  from 113.7 to 90.3 ms over nine interleaved runs. Current Python full tests: **268 passed, 2 skipped**;
  DSH/OpenCode Node: **23 passed**.
- Continuation ranking uses packed integer `(priority, recency)` keys for sized work lists, with the tuple rank
  retained for iterators. Synthetic 100,000 unique tasks produced identical candidates; time/peak moved from
  about 45.8 ms / 6.63 MiB to 34.6 ms / 4.08 MiB. A 50,000-row, 1,000-unique case showed little change.
  `check_evidence_history.py --records 50000 --unique-tasks 1000` matched the full-sort reference; current
  top-12 ranking took 33.4 ms / 0.06 MiB versus reference 151.5 ms / 9.28 MiB. Python full unittest
  **268 passed, 2 skipped** and DSH/OpenCode Node **23 passed**.
  Latest full regression: Python **268 passed, 2 skipped** and DSH/OpenCode Node **23 passed**.
- For 20,000 pending DSH `read_file` calls, the base `finish()` loop's file-operation/hook handling was
  simplified; a 13-round equivalence probe fell from 23.8 to 18.0 ms median with identical session output.
- For 20,000 DSH shell calls with `echo value` commands, compiling test-run detection and reusing the
  stringified command lowered seven interleaved full-read medians from 111.2 to 95.3 ms with identical output.
  After this change, Python unittest **266 passed, 2 skipped** and DSH/OpenCode Node **23 passed**.
- For 20,000 completed shell calls with exit-code text, compiled exit-code/file-success matchers preserved
  `SessionIR`; a seven-round finish-loop probe measured about 95.8 ms inline versus 89.6 ms compiled. Samples
  were noisy, so this is a small local microbenchmark gain rather than an end-to-end guarantee. Latest full
  validation after `finish()` changes: Python **267 passed, 2 skipped** and DSH/OpenCode Node **23 passed**.
- Grok's 50,000 same-role message chunks were also probed with direct dictionary-text extraction versus
  `text_content()`: `SessionIR` matched, but medians were only about 191.6 versus 195.0 ms amid large outliers.
  The small/non-repeatable gain did not justify source-specific chunk handling.
- JSONL 的 direct-bytes decoder 与首字节空行预检未在完整扫描中稳定获益：250,000 行 UTF-8/BOM 文件
  上条件 UTF-8 decode 约 1,551 ms、现有 decoder 约 1,519 ms；200,000 行空行混合文件上首字节分支
  中位数约 674 ms、`strip()` 参考约 659 ms。保留现有严格 UTF-8 decoder 与空白检测。
- `handoff.recent_decisions` 的 256 KiB 以上候选对照保持等价。对 2 MB 无命中单行和 100,000 行无命中
  文本，逐行拆分约 55/77 ms，combined regex 约 99/117 ms；但逐行拆分峰值临时内存约 6.7 MiB，
  regex 低于 0.01 MiB。加入“先检查命中”的双遍扫描虽把无命中样本降至约 61/76 ms，却让 100,000
  行稀疏命中样本从约 164 ms 增至 289 ms。保留现有 regex 的限内存分支和 256 KiB 阈值，不采纳
  在实际消息分布未知时会令命中样本回退的预检路径；目前该区域无稳健的通用替换收益。

## 2026-09-26 集成菜单分页优化与发布候选复核

- OpenCode TUI 与可选 Antigravity 菜单在打开选择器时把 `@agent:keyword` 查询交给本地索引，
  最多取 51 条作为分页提示，只展示前 50 条；点选后按精确 ref 重新验证。旧版 CLI 不识别
  `--query` / `--limit` 时回退原来的全列表调用。
- Python 3.14.6 与 3.11.15 全量回归均为 **共 268 项，266 项通过、2 项跳过**；本机 Node 24.18 的
  DSH、OpenCode、Antigravity broker 回归 **38 项通过**。Antigravity 使用合成页面与本地 CDP
  的浏览器测试通过；实际 Antigravity UI 和模型未测试。
- 六来源合成规模检查通过。12,000 行索引查询结果与参考一致；50 行页只装配 50 个 Python 行对象，
  来源过滤只装配 2,000 行而不是 12,000 行。41.1 MB JSONL 峰值内存约 40.92 → 0.20 MiB；
  50,001 条 DSH 事件约 31.74 → 0.13 MiB；50,000 条有界上下文渲染约 329.56 → 1.05 ms；
  50,000 条续接候选排序约 152.47 → 32.94 ms；5,000 次工具结果匹配约 403.75 → 2.12 ms。
  均为本地合成对照，不是用户会话或稳定性能保证。
- 12,000 行索引分页对照中，50 行全来源页约 77.96 → 1.71 ms，关键词页约 86.63 → 4.91 ms，
  结果及顺序一致。这是索引级合成基准，不含 Node 子进程启动、来源刷新或真实宿主 UI 延迟。
- 源码树外 wheel 安装、16 项资源哈希、安装后 CLI 与 MCP 合成读取通过；wheel 仍标为
  `0.1.0a3`，Python 3.14.6 与 3.11.15 均通过。DSH 构建后 `lib/` 两个产物 SHA-256
  与构建前一致，确认源码和生成文件同步。Node CI 已加 Antigravity 语法及 broker 测试，但远端
  Actions 尚未运行；本地结果不包含真实宿主加载或真实模型续做验收。

## 历史快照（2026-09-17）

## 版本与证据边界

- 基线：`main` / `1018072c89ce7e44bb4cc42ed1fe09cd7d5b9c9c`，对应
  `v0.1.0-alpha.2`；本轮开始时工作区干净。
- 该提交之后的未提交本地修复包括：DSH 元数据大小限制、索引警告传递、菜单提示、
  安装预览、真实来源验收脚本、Codex 新增文件事件适配及回归测试。
  DSH `src/` 与分发用 `lib/` 同步构建。
- DSH 修复阶段没有调用模型；其后经用户明确授权，尝试了一次真实 Codex 来源生成，
  结果及配置漂移见下节。随后本地修复阶段没有再调用模型、启动代理、安装插件、
  修改凭据/路由/ACL 或放宽沙箱。没有提交、推送或发布。
- 已有链接安装是否加载新文件尚未验证；不能声称真实宿主已应用本轮修复。
- 本地合成通过、浏览器合成通过、真实宿主交互、真实模型完成任务是四种不同证据。

## 2026-09-17 证据表

| 层级 | 最近验证结果（未注明者为 2026-09-16） | 不代表什么 |
| --- | --- | --- |
| Python 单元及合成集成 | 09-17：199 项，198 通过、1 项目录符号链接能力跳过；较 167 项基线新增 14 项验收脚本、3 项安装预览、15 项 Codex 事件测试 | 不代表本机跳过分支通过；测试未调用真实模型 |
| DSH / OpenCode Node 测试 | 09-17：29 项全部通过：DSH 22、OpenCode 7 | 模拟宿主不是实际宿主 |
| 大列表子进程传输 | 1,000 条合成元数据跨真实 Node 子进程；列表只显示 50 条，仍可检索并选中第 1,000 条 | 不代表任意大小列表可用 |
| 超限与恢复 | 元数据超过 8 MiB 明确失败，随后重试成功；正文超过 256 KiB 仍拒绝 | 尚未实现 CLI 分页 |
| 警告传递 | 成功 CLI 的 stderr 转为保守 `incomplete` 标志；正常刷新清除；成功响应不暴露原始 stderr | 不是详细错误分类或警告计数 |
| DSH 语法及构建 | 源码语法检查、构建通过 | 未确认正在运行的 DSH 已加载 |
| Chromium 合成页面 | 编译后的客户端通过六来源浏览、警告/空结果、取消、选中及后续合成发送；无页面异常 | 不是已认证 DSH 完整应用或真实模型 |
| 合成双向 demo | 09-17：Claude/Codex 通过，源哈希未变 | 不是真实双向模型续做 |
| 六来源七场景规模检查 | 09-17：每场景 30 会话、100 条长消息、宽度 2048；源哈希未变、最新证据保留、上下文未超 32,000 字符 | 不代表真实大库或长任务质量 |
| alpha.2 远端 CI | 09-16 查询：基线提交的 7 个作业均 success | 不覆盖本轮未提交修复 |
| alpha.2 Release | 09-16 查询：公开 prerelease，非 draft，目标提交等于基线 | 本轮未重新下载附件校验哈希 |
| 本轮 wheel | 09-17：隔离构建并在源码目录外安装，通过 CLI、doctor、MCP 及 16 项资源哈希核验 | 合成数据包验证，不是实际宿主安装 |
| 本轮跨平台 CI | 未提交或触发新 CI | 不能沿用基线 CI 为本轮背书 |
| 真实来源验收脚本 | 默认仅预览；显式 `--allow-live`；保留配置路由；标记、AST、保护文件及子进程清理测试通过 | 源阶段通过也不等于双向接续完成 |
| DSH 安装入口 | 默认预览无副作用；只有 `--apply` 才执行安装逻辑 | 未执行真实安装；尚无事务回退 |
| Codex 新增文件事件 | 09-17：合成回归及先前自有真实来源副本重读通过；警告 1 → 0，提取到 1 项精确哈希文件操作，副本哈希未变 | 仅已确认 add 格式；不是整库格式兼容性或模型续做验收 |

远端证据：[固定运行记录](https://github.com/jiezeng2004-design/agentref/actions/runs/34964321255)、
[alpha.2 Release](https://github.com/jiezeng2004-design/agentref/releases/tag/v0.1.0-alpha.2)。
这些是查询日状态，不是持续监控。

本轮忽略目录中的浏览器证据：`output/native-mentions/dsh-browser-jUn54X/`，
包含 `dsh-browser-result.json`、有候选与无候选的警告截图及键盘菜单截图。
结果记录六来源、一次明确读取、一次后续合成提交、零页面异常、未调用模型。
两张警告截图已人工式逐图检查：文字可读、候选未被遮挡。
重跑 `scripts/check_dsh_mentions_browser.cjs` 会创建新的独立目录，不覆盖旧证据。

## 当前宿主验收缺口

| 路径 | 已有历史证据 | 当前版本待验证 |
| --- | --- | --- |
| Claude → Codex / Codex → Claude | 2026-09-06 小任务真实双向续做；其中一个接收端是当时当前任务 | 原生选择 → 附加 → 发送 → 独立接收端实现 → 最终测试完整链路 |
| Codex / Claude 菜单 | 历史截图、CLI 菜单与 app-server 协议证据 | 当前宿主版本的选中、上下文消费；统一入口连续 Tab 也不能由协议成功推定 |
| OpenCode TUI | 2026-09-13 真实可执行程序、隔离合成会话的交互验证 | 真实来源和实际模型提交续做 |
| DSH Web | 本轮编译客户端的 Chromium 合成页面 | 已认证完整 DSH 应用、加载本轮构建及真实模型续做 |
| Grok / Antigravity | 发送后编号选择回退、历史元数据/协议检查 | 实际续做；不宣称原生发送前菜单支持 |

## 2026-09-16 真实来源尝试与本地修复

经用户允许使用现有模型配置，在一次性项目启动了 Codex CLI 0.147.0。
模型实际生成 register 与未实现的 rollback；独立验证 register 通过，另外两项
测试因 NotImplementedError 失败，符合阶段一代码状态，但并非最终任务通过。
暂停命令创建标记时 PermissionError；模型自行停止，未被受控中断。
进程 exit 0 不算验收通过。未提权，也没有通过修改权限重试。

AgentRef 对本次确切自有会话的字节一致快照完成 in-process MCP resources/read，
得到 9,372 字符上下文；原始来源、测试文件和生成代码在核验过程中哈希未变。
这证明真实来源读取，不证明已安装宿主附加或接收模型续做。
CLI/provider/配置状态并非当前所有宿主均已验证。

Claude Code 2.1.261 的原生登录状态为未登录；`ocx claude config status` 报告代理
未运行。安装入口代码显示 `ocx claude` 可能启动代理并同步模型缓存与 Agent 定义，
故未执行；没有改登录、凭据、路由或重启宿主。Claude 来源和接收端均未调用。
历史余额或模型路由失败未重新验证，不作为当前阻断原因。

测试窗口内 Codex config.toml 哈希变化，Claude settings.json 哈希未变。
没有调用配置写入命令，但没有旧内容快照，无法归因或复原具体改动。
复查的模型/provider/sandbox 值未变，不代表整个配置未变；不覆盖旧配置。
检测漂移后暂停模型调用，后续仅执行本地合成检查。

本地诊断：测试目录和代码文件无只读属性；ACL 与普通仓库目录不同。本进程的
合成子进程写入通过，无法代表被测 Codex 子进程的权限令牌，故尚不能归因到
某条 ACL 或断言权限问题已修复。没有修改 ACL、系统设置或沙箱。
读取的是本次确切来源副本，未扫描其他私人正文；一项索引警告定位为
`event_msg:patch_apply_end`。此事件包含代码修改证据，不能简单忽略来消除警告；
需后续为重复事件、工具关联、失败状态和格式变体定义适配及合成回归。

旧 live_demo 的可本地修复问题已处理：移除忽略 Codex 用户配置的启动选项、默认
预览并要求 `--allow-live`、用每次独立标记确认暂停、AST 核对约定阶段代码、
保护测试和暂停助手哈希、超时/异常时仅清理自有进程、失败返回非零。
不再根据日志字符串里的 401/403 或用户提示词猜测认证失败。新增测试只用合成
Python 子进程，无真实宿主、模型或代理调用。脚本仍只是来源阶段工具，不是
完整双向续做验证器，也没有修复宿主权限问题。

本地原始证据在忽略目录 `demo-artifacts/live-acceptance-20260916/`，
包括独立验收说明和 `codex-source-8nxhkpai/partial-verification.json`。
旧测试结果、原始日志及来源副本保留不变，不提交或公开。

## 2026-09-17 Codex 事件适配

上节记录的 `patch_apply_end` 缺口现已做有界修复，而不是忽略该事件：已确认的
add 类型转换为文件操作、历史完成/失败状态及精确 UTF-8 内容哈希。完全重复事件
只计一次；与直接工具结果吻合时合并来源证据且保留原始顺序；状态或哈希矛盾时
保持不确定，不用于成功覆盖历史。未知 update/delete、畸形字段等继续给出警告。
不解释或执行 `exec` 中的 JavaScript，不把结束事件当作整个任务完成。

重读仅限前述自有测试会话副本，使用临时隔离索引：刷新/解析警告均为零，提取到
1 项新增文件操作，上下文为 9,586 字符，副本哈希未变。旧证据文件未重写，
也没有扫描个人其他会话、启动模型或修改宿主配置。

AgentRef 自有索引版本从 1 升至 2：只将先前有警告的 Codex 行标为待重新扫描；
健康 Codex 行、其他来源和会话别名保留。本轮只在临时测试索引验证了此迁移，
没有打开或迁移用户个人索引。升级后的第一次实际刷新可能增加扫描耗时。
若回退旧解析器，旧代码忽略更高版本标志，可能沿用新版诊断缓存；应另行安排
仅重建 AgentRef 私有索引，不恢复或删除来源会话，不把重建当作默认回退动作。

## 下一轮真实双向验收协议

这是一份计划，不是通过记录。一次性项目使用现有配置的模型调用已获授权，
但当前登录、权限及配置漂移未闭环，未继续调用。启动代理、配置写入和宿主重启
仍未获授权；不读取任意私人会话、不改凭据、不切换付费路由、不终止现有用户任务。

1. 在独立一次性项目中，为每个方向记录 AgentRef 提交、宿主版本及接收模型。
   明确指定测试会话；源 Agent 完成第一阶段后，只中断本次拥有的测试子进程。
2. 记录源会话标识、已完成文件片段、测试文件及源文件哈希；可加入用户后续修改，
   验证接收端以当前文件为准。同名候选、空列表、取消应作为独立交互用例。
3. 在真实接收端菜单选择确切会话，观察附加项和发送动作；浏览/取消不应读正文，
   选中不得自动发送。单独记录 UI 证据，不能用 MCP 调用结果代替。
4. 用当前用户指令要求接收端继续；接收端应检查当前项目、只补齐剩余功能。
   独立复核已完成片段、用户修改、测试文件和源会话未变，并执行项目最终测试。
5. 两个方向分别记录通过、失败或未执行；认证失败、未产生实现、模型仅总结、
   测试未执行都不算通过。材料仅保留脱敏证据，不公开原始会话或凭据。

之后再推进：来源错误分类与诊断、安装/升级/回退一致性、SQL 层关键词筛选、
snapshot 缓存失效契约、复杂上下文接续质量评估。暂不扩展新来源或云端编排。

## 回退与使用

本轮补丁未提交；回退只撤销本轮文件差异，DSH `src/` 与 `lib/` 必须同步。
不要重置整个工作区、覆盖后续用户改动、删除会话或恢复旧配置。
没有安装步骤需要撤销；本轮不自动重启已链接的宿主。

## 2026-09-23 本地优化与验证

- 索引增量扫描现在保留适配器在 `consume` 阶段发出的诊断；孤立工具结果仍按
  元数据扫描策略过滤。新增回归测试确认冷刷新和暖缓存都维持不完整标志。
- `agentref sessions` 新增 `--query`、`--limit`、`--offset`；无这些选项时保留
  原全量输出。DSH 搜索把查询和 50 条限制传入 CLI，选中后按精确 ref 查询 1 条。
  旧 CLI 不认识新参数时回退到旧全量命令，因此大列表在旧 CLI 上仍可能超过 8 MiB。
- Python 测试：203 项通过，1 项 Windows 符号链接能力跳过。首次全量运行发现
  一个时间戳标签的旧断言，按现有“标题 · 时间”格式修正后全量复跑通过。
- DSH / OpenCode Node 测试：30 项通过。DSH 构建完成，`src/index.js` 与分发用
  `lib/index.js` SHA-256 相同。
- 12,000 行合成查询基准，5 次测量且结果/顺序一致：过滤列表中位数 15.37 ms
  （参考路径 40.41 ms），单来源服务器 15.59 ms（参考路径 41.66 ms），两项均从
  物化 12,000 行降至 2,000 行；全来源为 100.17 ms（参考路径 107.88 ms），两侧
  均物化 12,000 行。50 行分页为 45.08 ms（完整读取切片参考 123.91 ms），Python
  侧构造行数从 12,000 降至 50。仅是当前机器的合成观察，不是刷新耗时或性能承诺。
- 无关键词分页现在由 SQLite 按与原实现等价的 UTC 微秒时间键和 ref 排序，并在
  Python 侧构造行对象前应用 offset/limit；精确 ref 复核走主键单行查询。关键词
  筛选由 SQLite 调用等价谓词，标题覆盖、缓存标题及 Unicode casefold 语义保持不变。
  来源刷新成本未消除。
- 这轮没有运行真实 DSH、宿主菜单、模型、远端 CI 或发布验收，也没有改宿主配置。

## 2026-09-24 SQL 关键词分页

- `sessions --query --limit --offset` 的关键词页现在由 SQLite 候选查询返回，
  保留原 exact ref/session ID 优先级、时间/ref 排序、Codex 保存标题、经过身份
  校验的派生标题以及 Python Unicode `casefold` 行为。自定义 adapter 若覆盖标题
  但没有同时实现等价的 overlay/search hooks，会使用原完整列表路径。
- 12,000 行合成库、5 次测量、结果顺序一致：关键词页 50 行中位数 61.06 ms，
  参考路径 126.61 ms；Python 侧行对象从 12,000 降到 50。无匹配查询 37.10 ms，
  参考路径 152.93 ms；Python 侧行对象从 12,000 降到 0。SQLite 仍需检查和排序
  候选；基准不测 SQLite 内部临时排序内存，也不含来源刷新。
- Python 全量测试 212 项通过、1 项跳过；DSH/OpenCode Node 测试 30 项通过。

另一次 12,000 行、5 次测量在 overlay 单遍分组后仍保持行/顺序等价：来源过滤中位数
14.90 ms（参考 40.71 ms），单来源 15.55 ms（参考 40.58 ms），全来源 100.20 ms
（参考 103.89 ms）；50 行全来源页 44.69 ms（完整切片参考 116.26 ms）。

## 2026-09-24 快照刷新写入优化

- 快照适配器仍完整扫描来源，但只有索引元数据变化时才执行 `INSERT OR REPLACE`；
  暖扫描不再重写完全相同的 SQLite 行。回归测试核对 `total_changes` 在无变化扫描
  中保持不动，并确认 header 元数据改变后索引仍更新。
- 清理 stale rows 的查询也按当前启用 adapter 过滤；单来源 CLI 刷新共享索引时不再
  将其他来源的路径全部加载到 Python。混合来源回归确认未启用来源仍保留。
- DSH 扫描和上下文读取在内部传递已校验路径，避免同一调用链重复 `resolve()` 和
  symlink/junction 边界检查；外部 stream/metadata 入口仍自行校验。
- 100 会话、3 条消息、64 字符宽度的全六来源合成规模检查通过。DSH JSONL 暖刷新
  约 229 → 125 ms，菜单约 238 → 127 ms；DSH Zstandard 暖刷新约 305 → 126 ms。
  测试确认源哈希未变、最新证据保留、上下文低于上限；这些是本机合成观察。
- Python 全量测试 204 项通过、1 项跳过；DSH/OpenCode Node 测试 30 项通过。没有
  增加快照缓存，也没有运行真实宿主、模型、远端 CI 或发布验收。
- 隔离 wheel 检查通过：源码树外安装、16 项资源哈希、CLI 和合成 MCP 流程通过；
  没有调用模型或读取真实会话。

## 2026-09-24 快照扫描开销

- 快照扫描继续读取每个来源以检查 WAL、文件变化和删除，但只有元数据与索引行
  不同才写 SQLite；`refresh.changed` 现在也统计快照元数据变化。DSH 合成测试核对
  暖刷新不增加 `total_changes`，并确认 header 改动被写入索引。
- stale-row 清理按启用来源执行参数化 SQL；共享索引回归确认 DSH 刷新未把未启用的
  Claude 行载入清理列表或删除。
- DSH 在 scan/read 链路中只做一次会话路径边界校验；缺少投影缓存目录时，每轮只
  检查目录一次。对比同一 100 会话合成规模，DSH JSONL 暖刷新/菜单约 229/238 ms
  降至约 125/125 ms；Zstandard 约 305/329 ms 降至约 125/134 ms。后续复跑有机器
  负载波动，故只把这些作为本机样本，不外推生产性能。
- 300 会话、60 条消息的重复规模运行有显著抖动：DSH JSONL 暖刷新约 0.56–4.27 s，
  Zstandard 约 0.55–2.61 s；菜单约 0.54–1.34 s。源哈希与上下文检查都通过，
  但这组延迟不适合作稳定性能估计。
- 独立路径校验微基准使用 300 个合成的规范 root 子路径、7 次交错测量；旧/新实现
  返回路径完全一致，中位数约 331/107 ms。既有测试继续覆盖 root 别名、root 内
  symlink、逃逸路径和不可用的符号链接能力。

## 2026-09-24 JSONL 流式消费

- 增量索引和默认 Claude/Codex/Grok 会话读取逐条解析 JSONL；仍保留 `read_jsonl()`
  列表接口，覆写旧 `readSessionIncrementally()` 的自定义 adapter 通过兼容回退运行。
- 增量索引使用 warning callback 统计诊断数量和 incomplete-tail 状态，不再保留每条
  malformed/unknown 记录对应的 warning 字符串；完整会话读取仍可取得详细 warning 列表。
- 新增 `scripts/check_jsonl_streaming.py` 合成基准。对 41.1 MB、2,500 条记录，
  旧列表解析峰值约 40.89 MiB，流式消费约 0.20 MiB；数量、摘要、终止偏移和警告一致。
- 新增 `scripts/check_context_render.py` 合成基准。50,000 条 evidence、1,200 字符预算，
  与旧输出语义一致；中位耗时约 320.65 → 1.01 ms，峰值 Python 内存约 5.58 → 0.03 MiB。
  同脚本的 50,000 条近期决策扫描保持输出一致，中位耗时约 167 → 118 ms，峰值从
  9.2 MiB 降到低于 0.05 MiB；单条超长多行消息也覆盖了流式分行路径。
- continuation candidate 排序改为每个任务保留最佳优先级/新旧排名，再用 top-k 输出，
  结果与旧全量排序一致。50,000 项、1,000 个重复任务、limit=12 的基准中位耗时约
  145.44 → 35.82 ms，峰值 Python 内存约 9.28 → 0.12 MiB。
- 工具结果按 call ID 使用最新调用索引，重复 ID 仍匹配最近调用。5,000 个并行调用
  按原序返回结果的合成基准与旧反向扫描等价，中位耗时约 394.72 → 2.06 ms。
- Codex patch sideband 合并按 direct call ID、path 和 cwd 建索引，只比较同一 key
  的候选；状态/hash 冲突仍保守标成 `UNCERTAIN`，原文件操作顺序保持不变。
- `patch_apply_end` 重复事件按 `(call_id, turn_id)` 做每会话索引，重复/冲突事件继续
  使用现有不确定状态规则；索引会在元数据分段清理及会话 finish 后释放。
- DSH selected-session parser 不再保留第二份完整 event 列表。50,001 条合成事件的
  终态与 list-parser 参考一致，Python 峰值内存约从 32.10 MiB 降至 0.13 MiB。
- OpenCode 标题派生复用同一 session metadata 结果，Antigravity workspace URI 在首个
  本地路径命中后停止遍历。OpenCode bounded-title extraction 将至多128个 message 的
  part 查询合成一条有界 UNION 查询；adapter 回归确认只执行一条 parts statement。
- OpenCode selected-session 读取由每 message 一次 part 查询改为单个有序 join；回归
  核验 message 顺序和工具运行状态，并通过 trace 确认只执行一条 parts 查询。
- OpenCode snapshot metadata 按 SQLite cursor 逐行 yield；回归确认 `scan_files` 第一次
  yield 时只构造一个会话元数据对象。100 会话全来源合成规模中 refresh 峰值约 0.05 MiB；
  这是当前实现观察值，没有作为相对旧实现的性能承诺。
- OpenCode 同一 Index 进程内会在 SQLite 数据库/WAL 签名稳定、索引来源路径集合一致时复用
  快照元数据；数据库/WAL 变化、索引行替换/缺失、来源移除都会触发重扫/清理。300 会话
  synthetic cold/warm 约 34.1/1.8 ms。Antigravity 同规模 warm refresh 约 157.5 ms，仍使用全扫描；
  之前 cache 对照仅改善约 2%，因此保留全扫描以避免额外缓存状态。DSH 仍完整扫描；Grok 的缓存
  开关和 warm-path 复核见本节后续记录。
  同一 2,000 DB fixture 交错比对 Antigravity 缓存/全扫描，cold 约 1,895/1,033 ms，warm
  中位约 1,257/982 ms，因此关闭该缓存。OpenCode 缓存不跨进程持久化，基准不包含真实用户数据。
- handoff 的 status、两种 diff 摘要、log 和 HEAD 五条只读 Git 命令在 root 验证后并发；
  当前 checkout 交错测量 5 次、结果字节相同，中位数约 268 → 93 ms。该值依赖工作树和
  Git/磁盘负载，只作当前 checkout 的观察。
- MCP `resources/list` 使用 SQLite 有界分页，读取 101 行判定 next cursor，只输出前
  100 行；新增回归检查首尾页 cursor 和查询 limit/offset。
- MCP `search_mentions` 现在请求 100 行页面和精确匹配总数，返回的 items/total/hasMore
  与原全量列表一致；新增 `include_total` 查询基准覆盖分页后总数。
- Claude/Codex 增量索引 warm refresh 在 2,000 条合成会话上 cProfile 观察为约
  60/82 ms（此前同法约 244/386 ms）；300 条合成会话的非采样 warm refresh 分别约
  4.4/4.8 ms。变化来自每来源批量读取旧索引、`os.scandir` 非跟随链接遍历，以及复用
  扫描时取得的文件 mtime/size；统计映射在 refresh 后释放。合成检查确认历史证据保留、源哈希不变。
- 12,000 行、50 行返回的全来源分页合成基准中位数约 87.70 → 53.61 ms；时间键缓存
  只在 ISO 值重复后保存结果，最多 4096 项，超长值绕过。隔离键计算探针中，重复值约
  30.12 vs 48.60 ms，微秒级唯一值约 36.45 vs 33.40 ms，说明唯一值场景仍有约 9% 开销。
  路径 basename 匹配不再为每行构造 `Path`；SQL 排序键直接解析时间，不创建通用
  `session_time()` 临时字典。时区偏移、createdAt/mtime 回退和极端年份的排序回归保持一致。
- 12,000 条索引配 1.07 MB 合成标题缓存时，关键词分页复用已解析标题缓存约 107.21 ms，
  每次强制重载约 115.94 ms；标题文件外部改写后同一 Index 会读取新标题的回归通过。
- Alias inventory 超过 20,000 条时改用 4,096 行有序 SQLite batches；25,000 条合成会话
  unique/repeated 标题的 reservation 约 251/233 ms，tracemalloc peak 约 15.28/14.02 MiB，
  全部 alias 已持久化。小于等于阈值仍使用更快的整表路径。
- 12,000 条会话的动态 completion 首次 alias inventory 预留约 150.18 ms，后续热请求中位数
  约 32.17 ms（旧全量 rows/filter/alias 路径约 237.99/198.76 ms）；后续按 100 项页与精确
  总数查询。MCP 热路径只保留 inventory 签名，alias map 从 SQLite 页内读取，不长驻全表字典。
  12,000 行 tracemalloc 观察：首次完成后 retained 约 0.96 MiB、peak 15.74 MiB；热请求
  retained 约 0.01 MiB、peak 0.14 MiB，缓存中未保留全表 alias map。索引行、标题缓存或
  Codex session_index.jsonl 签名变化会重建 alias inventory。
- 仅更新活动时间/运行状态的刷新会推进 alias inventory 签名而保留已预留 alias；身份、
  标题、derived-title、Codex 保存标题或来源删除变化仍触发重建。新增测试覆盖追加 assistant
  活动记录后 completion inventory 保持热缓存。
- Python：`.venv` 全量 unittest **239 项通过、1 项跳过**。
- agent alias 表为空时首轮分配走单次有序扫描并用每个 base 的 suffix cursor；重复标题及
  `same` / `same_2` 跨标题冲突回归均通过。
- 12,000 条合成 alias 写入到同一 SQLite 表的 5 次微基准中，插入顺序与按 `(agent, alias)`
  排序后的中位数约 32.25 → 28.88 ms；正式分配映射保持不变。
- 已有 alias 库遇到 12,000 个同标题会话时，编号 owner 批量预读后按 base cursor 分配，
  warm duplicate alias allocation 约 41 ms；反序重分配约 48 ms，保持首轮 ref→alias 映射完全一致。
- 对已有 2,500 个连续保留编号的标题，后续 alias 分配通过最多 500 项的 suffix 批次找到
  第一个空号；测试确认 2,501 号分配正确，SQL 查询数有界，不逐编号逐条查询。
- 空的 derived-title 缓存会绕过每行 identity 检查；普通 ASCII 标题用 `str.translate` 做
  alias 规范化，异常字符走完整 Unicode 清理。completion 仍保留全部 12,000 个 ref/alias，
  分页路径保持全局 alias 顺序。
- Refresh stale cleanup 现在只顺序读取启用来源的 sourcePath，并在游标耗尽后批量删除 stale
  行；完整清理不再先 `fetchall()` 物化所有启用来源行。
- MCP context 在来源、16 位十六进制 ref 校验后走索引单行查询，已不再为明确选中的
  会话先枚举全量列表；无效/跨来源 ref 在读取正文前拒绝。
- Mention alias 分配在事务中仅批量读取当前候选的基础 alias，冲突后才按复合主键查询
  编号 alias，再批量插入新 alias；保留重命名、重启、重复标题的 stable ref 归属，避免
  将所有历史 alias 装入内存。候选基础 alias 超过 500 个时分块查询。
- `resources/read` 的 alias 反查新增 `(alias,agent,ref)` 覆盖索引；老索引库重开时
  会补建该索引，`EXPLAIN QUERY PLAN` 确认 alias 精确查找使用它。
- MCP resource completion 复用一次已排序的 metadata inventory，再以内存过滤查询，
  避免为搜索结果重复加载第二份会话列表；alias 仍按原全局顺序分配。
- 会话 picker 现在最多从索引读取 31 条候选以区分唯一命中和歧义，随后最多展示 30 条；
  unique auto-selection、空列表和歧义行为的回归检查通过。
- 12,000 行 `include_total` 关键词页面、offset 100/limit 50 的合成基准与全量参考
  顺序/总数一致；Python 行对象从 12,000 降至 50，中位耗时约 145.21 → 82.29 ms。
- CLI `inspect` 通过 SessionIR 直接 JSON 编码，避免 `dataclasses.asdict()` 深拷贝。
  10,000 条、每条 1 KiB 消息的合成会话输出逐字相同；中位耗时约 138.46 → 66.75 ms，
  峰值内存约 14.35 → 12.51 MiB。
- `_overlay_metadata()` 改为单次按来源分组，再按既有 adapter 顺序调用 metadata hooks；
  12,000 行全来源查询基准输出保持等价。
- 六来源小规模 `check_scale.py` 通过，源哈希未变、最新证据保留；Python 全量测试
  237 项通过、1 项跳过，Node 测试 30 项通过。wheel 在源码树外安装成功，16 项
  资源哈希、CLI、doctor 与合成 MCP 流程通过。
