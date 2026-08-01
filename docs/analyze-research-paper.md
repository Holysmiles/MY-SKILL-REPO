# analyze-research-paper

`analyze-research-paper` 用于从第一性原理重建论文的完整设计逻辑：

```text
问题约束
  -> 传统方法的失败机制
  -> 核心 insight
  -> 具体方法与张量变换
  -> 训练信号
  -> 实验及消融证据
  -> 适用边界
```

## 适用任务

- 系统精读论文，并生成无需反复查阅原文的中文分析。
- 重建模型 pipeline，追踪输入、特征和输出的张量形状。
- 解释核心公式的信息处理、优化或物理含义。
- 区分 inspiration、insight 与 novelty。
- 分析训练输入、监督信号、预测对齐和推理输出。
- 判断消融实验能支持哪些因果结论。
- 识别复杂场景、噪声、偏移、小样本和模态缺失下的潜在失效。

## 输入要求

调用时提供下列任一种内容：

- 上传的论文 PDF；
- 可读取的论文 PDF 或 LaTeX 文件路径；
- 粘贴的论文正文；
- 明确指定的论文文件及重点章节。

没有论文内容时，Skill 会先要求提供论文，不会仅根据标题或一般领域知识生成分析。

## 输出内容

报告固定覆盖：

1. Task
2. Challenge
3. Inspiration、Insight 与 Novelty
4. Potential Flaw
5. 追问式 Motivation
6. Methodology、张量流程、公式、训练/推理与 Ablation
7. 论文新术语和专有概念

其中 Methodology 和 Ablation 是分析主体。若论文的章节编号不是 Section 2 或 Section 4(c)，Skill 会定位语义上对应的章节并注明真实编号。

## 证据等级

| 标签 | 含义 |
|---|---|
| `[论文明确]` | 论文直接报告，并尽量附章节、公式、图、表、算法或页码 |
| `[严格推导]` | 可由论文给出的结构、公式或尺寸机械推出 |
| `[分析判断]` | 基于论文证据的解释、批判或外推 |
| `[未报告]` | 论文信息不足，无法可靠确定 |

这些标签用于防止把分析者推断写成作者结论，也防止用常见网络配置填补论文缺失细节。

## 张量维度规则

每一步按以下形式输出：

```text
Input: [B, C, H, W]
  -> operation
Output: [B, C', H', W']
```

具体数值必须满足以下条件之一：

1. 论文明确给出；
2. 能从卷积、采样、拼接、矩阵乘法、注意力或 reshape 规则唯一推出。

信息不足时保留符号维度，并说明缺少哪些配置。例如：

```text
Input: [B, C, H, W]
  -> convolution
Output: [B, C', H', W']

[未报告] C'、H'、W' 无法唯一确定，需要卷积核、步幅、填充和输出通道配置。
```

## 公式输出

核心公式同时给出 Markdown 源码和渲染 Preview，然后解释它如何改变信息流、优化方向或模型归纳偏置。

**Markdown 源码**

```markdown
$$
\mathcal{L}=\mathcal{L}_{\mathrm{task}}+\lambda\mathcal{L}_{\mathrm{reg}}
$$
```

**Preview**

$$
\mathcal{L}=\mathcal{L}_{\mathrm{task}}+\lambda\mathcal{L}_{\mathrm{reg}}
$$

这里的核心不是“两个损失相加”，而是让任务拟合与解空间约束形成可控权衡；`$\lambda$` 决定正则机制对参数更新方向的相对影响。

## 消融判断

每个消融项都检查：

- 唯一改变了什么；
- 其他条件是否受控；
- 指标变化支持哪个机制主张；
- 是否存在参数量、计算量、训练预算或多模块同时变化的混杂；
- 结论属于直接支持、部分支持、证据受混杂还是未提供证据。

单个数据集上的性能提升不会自动被解释为普遍有效，多模块同时变化也不会被归因给其中一个模块。

## 调用示例

### 完整分析

```text
$analyze-research-paper 请完整分析 paper.pdf。假设我不再阅读原文，
重点展开方法流程、张量形状、核心公式和消融证据。
```

### 复现导向

```text
$analyze-research-paper 请分析 model.tex 和论文 PDF，建立逐层维度账本。
所有具体尺寸必须附论文依据或严格推导过程；不能确定的地方列出缺失配置。
```

### 批判性分析

```text
$analyze-research-paper 请重点检查作者的 novelty 是否得到消融实验支持，
并分析噪声、分布偏移、小样本和模态缺失时可能出现的失效机制。
```

### 指定章节

```text
$analyze-research-paper 只分析 Methodology 和 Ablation Study，
但保留 Task、Insight 与 Novelty 的最小必要上下文。
```

## 文件结构

```text
analyze-research-paper/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── references/
    └── analysis-contract.md
```

- `SKILL.md`：触发条件、分析工作流与完成检查。
- `agents/openai.yaml`：Skill 列表中的名称、简介和默认调用提示。
- `references/analysis-contract.md`：完整分析规范，也可作为独立 Prompt 使用。
