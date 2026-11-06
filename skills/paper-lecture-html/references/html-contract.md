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
| table | columns、rows | caption、source |
| flow | steps | caption、source |
| details | summary、blocks | |

callout 的 kind 可为 question、insight、evidence 或 caution。正文使用普通文本，渲染器负责转义。公式 LaTeX 在 equation 块提供，KaTeX 在离线页面渲染。

figure 的 src 是相对 JSON 目录或绝对路径的本地 PNG、JPEG、WebP、GIF、SVG。脚本嵌入图片数据。marks 每项包含百分比坐标 x、y 和 label、text。x 与 y 范围为 0 到 100，位置对照原图校准。编号覆盖在图上，中文解释在图下按编号呈现。

table 的每行长度应与 columns 一致。flow 的 steps 是按信息流排列的字符串列表。details 包含同样的正文块，用于额外推导和术语补充。

每个 source 是紧邻内容显示的论文定位，如“论文 §3.1，Figure 2”。来源状态可以写入 source 或相应证据提示。教学示例在标题或正文中清楚注明。

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

检查单文件 HTML 在桌面和约 390 像素宽度下可读。长表格可水平滚动，公式具有溢出容器，图片按比例缩放。用浏览器打开后检查公式渲染错误、图片自然尺寸、导航、折叠、主题切换和打印布局。

输出包含连续正文与实际图片。图片取得失败时将缺口写明。HTML 文件内嵌字体、脚本和图片，正文与公式可离线读取。PDF 页面或图表截图中的字体仍按原图呈现。
