---
name: analyze-research-paper
description: Analyze a user-provided academic paper from first principles in Chinese, with evidence-grounded coverage of task, challenges, inspiration, insights, novelty, limitations, motivation, methodology, tensor dimensions, equations, training/inference, terminology, and ablation studies. Use when the user asks for a rigorous paper walkthrough, method reconstruction, architecture or pipeline analysis, formula intuition, dimension tracing, novelty analysis, or ablation interpretation from a PDF, LaTeX source, or pasted paper text.
---

# Analyze Research Paper

## Goal

Reconstruct what problem the paper solves, why its method follows from that problem, and how each claimed contribution is supported. Write in Chinese and make the report sufficient for a reader who will not return to the paper.

## Workflow

1. Identify the exact user-provided paper source. Prefer the explicitly named file or attachment. If no paper content is available, request a PDF or text and stop.
2. Read the method, architecture figures, equations, implementation details, experiments, ablations, tables, appendices, and supplementary material before drafting. Map semantic sections when numbering differs from “Section 2” or “Section 4(c)”.
3. Build a private evidence ledger for every material claim:
   - `论文明确` for statements directly reported by the paper.
   - `严格推导` for consequences mechanically derivable from reported equations or architecture.
   - `分析判断` for reasoned interpretation or extrapolation.
   - `未报告` when the source cannot determine the answer.
4. Build a dimension ledger for the complete pipeline. Record each tensor's meaning, shape, producing operation, consuming operation, and source evidence. Use symbolic dimensions when exact numbers are absent. Never invent channel counts, token counts, resolutions, batch sizes, or broadcasting rules.
5. Separate three concepts:
   - Inspiration: observation or prior mechanism that could lead to the idea.
   - Insight: the causal proposition explaining why a design should work.
   - Novelty: the concrete mechanism the authors actually implement.
6. Test claimed insights against ablations. Distinguish direct support, partial support, confounded evidence, and no evidence. Do not convert correlation or a single benchmark gain into a universal claim.
7. Explain equations by their information-processing role, optimization effect, inductive bias, or physical meaning. Do not merely translate symbols.
8. Follow [references/analysis-contract.md](references/analysis-contract.md) exactly for the report structure, formula rendering, dimension rules, and final checks.

## Source Discipline

- Base paper-specific facts only on user-provided material.
- Do not browse for missing content unless the user explicitly permits external sources.
- Cite evidence inline using the paper's actual section, equation, figure, table, algorithm, or page identifier where available.
- Mark reconstructed author motivation as `分析判断`; do not present it as the authors' stated inspiration unless the paper says so.
- Preserve ambiguity. State what additional implementation detail is needed to resolve an unknown dimension or operation.

## Analysis Priorities

Spend the most detail on the methodology and ablation evidence. Compress generic background. For every module, connect:

`problem pressure -> insight -> mechanism -> tensor/data transformation -> training signal -> ablation evidence -> limitation`

## Completion Check

Before returning the report, verify that:

- Every requested section exists and uses the required novelty-chain syntax.
- Every pipeline edge has a valid or explicitly unknown shape.
- Concatenation, addition, matrix multiplication, attention, reshaping, and up/downsampling are dimensionally consistent.
- Training objectives, labels, prediction-to-target alignment, and inference outputs are distinguished.
- Correctness at training time is not confused with benchmark correctness at evaluation time.
- Formula Markdown source and rendered preview are both present for every core equation.
- All unsupported values and causal claims have been removed or labeled.
