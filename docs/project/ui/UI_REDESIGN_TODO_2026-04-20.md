# UI 改版执行 TODO

核心业务基准：
- [x] 已建立 [核心业务功能基准](C:/Users/18335/Documents/New%20project/docs/CORE_BUSINESS_FUNCTIONS.md)，后续 UI 改版必须围绕“全局态势 -> 信号扫描 -> 机会池 -> 执行审查 -> 委托提交 -> 回执跟踪 -> 单票/日终复盘 -> 策略参数改进”主链路。
- [ ] 新增或调整页面前，先判断功能属于 P0 主链、P1 增强还是 P2 暂缓扩展。

最新补充：
- [x] 机会池“深度洞察”子页已补页首“深度洞察速览”，把主线热度 / 战法中控 / 今日计划 / 消息中心重新抬回统一入口，并接入同一套 `watch` 首屏下沉规则。
- [x] 扫描页“观察池”子页已补页首“观察池与回测速览”，把观察池焦点 / 回测摘要 / 盘中联动重新抬回统一入口，并接入同一套 `watch` 首屏下沉规则。
- [x] 扫描页“盘中监控”子页已补页首“盘中监控速览”，把监控状态 / 总览联动 / 机会链路 / 执行去向重新抬回统一入口，并让监控动作优先认当前监控焦点。
- [x] 扫描页默认焦点已统一为“盘中监控 > 观察池 > active_symbol”，让状态条 / 焦点卡 / 摘要卡 / scanner focus banner 保持同一标的，不再各说各话。
- [x] 扫描工作区残留入口文案已开始统一到 `看… / 去…` 口径，补齐能力卡按钮、页签 tooltip 和 scanner action row，移除“打开 / 查看 / 回到”混用。
- [x] `涨停策略 / 执行中控 / 复盘` 这些常用 action row 也已开始切到 `看… / 去…` 源头文案，并补了新旧文本共存期的绑定兼容。
- [x] `overview / 机会池` 的 action row 源头文案也已同步切到 `看机会 / 看总览 / 看消息 / 看风险 / 看观察 / 定位机会` 这套短词，不再只靠后置归一化修正。
- [x] 低频入口与提示文案继续收口：消息推荐动作改成 `先看复盘 / 先看总览` 口径，trade plan 空态按钮改成 `看观察 / 去交易`，并把 `查看委托明细 / 回到机会池 / 去看交易` 这类旧语气改成统一短词。
- [x] 与 `去执行中控` 相关的可见旧口径继续收口：默认提示、推荐主 CTA 路径建议、`去执行中控盯回执 / 复核` 等说法已统一改成 `去交易 / 去交易盯回执 / 去交易复核`。
- [x] tooltip 与低频弹窗入口继续收口：消息弹窗里的 `看推荐 / 去执行中控` 已改成 `看机会 / 去交易`，`RECOMMEND_TERMINAL_CTA_BASE_TOOLTIPS` 与 action tooltip 里的 `继续查看` 也开始统一改成 `继续看`。
- [x] 长文本说明继续收口：`回到这里 / 查看当前时点信息 / 查看执行反馈 / 继续查看信号` 这类低频旧语气已改成 `来这里 / 看当前时点 / 看执行反馈 / 继续看信号`。

基于 [UI_WORLD_CLASS_TERMINAL_DESIGN_2026-04-19.md](C:/Users/18335/Documents/New%20project/docs/UI_WORLD_CLASS_TERMINAL_DESIGN_2026-04-19.md) 拆解出的可落地任务清单。

工程约束补充：

- 后续页面与 Toggle 改动必须同时遵守 [UI 解耦与重构规范](C:/Users/18335/Documents/New%20project/docs/UI_DECOUPLING_REFACTOR_STANDARD_2026-04-20.md)。

总优先级：

- 第一优先级：整体 UI 设计先行，先统一页面结构、视觉语言、品牌纪律和终端节奏。
- 第二优先级：先判断页面是否要拆、是否要重排、是否要改成子视图，不先因为代码层原因进入重构。
- 第三优先级：只有设计落地需要时，才做代码解耦和重构。

执行提醒：

- 以后不要把“继续重构代码”当成默认主线。
- 以后默认主线是“继续把页面 UI 设计做对、做统一、做成机构终端”。

## P0 页面解耦与重构规范

- [x] 把“页面 / Toggle 解耦”要求正式写入规范文档
- [x] 把解耦规范挂回主 UI 设计文档
- [x] 把“控件复用优先 / 一 Toggle 一页面语义 / 首屏统一骨架”正式写入规范
- [ ] 以后新增功能前先判断属于主链还是辅助层
- [ ] 对已过重页面优先做下沉、折叠、拆模块，而不是继续堆功能
- [ ] workflow / toggle 设计优先保证“一项流程一个独立主视图”，不要把两个阶段塞进同一主页面
- [x] 将 shell workflow 中的“实验”从交易页拆成独立工作区
- [x] 将策略配置页拆成“参数与风险 / 战法配置 / 消息与AI / 说明”四个子页面
- [x] 将单票复盘页拆成“单票总览 / 信号与交易 / 历史战法”三个子页面
- [x] 将机会池页拆成“机会总览 / 执行审查 / 深度洞察”三个子页面
- [x] 将信号扫描页拆成“扫描榜 / 观察池 / 盘中监控”三个子页面
- [x] 将执行中控页拆成“执行总览 / 委托提交 / 回执复盘 / 接入维护”四个子页面
- [x] 将实验台页拆成“实验总览 / 持仓与交割 / 战法与巡航”三个子页面
- [x] 将涨停策略页拆成“候选总览 / 回封监控”两个子页面
- [x] 把工作区命名 / Hero / 壳层文案抽成统一配置源
- [x] 把 recommend / broker 的辅助区显示策略抽成统一配置
- [x] 把主表列宽 / 隐藏 / 拉伸规则抽成统一配置
- [x] 把 recommend / broker 的部分 splitter 默认尺寸抽成统一配置
- [x] 把 overview / recommend / board 控制台显隐策略抽成统一配置
- [x] 把 overview / recommend / broker 的主链区块顺序抽成统一配置
- [x] 把首屏次级区块显隐规则抽成统一配置
- [x] 把主链重排逻辑抽成可复用 layout helper
- [x] 把控制台显隐执行逻辑抽成可复用 visibility helper
- [x] 把工作区摘要与焦点条刷新逻辑抽成可复用 workspace runtime helper
- [x] 把 workspace badge 与 broker 状态 banner 文本生成抽成 runtime helper
- [x] 把 shell header 的顶部状态摘要生成抽成独立 helper
- [x] 把 workspace status labels 默认回写逻辑抽成 runtime helper
- [x] 把 shell header 本体刷新和跨页面焦点标签回写抽成 runtime helper
- [x] 把 recommend focus status 文本拼装抽成 runtime helper
- [x] 把 broker status panel 文本与指标回写抽成 runtime helper
- [x] 把 broker order focus 与 submission focus 文本拼装抽成 runtime helper
- [x] 把 recommendation focus panels 文本拼装抽成 runtime helper
- [x] 把 recommend bucket panels 文本拼装抽成 runtime helper
- [x] 把 recommend story panels 文本拼装抽成 runtime helper
- [x] 把 recommend focus cards 回写逻辑抽成 runtime helper
- [x] 把 broker auxiliary panels 状态文案抽成 runtime helper
- [x] 把 broker action flow 的按钮、摘要卡与回放状态回写抽成 runtime helper
- [x] 把 submission focus 的回放卡、复盘卡与执行摘要回写抽成 runtime helper
- [x] 把 recommend decision summary 的正文插入与 CTA 按钮层级回写抽成 runtime helper
- [x] 把 recommendation focus panels 的消息附加与焦点标签联动抽成 runtime helper
- [x] 把 recommend / board CTA 按钮状态与主次操作层级回写抽成 runtime helper
- [x] 把 detail workspace 的摘要卡与复盘文本回写抽成 runtime helper
- [x] 把 scanner 的状态条、焦点卡和摘要卡回写抽成 runtime helper
- [ ] 逐步把页面级逻辑从 `app_qt.py` 继续下沉到 builder / refresh / controller

## P0 终端命名与标题语言

- [x] 统一 8 个工作区的 Tab 命名
- [x] 统一 shell/header 的工作区标题映射
- [x] 统一状态栏 breadcrumb 的工作区命名
- [x] 调整 broker 页内部 Hero，降低“产品介绍感”，强化 desk header 气质
- [ ] 全量梳理页内旧命名，如“市场机会工作台 / 每日推荐 / 参数配置”等残留文案

## P0 执行终端气质

- [x] 完成一轮全局视觉系统改版，把壳层、Hero、面板、表格和按钮统一压到“石墨黑 + 机构蓝 + 交易金”体系
- [x] 压缩顶部 shell chips / pulse / workflow bar 的信息密度
- [x] 强化 broker 页三段式结构：摘要、控制、明细
- [x] 保持账户配置与运行维护默认可见，符合执行台使用习惯
- [x] 收紧 broker Hero 与 shell 文案，改成更短的终端式表达
- [x] 为已拆分子页面统一增加“子视图摘要条”，明确每个二级页面的看点、动作与下一步
- [x] 为全局态势增加“市场判断条”，让首页先回答判断、动作与下一步
- [x] 继续压缩 shell header 的产品介绍感，改成更短的终端指挥条表达
- [x] 为机会池 / 执行中控补统一判断条，形成“状态条 -> 判断条 -> 指标 -> 子视图”的首屏节奏
- [x] 收短 overview / recommend / broker 的 Hero 副标题，避免首屏再次产品介绍化
- [ ] 继续压缩 shell header 的介绍性表达，进一步向 OMS/EMS 顶栏靠拢

## P0 表格与数字规范

- [x] 调整 broker 委托表与回执表列宽、对齐、行高
- [x] 为关键数字列应用更明确的右对齐和终端数字字体
- [x] 收敛优先级、动作、风险灯的色彩语义
- [x] 为更多核心表格统一“名称左、状态中、数字右”的规则
- [x] 补充当前选中行的左侧焦点线样式
- [x] 为核心表格增加响应式列裁剪优先级，紧凑宽度下自动收起次要列
- [x] 为核心主表统一终端式空态占位，避免空表时只剩一片空白
- [x] 为核心主表增加紧凑短表头，紧凑宽度下自动切到更短的终端式列名

## P1 文案与状态语言

- [x] 更新接入中心、机会池、执行中控、涨停策略、单票复盘、策略配置的 Hero 文案
- [x] 更新 shell/page copy 到“判断式 + 下一步”风格
- [x] 统一各工作区顶部状态条句式为“状态：当前阶段 | 当前阻塞 | 下一步”
- [x] 扫描摘要、推荐状态、交易状态等高频回写文案已开始统一到终端句式
- [ ] 全量梳理 Banner、空状态、按钮文案，统一为交易中控口吻
- [x] 工作台 Banner 与运行空态默认文案已开始统一配置化
- [x] 统一消息中心与运行日志的状态语言模板
- [x] 推荐 / broker 主 CTA 与焦点按钮已开始统一配置化
- [x] action row 辅助动作短标签与 tooltip 已开始统一配置化
- [x] workbench 空态 copy 与主 CTA 标签已进一步收短到终端口吻
- [x] broker 默认说明块中的旧操作词已开始统一到“委托链路 / 提交确认”口径
- [x] overview / auth 的长导航入口词已开始统一到短标签口径
- [x] 高频“推荐页 / 推荐池”旧称已开始统一到“机会池”口径
- [x] 消息动作、board 联动提示与 broker 高频引导里的旧“推荐池”表述已继续向“机会池”扩散
- [x] scanner 已补齐状态条 + 判断条，开始接入统一首屏骨架
- [x] auth / paper 已补摘要层，开始接入“状态条 + 判断条 + 摘要层”首屏骨架
- [x] scanner / board 已补摘要层，开始接入“状态条 + 判断条 + 摘要层”首屏骨架
- [x] paper / scanner / board / detail 的状态条与判断条已开始接入动态回写
- [x] config 已补齐状态条 + 判断条，开始接入统一首屏骨架

## P1 视觉语义系统

- [x] 继续区分系统状态色与执行表格状态色
- [x] 收紧 broker 终端配色，减少后台式浅色块
- [x] 全局落地“系统状态色 vs A 股涨跌色”双语义规范
- [x] 统一图表中的入场 / 止损 / 目标位颜色

## P2 终端密度与自适应

- [x] 抽出统一宽高断点常量
- [x] 抽出统一 Hero 紧凑态规则
- [x] 抽出表格列优先级隐藏映射
- [x] 增加“标准 / 紧凑 / 盯盘”三档终端密度模式

## 当前这轮已完成

- 工作区命名已切到：
  - 全局态势
  - 接入中心
  - 机会池
  - 执行中控
  - 信号扫描
  - 涨停策略
  - 单票复盘
  - 策略配置
- broker 页 Hero 已改成更短的 desk header 风格
- shell 品牌与状态文案更接近“机构级交易决策终端”方向
- broker 委托表 / 回执表已继续金融终端化
- 核心工作区的 Hero Stamp、面板标题和分区命名已开始统一到终端语义
- 工作区命名 / Hero / shell / statusbar 文案已开始统一配置化
- 总览 Hero 标题、机会池生成状态、顶栏脉搏与战法卡空态已继续从“市场机会工作台 / 每日推荐池”收口到“市场总控台 / 机会池”命名
- 跨工作区主链提示已继续从“推荐页 / 交易执行 / 打板页”收口到“机会池 / 执行中控 / 涨停策略”命名
- 统一词典与风险档位按钮 tooltip 已继续收口到“机会池 / 执行中控 / 接入中心 / 涨停策略”口径
- workbench 横幅、消息中心动作提示与外围空态说明已继续收口到“机会池 / 执行中控 / 单票复盘 / 信号扫描 / 涨停策略”口径
- 配置页“消息与AI”子页已补首部速览层，把消息源状态与 AI 评测状态前移到页首判断条之后，不再只有两块长面板堆叠
- 配置页“战法配置”子页已补首部速览层，把目录、草稿和 JSON 编辑状态前移到页首，不再只有列表与表单/脚本 splitter 直接堆叠
- 配置页现在已形成“能力总览 + 战法速览 + 消息与AI速览”三级首部结构，配置主链开始像终端中控，而不是一组长表单
- 涨停策略页已补可折叠“打板控制台”，把导出与专项动作下沉到独立抽屉，首屏继续优先保留候选与监控主链
- 单票复盘页“历史战法”子页已补页首速览层，把当前战法、参数对比和逐笔样本状态前移到页首，不再直接掉进多张统计表
- 实验台“战法与巡航”子页已补页首速览层，把主测战法、巡航状态和实验洞察前移到页首，不再直接掉进收益拆解表和巡航日志
- 实验台现在已形成“能力总览 + 战法与巡航速览”双层首部结构，实验子页主链开始和配置页、复盘页保持同一套节奏
- UI 设计硬规则已补成文档：优先复用现有骨架组件、一个 toggle 对应一个页面语义、首屏统一按 Hero/状态/判断/摘要/子视图组织
- 工作台 Banner、运行日志与多块文本空态已开始统一配置驱动
- 消息中心摘要、事件详情、动作条与运行日志级别文案已开始统一模板化
- 推荐页主 CTA、交易页主 CTA 与阻塞/优先焦点按钮已开始统一配置驱动
- 页内 action row 的“看机会 / 去交易 / 看委托 / 刷新监控 / 导出日志”已开始统一词典驱动
- workbench 空态 copy 与主 CTA 标签已继续收短，整体更接近终端式口吻
- broker 页默认说明、执行回放引导与 shell note 已开始统一到“生成委托链路 / 打开确认弹窗提交”表述
- overview / auth 首屏导航入口已开始从“前往推荐池 / 前往交易执行 / 前往登录配置”统一到短标签
- 消息中心动作、模拟盘回跳按钮、机会池刷新入口与 AI 提示已开始从“推荐页 / 推荐池”统一到“机会池”
- 新闻动作提示、board/扫描联动说明、broker 高频回跳提示里的“推荐页 / 推荐池”已继续收敛到“机会池”
- auth / paper / detail / board / scanner 已开始统一到“Hero -> 状态条 -> 判断条 -> 子视图”的首屏节奏
- auth / paper 已进一步补到“Hero -> 状态条 -> 判断条 -> 摘要卡 -> 子视图”的首屏骨架
- scanner / board 已进一步补到“Hero -> 状态条 -> 判断条 -> 摘要卡 -> 子视图”的首屏骨架
- paper / scanner / board / detail 已开始从静态首屏骨架进入动态状态层
- config 已开始统一到“Hero -> 状态条 -> 判断条 -> 子视图”的首屏节奏
- recommend / broker 辅助区的默认显隐与提示文案已开始配置驱动
- 关键表格列规则与部分 splitter 默认值已开始配置驱动
- 顶栏右上角已增加全局密度切换，开始把“标准 / 紧凑 / 盯盘”从文档要求变成可直接操作的终端能力
- 宽高断点与密度语义已开始进入统一配置源，页面不再只靠局部 patch 自行判断
- Hero、表格行高、表头高度与首屏间距已开始按统一密度模式联动收缩
- 图表与状态色已开始按“双语义”统一：K 线切到 A 股红涨绿跌，系统成败继续保留成功 / 警示 / 风险色
- 计划买点 / 止损 / 目标位已开始统一到固定图表语义色，后续页面扩展不再各自定义一套颜色
- 核心终端表已开始切到统一列优先级映射，`标准 / 紧凑 / 盯盘` 不再只是间距变化，也会联动列保留和短表头策略
- 首屏显隐已开始接入密度模式，扫描 / 打板 / 复盘 / 实验等工作区的次级摘要层会按 `盯盘` 模式自动下沉
- 扫描工作台 / 涨停执行台 / 单票工具台 / 实验导航等辅助工具区已开始按 `盯盘` 模式自动下沉，首屏进一步回到主链判断
- 接入摘要、配置总控与风险快照也已开始接入 `盯盘` 下沉规则，但接入表单和关键配置区仍保留在首屏主链里
- 总览页的 `前排龙头` 与 `主题摘要` 也已开始接入 `盯盘` 下沉规则，首屏进一步聚焦市场判断、主图与机会池
- 当总览页已有焦点或机会池时，`优先级看板`、`关键摘要`、`右侧情报 Tabs` 也已开始接入 `盯盘` 下沉规则
- 总览页的 `左侧信号 Tabs`、`副图 Tabs`、`图层控制 Tabs` 也已开始接入 `盯盘` 下沉规则，首屏更集中到主图与机会池
- 当总览页已有焦点或机会池时，`关键指标`、`主线看板`、`下一步动作` 这些行动说明层也已开始接入 `盯盘` 下沉规则
- 当这些块都下沉后，总览页左右侧栏容器也已开始接入 `盯盘` 下沉规则，首屏空间进一步回收到主图与机会池
- 总览页 `盯盘` 模式下已开始回收 splitter 空间，不再只隐藏侧栏内容而保留左右空栏
- 总览页 `盯盘` 模式下已开始放开主图与机会池的高度上限，让主视图区真正吃到回收空间
- 总览页中心区的二级标题 / 副标题 / 信号说明也已开始接入 `盯盘` 下沉规则，避免和顶部 Hero 重复表达
- 机会池与执行中控的 `desk summary / stage summary / 工作台横幅 / 次级摘要卡` 也已开始接入 `盯盘` 下沉规则
- 机会池的 `关键摘要卡` 也已开始接入 `盯盘` 下沉规则，首屏继续聚焦焦点状态、执行动作卡和工作流
- 机会池在 `盯盘` 模式下已开始回收 splitter 空间，优先把空间让给执行审查和深度洞察主视图区
- 机会池的执行动作卡在 `盯盘` 模式下已开始放开高度上限，主链动作区能真正吃到回收空间
- 机会池与执行中控的 `workflow tabs / stage tabs` 在 `盯盘` 模式下也已开始拿到更高的高度预算
- 执行中控的 `执行阶段` 重复标签也已开始接入 `盯盘` 下沉规则，避免和状态条 / 焦点条重复表达
- 执行中控在 `盯盘` 模式下已开始回收 splitter 空间，优先把宽度让给委托主区和当前委托详情
- 扫描 / 打板 / 复盘 / 实验 / 配置这些工作区的 `stage summary` 也已开始接入 `盯盘` 下沉规则，Tabs 继续保留
- 扫描 / 打板 / 复盘 / 实验 / 配置这些页面的 `stage tabs` 在 `盯盘` 模式下也已开始拿到更高的主区高度预算
- 扫描 / 打板 / 复盘 / 实验 / 配置 / 接入这些工作区的 `desk summary` 也已开始接入 `盯盘` 下沉规则，避免和状态条重复解释
- overview / recommend / board 三类控制台显隐策略已开始配置驱动
- overview / recommend / broker 的主链重排与首屏次级显隐已开始配置驱动
- 主链重排逻辑已开始从 `app_qt.py` 下沉到通用 layout helper
- 控制台显隐执行逻辑已开始从 `app_qt.py` 下沉到通用 visibility helper
- 工作区摘要与焦点条刷新逻辑已开始从 `app_qt.py` 下沉到 workspace runtime helper
- workspace badge 与 broker 状态 banner 文本生成已开始从 `app_qt.py` 下沉到 workspace runtime helper
- shell header 顶部状态摘要已开始从 `app_qt.py` 下沉到独立 helper
- workspace status labels 默认回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- shell header 本体刷新与 cross-workspace focus labels 已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommend focus status 文本拼装已开始从 `app_qt.py` 下沉到 workspace runtime helper
- broker status panel 文本与指标回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- broker order focus 与 submission focus 文本拼装已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommendation focus panels 文本拼装已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommend bucket panels 文本拼装已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommend story panels 文本拼装已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommend focus cards 回写逻辑已开始从 `app_qt.py` 下沉到 workspace runtime helper
- broker auxiliary panels 状态文案已开始从 patch 层下沉到 workspace runtime helper
- broker action flow 的按钮、摘要卡与回放状态回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- submission focus 的回放卡、复盘卡与执行摘要回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommend decision summary 的正文插入与 CTA 按钮层级回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommendation focus panels 的消息附加与焦点标签联动已开始从 `app_qt.py` 下沉到 workspace runtime helper
- recommend / board CTA 按钮状态与主次操作层级回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- detail workspace 的摘要卡与复盘文本回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- scanner 的状态条、焦点卡和摘要卡回写已开始从 `app_qt.py` 下沉到 workspace runtime helper
- 已完成一轮全局 UI 重设计，统一了壳层、Hero、面板、表格和按钮的品牌纪律与视觉语义
- shell workflow 已开始按“实验独立工作区”方向拆分，不再让交易与实验共用同一主页面
- 策略配置页已开始按独立子页面拆分，不再把参数、战法、消息源、AI 和说明堆在同一长页
- 单票复盘页已开始按独立子页面拆分，不再把决策、执行、信号和历史统计堆在同一长页
- 机会池页已开始按独立子页面拆分，不再把候选、审查、战法和复盘消息堆在同一长页
- 信号扫描页已开始按独立子页面拆分，不再把扫描榜、观察池和盘中监控挤在同一长页
- 执行中控页已开始按独立子页面拆分，不再把执行总览、委托提交、回执复盘和接入维护堆在同一长页
- 实验台页已开始按独立子页面拆分，不再把实验总览、持仓交割和战法巡航堆在同一长页
- 涨停策略页已开始按独立子页面拆分，不再把候选判断和回封监控挤在同一主视图
- 已拆分工作区开始统一使用子视图摘要条，二级页面不再只是裸 tab，而是具备明确的页内判断与下一步提示
- 全局态势首页已增加市场判断条，首页不再直接从控制台跳到指标带，而是先给出市场判断
- shell 顶部副标题已切到更短的工作台短句，不再继续复用偏介绍型的 Hero 文案
- 机会池与执行中控首页也已补统一判断条，三页开始形成同一套机构级首屏节奏
- 核心表格已开始统一列语义、行高与选中焦点线，读法更接近机构终端
- 核心表格已补响应式列裁剪，紧凑宽度下优先保留名称、状态和关键数字列
- 核心主表已补统一空态占位，空表时也保持终端秩序感
- 核心主表已补紧凑短表头，窄屏下仍保持终端读法
- 各工作区顶部状态条已开始统一为终端句式，不再混用说明型文案
- 扫描摘要、推荐回流提示、交易生成提示等高频状态文案已继续收口到统一终端句式
- watch main area expansion:
  - detail / paper / config 在 `watch` 下补齐 splitter 空间回收，主区不再只靠隐藏摘要层“假扩容”。
  - board / detail / paper 的主文本区在 `watch` 下放开旧高度上限，让清出来的首屏空间真实回到主内容。
  - scanner 在 `watch` 下补齐观察池 / 回测摘要分栏回收，并把扫描榜、观察池、盘中监控主表预算继续前推。
  - config / auth / detail 的状态台与帮助面板在 `watch` 下同步抬高预算，避免主链文本继续被短面板切碎。
  - detail / paper 的图表和历史分析区在 `watch` 下同步抬高预算，历史曲线、历史交易表、对比表和权益图继续向主分析区让位。
  - broker 的执行分析区在 `watch` 下同步抬高预算，执行分析 splitter 和执行结果文本继续向主执行链路让位。
  - config 的多行策略编辑区在 `watch` 下同步抬高预算，让公式权重、场景定位、动作模板等编辑表单进入主链节奏。
  - recommend 的 review / recap 主链在 `watch` 下同步抬高预算，分发、复核、复盘、次日计划和 recap 分栏继续向连续判断链路让位。
  - broker 的委托焦点与运行维护区在 `watch` 下同步抬高预算，委托焦点文本、运行状态、运行日志和 setup 分栏继续向盘中诊断链路让位。
  - recommend 的策略细节盒子与行动卡盒子在 `watch` 下同步抬高预算，让决策摘要、策略细节、主线推演和优先级看板一起进入主链节奏。
  - overview 的辅助判断文本与 broker 的结果回放区在 `watch` 下同步抬高预算，让主题摘要、资金画像、交易决策和回放事件卡一起进入主链节奏。
  - overview 的右侧判断盒子与 recommend 的 recap / 消息中心容器在 `watch` 下同步抬高预算，让容器层级也进入工作台节奏。
  - overview / recommend / broker 的大容器本体在 `watch` 下同步放开预算，让 cockpit、playbook、主线看板、策略中控、posttrade section 这些 section 一起进入工作台节奏。
  - overview / recommend / broker 的 drawer / stage 容器在 `watch` 下同步放开预算，让 controls drawer、stage container、setup drawer 这些壳层也进入工作台节奏。
  - watch 模式下同步压缩 hero / stage hero / drawer / stage container 的留白与间距，让外层 chrome 也切换到工作台节奏。
  - workspaceHero / workspaceStageHero 在 `watch` 下同步压缩 badge rail 宽度、grid spacing 和 subtitle 占高，进一步收紧顶部摘要带。
  - 当主链就绪时，watch 首屏同步下沉重复的 statusBanner，优先保留 focus strip 和主视图，避免顶部三层同权重提示。
  - watch 模式下同步自动落到最该看的子视图，机会池 / 交易 / 扫描 / 配置页优先进入当前阶段最关键的 tab，但不覆盖用户手动锁定的 tab。
  - focus strip 的副标题句式统一成 “当前状态 / 焦点 / 下一步” 顺序，不同页面只替换内容，不再各自换顺序。
  - 工具区 live summary 的 headline / detail / meta 统一成 “当前状态 / 焦点 / 下一步” 三层顺序，不再混写信息。
- focus banner 可见文案开始统一成“当前状态 + 下一步”节奏，tooltip 同步切到“当前状态 / 焦点 / 下一步 / 交互”四段语义。
- [x] 配置页开始补“功能回补主链”，把参数与风险 / 战法配置 / 消息源管理 / AI 评测重新做成能力总览与直达入口，避免拆页后像功能被删掉。
- [x] 机会池开始补“功能回补主链”，把战法工作台 / 复盘消息 / 策略细节重新做成能力总览与显性入口，不再只剩局部卡片。
- [x] 单票复盘开始补“功能回补主链”，把历史战法统计 / 信号交易回放重新拉回能力总览与显性子视图。
- [x] 实验台开始补“功能回补主链”，把战法巡航 / 交割分析重新做成能力总览与可直接抵达的主链入口。
- [x] 涨停策略开始补“功能回补主链”，把候选判断 / 回封监控 / 执行准备做回能力总览与连续工作流。
- [x] 扫描页开始补“功能回补主链”，把扫描候选 / 观察池与回测 / 盘中监控重新做成能力总览与显性入口。
- [x] 执行中控开始补“功能回补主链”，把执行总览 / 委托提交 / 回执复盘 / 接入维护重新做成能力总览与显性入口。
- [x] 总览开始补“功能回补主链”，把市场判断 / 主线龙头 / 消息催化 / 买卖决策重新做成能力总览与显性入口。
- [x] 接入中心开始补“功能回补主链”，把接入通道 / 凭据校验 / Bridge 环境 / 后续入口重新做成能力总览与显性入口。
- [x] 统一能力总览组件纪律：所有 capability box 统一用同一套 `metric-band / capability card / watch 下沉` 规则，不再各页各画一套。
- [x] 统一能力总览入口动作词：同页入口统一收成“看…”，跨工作区动作统一收成“去…”，不再混用“打开 / 查看 / 前往”。
- [x] 继续统一低频入口语言：更多菜单、tooltip、消息按钮等次级入口也开始收成同一套短促终端词，不再出现“打开更多 / 查看详情 / 前往页面”混写。
- [x] 继续统一确认弹窗与消息提示词：`进入确认弹窗 / 看原文 / 看详情 / 可看原文` 这类说明词已开始替换旧的 `打开 / 可查看` 口径。
- [x] 记账原则：具体业务设计、UI 布局和信息层级由改版负责人按约束自主决定，但任何页面改版都不能丢功能，必须先补完整能力，再做视觉收口。
