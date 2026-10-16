# 小蕾米埃尔桌宠 · Claude Code 状态指示器

> ### ⚠️ 非官方同人衍生项目，使用前请先读这段
>
> - **素材来源**：动作素材来自《绝区零》官方活动页面，由 **[HanaAyane / 小蕾米](https://github.com/HanaAyane/remielle-codex-pet)** 整理并公开。
>   原作是给 **Codex** 用的素材包（不含运行器，422★）；**本项目是给 Claude Code 新写的运行器**，复用了它的动作语义与配置 schema。
> - **版权归属**：原始素材及角色版权归 **米哈游 / HoYoverse** 所有，本项目**不主张其版权**，也**未获得商业授权**。
> - **使用范围**：**仅供个人学习与非商业同人交流**。不得出售、商业授权、打包销售，不得暗示获得官方认可。
> - **不授予开源许可**：素材部分**没有** MIT / Apache / CC0 等任何通用开源授权。程序代码部分可自由修改自用。
> - 完整声明见 **[NOTICE.md](NOTICE.md)**；素材使用条款以原作者的
>   **[ASSET-USAGE.md](https://github.com/HanaAyane/remielle-codex-pet/blob/main/ASSET-USAGE.md)** 为准。

一只悬浮在桌面上的小蕾米，实时反映 Claude Code 在干什么 —— 思考、工作中、等你授权、完成、出错。

参考 [HanaAyane/remielle-codex-pet](https://github.com/HanaAyane/remielle-codex-pet)：**hook 只负责上报原始事件，桌宠按配置表把事件映射成动作**。调整「什么情况播哪张图」不用改代码，改 `pet_config.json` 就行。

> 原项目是给 Codex 用的素材包，本身不含运行器。这里沿用了它的**动作语义**（idle / expect / pen_idle / draw_continuous / smug / draw_intermittent / think）和 `states` + `events` + `priority` + `cooldownMs` 的配置 schema，但运行器是为 Claude Code 新写的。

> **要拷到别的电脑用？** 看 [`移植说明.md`](移植说明.md)。整包已经做成可移植的：路径全部按 `__file__` 推导、解释器自动发现、双击 `install.bat` 即可，里面有可直接粘给那台机器 Claude 的提示词。

---

## 快速开始

1. **启动桌宠** —— 双击 `启动小蕾米.bat`
2. **注册 hook** —— 运行一次（只需一次）：

```bash
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\install_hooks.py"
```

3. **重启 Claude Code** —— 改 settings.json 后需要重启才加载

---

## 启动与停止（跟随 Claude Code 生命周期）

**Claude Code 启动成功 → 小蕾米自动出现；Claude Code 关掉 → 小蕾米自动下班。** 你不需要管它。

| 事件 | 小蕾米的行为 |
|---|---|
| Claude Code 启动（SessionStart） | 自动被拉起来。已经在跑就什么都不做，不会开出第二只 |
| Claude Code 运行期间 | 一直陪着。关掉某一个会话**不会**让它退出（可能还开着别的会话） |
| Claude Code 完全关闭 | 连续 30 秒没检测到 `claude.exe` 进程，自己退出 |
| 想临时隐藏 | 单击托盘图标 |
| 想马上关掉 | 右键小蕾米 → 退出桌宠；或托盘图标右键 → 退出 |
| 想手动启动 / 唤出 | 双击 `启动小蕾米.bat`（已经在跑就把它叫到前面） |

`.bat` 用的是 `pythonw.exe`，**不会弹黑色控制台窗口**。

> **关闭为什么不用 SessionEnd？** 因为 Claude Code 可以同时开多个会话，某个会话结束不代表 Claude 退出了。所以关闭走的是「盯着 `claude.exe` 进程」—— 桌面版主程序和它带起来的 CLI 都叫这个名字，一并监视，谁在都算 Claude 还活着。

> **只可能有一只小蕾米。** 单实例锁用**原子的 pid 文件**（`O_CREAT|O_EXCL`），抢不到的那个直接退出，并顺手把已运行的那只唤到前面。
> 早先只用命名管道做判据是有坑的：管道连不上时得靠 `QLocalServer.removeServer()` 清残留，而那一步会把**正在运行那只的管道一起删掉**，于是自己重新监听成功 —— 多开 Claude 会话时几乎同时触发 SessionStart，就会冒出第二只。另外连接处理也从阻塞的 `waitForReadyRead()` 改成了异步信号，避免探测把桌宠的事件循环卡住。

### 「总在最前」是定期强制的

Qt 的 `Qt.WindowStaysOnTopHint` 并不牢靠 —— 窗口重建、被全屏程序顶掉、系统调整 z-order 之后都可能失效，表现就是**桌宠还在，但被别的窗口盖住了**（进程活着、`IsWindowVisible()` 也返回 True，可你就是看不见）。

所以 `pet.py` 每 4 秒用 Win32 `SetWindowPos(HWND_TOPMOST, ...)` 重申一次（带 `SWP_NOACTIVATE`，不抢焦点）。右键菜单的「总在最前」可以关掉，关掉后就不再重申。

### 窗口位置会被校验

窗口坐标是持久化的，但显示器布局会变（拔副屏、换接口、接投影）。如果上次的落点已经不在任何显示器里，**启动时会自动挪回主屏并记进日志** —— 否则窗口会永远待在屏幕外，看起来就像"桌宠没了"。

日志里能看到当时的显示器布局和落点：

```
显示器: H27D9S 0,0 2560x1440, RTK FHD HDR -1080,0 1080x1920　窗口落点: (-1068, 1330)
```

### 想改这个行为

`pet_config.json` 的 `lifecycle` 段：

```json
"lifecycle": {
  "launchWithClaude": true,           // 关掉它就完全不自动启动，只能手动双击 .bat
  "exitWithClaude": true,             // 关掉它就跟随不再退出，一直开着
  "claudeProcesses": ["claude.exe"],  // 监视哪些进程名
  "checkEveryMs": 3000,               // 每 3 秒查一次
  "exitAfterMisses": 10               // 连续 10 次没看到才退出（约 30 秒宽限）
}
```

比如你想让它完全不自动启动、完全手动控制：把 `launchWithClaude` 和 `exitWithClaude` 都设为 `false`。

---

## 怎么操作

| 操作 | 效果 |
|---|---|
| 左键拖动 | 挪位置（自动记住） |
| 右键 | 菜单：预览动作 / 窗口大小 / **文字大小** / 透明度 / 总在最前 / 重载配置 / 退出 |
| 双击 | 临时显隐状态文字 |
| 托盘图标单击 | 显示 / 隐藏 |
| 托盘图标右键 | 退出 |

**「预览动作」菜单**最常用 —— 不用真让 Claude 干活，就能挨个看每个状态。

### 调状态文字

右键菜单 → **文字大小**，可选 12 / 18 / 22 / 28 / 36 / 48 pt（当前默认 **18pt**）。

也可以直接改 `pet_config.json` 的 `window` 段：

```json
"labelFontPt": 18,      // 字号；内边距和圆角会跟着等比缩放
"labelMaxWidth": 460,   // 气泡最大像素宽，超长文字自动加省略号
```

改完让桌宠重新读取配置，两种方式都行：

- 右键小蕾米 → 「重新读取配置」
- 命令行：`D:\Anaconda\python.exe "D:\Claude project\DESK.PET\send_cmd.py" reload`

`send_cmd.py` 还能发 `show`（叫到前面）、`hide`、`toggle`。

> **注意**：`reload` 只重新读取 `states` / `events` / `window` 这些显示相关的设置。
> 改 `lifecycle` 段（自动启动/自动退出）**必须重启桌宠**才生效，因为看门狗定时器是启动时建的。

### 控制桌宠的其它命令

```bash
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\send_cmd.py" show
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\send_cmd.py" hide
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\send_cmd.py" toggle
```

---

## 状态映射

### 9 个动作

素材名沿用原作者的动作语义，一一对应他仓库里的 `gif/1.gif`–`gif/7.gif`：

| 状态名 | 素材 | 原作者的语义 | 画面 | 一次性？ |
|---|---|---|---|---|
| `greet` | `waving.gif` | （图集 waving 行） | 挥手打招呼 | 播一次 1.1s |
| `thinking` | `think.gif` | `gif/7` **think** | 手扶头、蚊香眼，苦思 | 循环 |
| `tool` | `draw_continuous.gif` | `gif/4` **draw_continuous** | 埋头狂画，蚊香眼 | 循环 |
| `waiting` | `expect.gif` | `gif/2` **expect** | 睁大眼睛，期待地等 | 循环 |
| `done` | `smug.gif` | `gif/5` **smug** | 抱着画板，得意 | 播一次 1.8s |
| `error` | `failed.gif` | （图集 failed 行） | 垂头丧气 | 播一次 1.6s |
| `compact` | `pen_idle.gif` | `gif/3` **pen_idle** | 笔待机，环顾 | 播一次 2.4s |
| `idle` | `idle.gif` | `gif/1` **idle** | 半睁眼，呼吸眨眼 | 循环 |
| `sleep` | `sleep.gif` | 从 `gif/6` 抽的 15/16/17 帧 | 低头打瞌睡，头一点一点 | 循环 |

> **注意**：原作者的 `draw_continuous`（画得投入，蚊香眼）被他自己映射到 Codex 的「工作中 / running」，所以这里也用它表示 `tool`。蚊香眼在这个角色身上表达的是**专注到冒烟**，不是晕倒。

> **`sleep.gif` 是自己截的**：从 `draw_intermittent.gif`（32 帧）里抽出第 **15/16/17** 帧做成 3 帧循环，每帧 150ms、一轮 0.45 秒。原动画是 30ms/帧，3 帧循环只有 90ms 会像抽搐，放慢到 150ms 才像打瞌睡。想调快慢就改 `sleep.gif` 的帧延时，或者换另外几帧重做。

### 做 GIF 素材的坑（踩过两次）

用 Python 生成 GIF 时，**PIL 会把 RGBA 的 alpha 丢掉**，只认 `transparency=<索引>` 这一个参数。如果量化后的调色板里那个索引恰好被画面真正用到，透明就失效 —— 而且往往**只有部分帧坏掉**，看起来就是"最后几帧突然有黑背景"。

正确做法是：把**所有帧**拼起来统一量化出一套调色板（只用 0~254 号），再给每帧的透明像素统一涂上预留的 **255 号**，最后 `save(transparency=255)`。

改完素材**一定要跑一遍体检**：

```bash
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\check_assets.py"
```

它会逐帧查四角透明和透明像素占比 —— 只查第 0 帧是查不出这个问题的。全绿就没问题。

### 事件 → 动作

| 事件 | 什么时候触发 | 动作 |
|---|---|---|
| `SessionStart` | 会话开始 | `greet` 挥手 |
| `UserPromptSubmit` | 你发了消息 | `thinking` |
| `PreToolUse` | 要调用工具了 | `tool`（气泡显示工具名） |
| `PostToolUse` | 工具跑完了 | `thinking` |
| `PostToolUseFailure` | 工具报错了 | `error` |
| `Notification` | 需要你注意 / 等你授权 | `waiting` |
| `Stop` | Claude 回复完了 | `done` |
| `SubagentStop` | 子代理结束 | `thinking` |
| `PreCompact` | 压缩上下文前 | `compact` |
| `SessionEnd` | 会话结束 | `idle` |

**自动行为**：连续 `idleTimeoutMs`（默认 **5 分钟**）没有任何事件，会自动切到 `sleep` 睡着。

**一次性动作**播完会自己回到别的状态，规则写在各自的 `restoreTo` 里：

| 动作 | 播完回到 | 为什么 |
|---|---|---|
| `done` 任务完成 | `idle` 待机 | 干完活了，休息 |
| `greet` 会话开始 | `idle` 待机 | 刚启动时 Claude 并没在思考，显示「思考中」是错的 |
| `compact` 整理上下文 | `thinking` 思考中 | 压缩发生在干活中途，结束后 Claude 接着干 |
| `error` 出错 | `previous-or-idle` | 回到出错前的状态；没有就回待机 |

`pet_config.json` 顶层的 **`defaultState`** 决定桌宠启动瞬间显示什么（默认 `idle` 待机），也是所有「不知道该回哪」时的兜底。

### 为什么要有 `turn` 和 `working`（重要）

Hook 是以 `async: true` 后台执行的，**事件到达顺序不保证**。这会造成一个很难查的问题：

> `Stop`（回合结束）已经处理完、桌宠回到「待机」之后，一条**迟到的** `PostToolUse` 才写进 status.json。它会把桌宠重新推回「思考中」，而 `thinking` 是循环状态不会自己超时 —— 于是桌宠明明该待机，却一直显示「思考中」，直到 5 分钟后睡着。

修法是给状态和回合起点打标记：

```json
"states": {
  "thinking": { ..., "working": true },   // 标了 working 的，视为"Claude 正在干活"
  "tool":     { ..., "working": true }
},
"turn": {
  "startEvents": ["UserPromptSubmit", "SessionStart"],   // 回合开始 → 解除该会话的"安静"
  "endEvents":   ["Stop", "SessionEnd"]                  // 回合结束 → 标记该会话"安静"
}
```

规则：**某个会话的回合结束后，来自该会话的 `working` 事件一律忽略**，直到它开新回合。

- 按 `session_id` 区分，所以**多开会话互不影响** —— A 停止后，B 照常显示「工作中」
- 回合记账**不受 `cooldownMs` 影响**，否则两个会话几乎同时 Stop 时，第二个会被冷却挡掉，保护就失效了
- 被忽略的事件会记进 `pet.log`（`忽略迟到的工作中事件 ...`），排查时可查

如果你新增了别的"Claude 正在干活"的状态，记得也加上 `"working": true`。

### `workingTimeoutMs`：兜底

`turn` 那套依赖 `Stop` 事件。但如果你**按 ESC 打断了 Claude**，`Stop` 可能根本不触发 —— 那个会话永远不会被标记成"回合结束"，之后任何迟到事件都能把桌宠推回「思考中」。

所以还加了一道与事件无关的兜底：

```json
"workingTimeoutMs": 90000    // 停在"工作中/思考中"超过 90 秒且毫无事件 → 回待机
```

Claude 真在干活时 hook 会不停触发，不会撞上这个超时；撞上基本就是回合其实已经结束了。设 `0` 可关掉。

### 状态切换日志

`pet.log` 会记录**每一次状态变化和原因**，排查「状态不对」时先看它：

```
状态 idle -> greet　　（事件 SessionStart sid=final）
状态 greet -> idle　　（一次性动作播完）
状态 thinking -> tool　（事件 PreToolUse sid=5a6b3ee6）
状态 tool -> idle　　（工作态超过 90 秒无任何事件）
```

每 2 分钟还有一条心跳，记当前状态和「已结束回合的会话」集合：

```
心跳：当前状态=idle　已结束回合的会话=['5a6b3ee6', 'c171b532']
```

### 关于多开 Claude 会话

桌宠反映的是**所有会话的整体状态**，不区分是哪一个：

- A 会话停止了、B 会话还在干活 → 桌宠显示「工作中」（因为确实有活干）
- 所有会话都停了 → 才显示「待机」

每个会话的回合状态按 `session_id` 分开记账，互不干扰。如果你觉得这样容易混淆，可以在 `turn` 段里调整，或者干脆只用一个小蕾米对应一个会话。

### 想换图？改一行就行

```json
"tool": { "label": "工作中", "gif": "assets/gifs/think.gif", "loop": true, "priority": 50 }
```

改完在右键菜单点「重新读取配置」，不用重启。

---

## 目录结构

```
DESK.PET/
├── 启动小蕾米.bat         双击启动 / 唤出
├── pet.py                 桌宠主程序（PySide6，无边框透明置顶窗口）
├── pet_config.json        状态映射表 ← 想调什么改这里
├── send_cmd.py            给运行中的桌宠发指令（reload / show / hide / toggle）
├── check_assets.py        素材体检：逐帧检查每个 GIF 的透明是否正常
├── install_hooks.py       注册 / 卸载 Claude Code hook
├── status.json            运行时状态（hook 写，桌宠读），可随时删
├── pet.log                运行日志，排查问题时看这个
├── pet.pid                单实例锁（存当前桌宠的 PID），桌宠不在时可删
├── hooks/
│   └── pet_hook.py        hook 入口，每次工具调用被拉起一次
├── assets/gifs/           10 个 GIF（9 个在用；draw_intermittent.gif 保留作素材来源）
└── 参考/
    ├── 状态对照.png             9 个状态一图流
    ├── 原项目精灵图总览.png      原仓库 spritesheet.webp 展开
    ├── 原项目动作触发规则.md
    ├── 原项目-animation-triggers.json
    └── 素材来源与版权.md
```

---

## 工作原理

```
状态上报
  Claude Code 执行一步
        ↓ 触发 hook
  pet_hook.py  （读 stdin 的 JSON，把事件名 + 工具名写进 status.json）
        ↓ 原子写入（临时文件 + os.replace）
  status.json
        ↓ 桌宠每 150ms 轮询
  pet.py 查 pet_config.json 的 events 表 → 切到对应动作

生命周期
  SessionStart  → pet_hook.py 探测命名管道，没在跑就后台拉起 pet.py
  运行期间      → pet.py 每 3 秒扫一次进程表找 claude.exe
  连续 30 秒找不到 → app.quit()，小蕾米下班
```

Hook 注册成 `async: true`，在后台跑，**不占用 Claude Code 的时间**。
`pet_hook.py` 无论如何都 `exit 0` 且不写 stderr，不可能干扰 Claude Code 本身。
拉起桌宠用的是 `DETACHED_PROCESS`，hook 进程退出后桌宠继续活着。

每次调用约 65ms（Anaconda Python 启动 40ms + 读写文件），后台执行下感知不到。

---

## 管理 hook

```bash
# 查看当前装了什么
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\install_hooks.py" --status

# 卸载（只摘小蕾米的，不动你其它的 hook）
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\install_hooks.py" --uninstall

# 如果你的 Claude Code 版本不认 async 字段，改用同步模式
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\install_hooks.py" --no-async
```

安装器只**追加**，不会碰你已有的 hook（例如 ComfyUI 自启那个），改之前自动备份成 `settings.json.bak-<时间戳>`。

---

## 手动测试

```bash
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\hooks\pet_hook.py" --test done
D:\Anaconda\python.exe "D:\Claude project\DESK.PET\hooks\pet_hook.py" --test tool "Bash"
```

`--test` 后面既可以跟**状态名**（`done`/`error`/`waiting`/`sleep`…直接强制切换），也可以跟**事件名**（`Stop`/`Notification`…走映射表）。

---

## 依赖

- **PySide6** —— 已随 Anaconda 安装（`D:\Anaconda\python.exe`，PySide6 6.9.2）
- Windows / Claude Code 桌面版
- 无需联网，无需额外安装任何东西

换 Python 环境的话，改 `启动小蕾米.bat` 里的 `PYW` 路径，并重跑一次 `install_hooks.py`。

---

## 素材来源与版权

> ⚠️ **本项目是非官方同人衍生项目**，与米哈游、HoYoverse、《绝区零》无隶属、合作或背书关系。
> 素材**仅供个人学习与非商业交流**，不得商用。完整声明见 [`参考/素材来源与版权.md`](参考/素材来源与版权.md)。

`assets/gifs/` 里的动作素材来自《绝区零》官方活动页面，由 **[HanaAyane / 小蕾米](https://github.com/HanaAyane/remielle-codex-pet)** 整理并公开。本项目的 `waving.gif` 和 `failed.gif` 是从该项目的 `spritesheet.webp` 里导出的；`sleep.gif` 是在其 `draw_intermittent.gif` 基础上抽帧重制的。

按原作者 [ASSET-USAGE.md](https://github.com/HanaAyane/remielle-codex-pet/blob/main/ASSET-USAGE.md) 的要求署名：

```text
素材作者：HanaAyane / 小蕾米
来源：https://github.com/HanaAyane/remielle-codex-pet
说明：本素材基于《绝区零》公开素材，经 AI 辅助重绘、人工整理与编辑
许可范围：仅限非商业同人交流，详见 ASSET-USAGE.md 与 NOTICE.md
```

**本仓库的定位**：原作是给 Codex 用的素材包（不含运行器），本项目是**为 Claude Code 新写的运行器** ——
复用了它的动作语义（idle / expect / pen_idle / draw_continuous / smug / draw_intermittent / think）
和 `states` + `events` + `priority` + `cooldownMs` 的配置 schema，代码部分全部重写。

原始素材及角色版权归**米哈游 / HoYoverse** 所有，本项目不主张其版权，也未获得商业授权，
且**未对素材部分授予 MIT / Apache / CC0 等任何通用开源再授权**。程序代码部分可自由修改自用。

