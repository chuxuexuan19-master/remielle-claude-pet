# 版权与声明

> **本项目是非官方同人衍生项目**，与米哈游、HoYoverse、《绝区零》及其官方活动不存在隶属、合作、赞助或背书关系。

---

## 一、上游来源与署名

本项目的**动作素材**并非原创，来自以下上游：

```text
素材作者：HanaAyane / 小蕾米
来源：https://github.com/HanaAyane/remielle-codex-pet
说明：本素材基于《绝区零》公开素材，经 AI 辅助重绘、人工整理与编辑
许可范围：仅限非商业同人交流，详见 ASSET-USAGE.md 与 NOTICE.md
```

| 上游文档 | 链接 |
|---|---|
| 源仓库 | https://github.com/HanaAyane/remielle-codex-pet |
| **素材使用说明（本项目必须遵守）** | https://github.com/HanaAyane/remielle-codex-pet/blob/main/ASSET-USAGE.md |
| 上游版权声明 | https://github.com/HanaAyane/remielle-codex-pet/blob/main/NOTICE.md |

### 本项目的性质

上游仓库是**给 Codex 用的素材包**，本身**不含运行器**（运行器由 OpenAI Codex 自带）。
本项目是**为 Claude Code 新写的运行器**，对上游的复用仅限于：

- **动作语义**：`idle` / `expect` / `pen_idle` / `draw_continuous` / `smug` / `draw_intermittent` / `think`
- **配置 schema**：`states` + `events` + `priority` + `cooldownMs`
- **动作素材文件**：`assets/gifs/` 下的 GIF

**代码部分全部重写**，与上游无代码继承关系。

### 本项目对素材做过的改动（按上游 ASSET-USAGE 第 4 条主动披露）

| 文件 | 改动 |
|---|---|
| `waving.gif`、`failed.gif` | 从上游 `spritesheet.webp` 中导出（上游未单独提供这两个动作） |
| `sleep.gif` | 在上游 `draw_intermittent.gif` 基础上**抽第 15/16/17 帧**重制的 3 帧循环 |
| `assets/gifs/` 其余 7 个 | 直接使用上游文件，未改动 |

---

## 二、原始素材来源

本项目部分角色视觉、动作参考及原始素材来源于米哈游官方活动：

- 来源：[《绝区零》官方活动页面](https://act.mihoyo.com/zzz/event/e20260717reserve-pvy5cf/index.html)
- 同人规则：[《绝区零》同人周边运行指引（大陆地区）V1.0](https://m.miyoushe.com/zzz/#/article/55737410)
- 相关规则参考：[《绝区零》游戏使用许可及服务协议](https://fastcdn.mihoyo.com/static-resource-v2/2025/12/30/f91a0c8796a63ce69bb054d096371593_7574548664798296571.pdf)

原始素材及其角色、图像、动画、商标和其他相关知识产权**归米哈游及其他相关权利人所有**。
本项目不主张拥有上述原始素材的版权，也不表示已获得米哈游或其他权利人的商业授权。

## 三、衍生内容与 AI 辅助

本项目中的部分动作经过人工整理、编辑、逐帧处理和图集编排，上游项目使用 Codex AI 辅助制作衍生动作素材。
该过程**不改变原始素材的权利归属**，也不将原始素材的权利转移给任何一方。

本项目作者仅对**自己实际创作的代码、文档、排版和原创编辑部分**主张相应权利；
任何基于第三方素材形成的衍生部分，仍受原始权利人的权利和适用规则约束。

## 四、使用边界

- 本项目仅用于**个人学习、非商业展示与技术研究**。
- **不得**将含有上述衍生素材的桌宠包、GIF、精灵图或宣传图**出售、商业授权或打包销售**。
- **不得**移除来源和版权声明，**不得**暗示获得米哈游官方认可、赞助或授权。
- **本项目未对素材部分授予 MIT、Apache、CC0 等任何通用开源再授权**，也不得将上游素材重新包装后
  以自己的原创素材或其他通用授权发布（上游 ASSET-USAGE 第 6 条明令禁止）。
- **程序代码部分**可自由修改自用。

## 五、权利人联系

如权利人认为本仓库中的某项内容不适合公开，请通过 GitHub 仓库渠道提出，我们会立即移除或调整。

---

*本文件与 `参考/素材来源与版权.md` 内容一致，根目录这份是为了让访客第一眼就能看到。*
