# HTML 交付数据

`scripts/render_lecture.py` 使用 Python 标准库运行。打包的 KaTeX 来自 npm 官方分发，归档校验值与版本见 `assets/katex/version.txt`，许可见同目录 LICENSE。

## 顶层数据

UTF-8 JSON 包含 `title`、`subtitle`、`audience`、`source`、`sections`。后三个说明字段可省略。`source` 使用普通文本描述原论文，章节内的出处就近记录。

`sections` 是非空列表。每节包含唯一的 `id`、`title`、可选的 `question` 和 `blocks`。id 使用字母、数字、下划线或连字符。标题使用具体读者问题或内容名称。

## 正文块

| type | 必填字段 | 可选字段 |
|---|---|---|
| paragraph | text | source |
| callout | text | title、kind、source |
| list | items | source |
| equation | latex、meaning | source |
| figure | src、alt、caption | source、marks |
| walkthrough | src、alt、caption、steps | source、citations |
| table | columns、rows | caption、source |
| flow | steps | caption、source |
| details | summary、blocks | |

callout 的 kind 可为 question、insight、evidence 或 caution。正文使用普通文本，渲染器负责转义。公式 LaTeX 在 equation 块提供，KaTeX 在离线页面渲染。

figure 的 src 是相对 JSON 目录或绝对路径的本地 PNG、JPEG、WebP、GIF、SVG。脚本嵌入图片数据。marks 每项包含百分比坐标 x、y 和 label、text。x 与 y 范围为 0 到 100，位置对照原图校准。编号覆盖在图上，中文解释在图下按编号呈现。

table 的每行长度应与 columns 一致。flow 的 steps 是按信息流排列的字符串列表。details 包含同样的正文块，用于额外推导和术语补充。

每个 source 是紧邻内容显示的论文定位，如“论文 v2 §3.1，Figure 2”。所有正文块也可带 citations 数组，每项含 label 与绝对 HTTP(S) url，生成可点击链接。外部引用不在打开页面时自动加载，正文、图片和公式仍可离线阅读。来源状态可以写入 source 或相应证据提示。教学示例在标题或正文中清楚注明。

## 初学者阅读布局

借鉴参考材料 `skill2.md` 的先图解再答疑、首次展开缩写、分层阅读和自测。用现有块组织，不依赖固定漫画人物或配色。标题优先写读者想弄清的事；同一小块放一个概念或操作。

| 阅读任务 | HTML 怎么排 |
|---|---|
| 第一屏先建立全局 | 用一段具体场景说明输入、目标和成功条件。用 `flow` 摆出少量顺序动作，或用总图放大关键区域。若流程由讲解者归纳，在 `caption` 和 `source` 标出身份和依据。 |
| 遇到陌生词时马上能继续 | 第一次出现时给英文全称、中文含义和当前作用。符号在首次参与计算时解释。必要时在相邻 `paragraph` 补一条先修知识并注明来源。 |
| 从真实疑问过渡到细节 | 用 `callout` 的 `question` 或章节 `question` 提问，紧接回答。把“为什么”“这个数字从哪来”之类问题接到一个操作、原图位置、算例或对照。用 `evidence` 和 `caution` 呈现有依据的判断和边界。 |
| 在主线与深读之间切换 | 使用 `details` 包装可暂缓的证明或变体，并在标题写清展开后会读到什么。关键假设、公式所用符号、核心机制与证据判断留在可见正文或对应的读图步骤内。 |
| 确认读者能独立解释 | 在结尾安排少量自测，可覆盖任务或机制、一次代入、实验能支持什么。用 `details` 折叠答案，附推理及原文位置，或明确指向上文已引用的算例与证据。 |

纯教学引导无需假装是论文措辞。含技术断言的图解步骤、问答、类比、选读和自测答案按 [证据规则](review-method.md#证据与解释的对应规则) 就近标注。架构因果、设计动机和实验归因分别核对证据。

## Review 版图与公式详解

以下是讲稿内容的验收要求，使用现有 JSON 块组合编排。

- **每张图都配相邻解释。** `caption` 简述主题和原图、裁剪或重绘身份，`source` 标作品版本与真实图号、页码，已知稳定链接时加入 `citations`。解释说明图回答什么问题、要先看哪里、关键视觉元素的含义、能得出什么以及条件。正文用相邻 `paragraph`、`callout` 或当前步骤 `blocks` 承载，注释用于精确指图。
- **架构图、实验图按图型读取。** 流程图逐段解释输入、箭头或分支所走的操作、输出及下游用途。统计图指出坐标、单位、图例、对照和关键读数，说明指标方向、误差条含义或不确定性信息是否缺失。对截图中的每个实际讲解面板保留并解释必要的标尺和图例。说明图适用的版本、数据或评测条件。
- **每个公式都配解释。** 公式前说明它解决的子问题，`meaning` 或相邻正文讲清未定义的符号和索引、输入与输出、关键运算与使用位置。适用时说明形状、单位、求和或归一化轴、符号取值范围和约束。原文公式写明版本、编号或章节，讲解推导、记号改写和教学代值明确标记。
- **核心公式能随手验算。** 展开关键等式或选一组明确参数走一遍计算，解释结果为何成立，必要时说明公式与图中模块的对应。简单公式可在 `meaning` 内讲全。核心上下文可见，较长推导用 `details` 收起。连续公式可以共享已经写明的符号表和假设。

## 同图分步讲解

复杂架构或需要逐步指向的图使用 walkthrough。steps 是非空列表。每步含 title、blocks，可含 marks、source 和 citations。marks 格式与 figure 相同，只显示当前步骤的编号；blocks 使用 paragraph、equation、callout、list、table 或 details。避免嵌套 walkthrough。每步解决一个问题，正文能解释图中编号所指之处。

```json
{
  "type": "walkthrough",
  "src": "assets/model.png",
  "alt": "论文模型架构图",
  "caption": "原论文架构图，中文编号由讲解者添加",
  "source": "所读版本、章节与真实图号",
  "citations": [{"label": "打开原论文", "url": "https://example.org/paper.pdf#page=3"}],
  "steps": [
    {
      "title": "输入如何成为表示",
      "marks": [{"x": 30, "y": 75, "label": "1", "text": "当前输入的位置，坐标需按实际图像校准"}],
      "blocks": [{"type": "paragraph", "text": "以论文真实内容写出这一步的连续讲解。"}]
    },
    {
      "title": "表示在哪里交互",
      "marks": [{"x": 55, "y": 40, "label": "2", "text": "当前交互模块，坐标需按实际图像校准"}],
      "blocks": [{"type": "paragraph", "text": "解释本步如何承接上一步，以及输出送往哪里。"}]
    }
  ]
}
```

页面提供步骤按钮、上一步/下一步、状态提示和图片放大。打印时展示全部步骤正文，隐藏会相互遮挡的图上编号，保留各步文字注释。数值例子先在段落里声明配置；不能把示例值伪装成论文默认设置。

## 最小输入

```json
{
  "title": "某论文图文精讲",
  "subtitle": "从任务到设计理由与实验证据",
  "audience": "具备机器学习基础",
  "source": "用户提供的论文正文与附录",
  "sections": [
    {
      "id": "problem",
      "title": "模型需要保留什么信息",
      "question": "输入、输出和成功条件分别是什么？",
      "blocks": [
        {"type": "paragraph", "text": "在这里写基于论文的完整解释。"},
        {"type": "flow", "steps": ["输入", "关键变换", "输出"]},
        {"type": "callout", "kind": "evidence", "title": "证据", "text": "说明该结论的来源和条件。", "source": "论文实际章节或图表"}
      ]
    }
  ]
}
```

此示例展示数据结构。实际交付前填入真实论文内容，并删除未使用的示例内容。

## 页面验收

检查单文件 HTML 在桌面和约 390 像素宽度下可读。长表格可水平滚动，公式具有溢出容器，图片按比例缩放。用浏览器打开后检查公式渲染错误、图片自然尺寸、导航、折叠、主题切换和打印布局。含 walkthrough 时逐步点击，确认图上编号、步骤正文、进度、首尾禁用状态同步，放大图保留当前注释，打印包含全部步骤。

输出包含连续正文与实际图片。图片取得失败时将缺口写明。HTML 文件内嵌字体、脚本和图片，正文与公式可离线读取。PDF 页面或图表截图中的字体仍按原图呈现。

逐项对照实际插入的图和公式，检查是否具备相邻详解、可复核定位和与结论对应的条件说明。用前作对照检查方法差异、论据与创新主张是否一一对应。误差、缺失项和无法比较的条件随相关图表呈现。
