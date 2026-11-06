# MY-SKILL-REPO

个人 Codex Skills 集合，用于保存、复用和维护可重复执行的工作流。

## Skills

| Skill | 功能 | 文档 |
|---|---|---|
| [`analyze-research-paper`](skills/analyze-research-paper) | 从第一性原理分析论文，覆盖任务、挑战、insight、novelty、方法流程、张量维度、公式、训练/推理和消融实验 | [详细说明](docs/analyze-research-paper.md) |
| [`contribute-agent-oss`](skills/contribute-agent-oss) | 用证据门禁完成 AI Agent 开源项目筛选、Issue 与七维架构分析、方案对齐、实现验证、PR/review 跟进和面试叙事 | [Skill 说明](skills/contribute-agent-oss/SKILL.md) |
| [`paper-lecture-html`](skills/paper-lecture-html) | 根据论文制作带原图、中文注释与公式的 HTML 图文精讲 | [Skill 说明](skills/paper-lecture-html/SKILL.md) |

## 安装

克隆仓库：

```bash
git clone git@github.com:Holysmiles/MY-SKILL-REPO.git
cd MY-SKILL-REPO
```

安装单个 Skill。

PowerShell：

```powershell
Copy-Item -Recurse .\skills\analyze-research-paper "$env:USERPROFILE\.codex\skills\"
Copy-Item -Recurse .\skills\contribute-agent-oss "$env:USERPROFILE\.codex\skills\"
Copy-Item -Recurse .\skills\paper-lecture-html "$env:USERPROFILE\.codex\skills\"
```

macOS/Linux：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/analyze-research-paper "${CODEX_HOME:-$HOME/.codex}/skills/"
cp -R skills/contribute-agent-oss "${CODEX_HOME:-$HOME/.codex}/skills/"
cp -R skills/paper-lecture-html "${CODEX_HOME:-$HOME/.codex}/skills/"
```

安装后刷新 Skill 列表或新建 Codex 会话。

## 快速使用

```text
$paper-lecture-html 请精讲我提供的论文，结合原图、公式与实验，生成中文 HTML 讲稿。
```

```text
$contribute-agent-oss 请帮我筛选一个活跃的 AI Agent 开源项目，
找出可在两周内完成的贡献方向，并从分析和方案设计开始推进。
```

```text
$analyze-research-paper 请分析我提供的论文，重点解释 Methodology、
张量维度、核心公式和 Ablation Study。
```

Skill 只把用户提供的论文作为论文事实来源。论文未报告的信息会标记为“未报告”，不会用常见实现或主观猜测补齐。
