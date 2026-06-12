# ML-KEM 时间泄漏检测

基于统计检验和机器学习的 ML-KEM 解封装时间侧信道筛查实验。

本仓库提供一套可复现的软件计时实验，用于观察 `pqcrypto` 中 ML-KEM
解封装实现面对有效密文和无效密文时，是否表现出稳定、可分类的执行时间差异。
它适合作为课程论文、实验报告或实现级侧信道筛查的基础工程。

> 重要边界：本项目不是密钥恢复攻击，也不能证明某个实现“没有侧信道风险”。
> 它只回答一个更窄的问题：在当前软件计时条件、当前输入构造策略和当前分析阈值下，
> 是否检测到可区分的时间信号。

## 项目能做什么

- 采集 ML-KEM 解封装时间数据。
- 对比有效密文与多种无效密文策略。
- 使用统计检验和分组机器学习评估可区分性。
- 使用正对照验证检测管线能识别已知时间信号。
- 支持 ML-KEM-512、ML-KEM-768、ML-KEM-1024。
- 生成 CSV、JSON、Markdown 报告和论文图表。

![实验架构](docs/figures/overall_architecture.png)

## 项目结构

```text
.
├── README.md
├── RUN_EXPERIMENTS_README.md
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── docs/
│   ├── PAPER_DRAFT.md
│   ├── paper.tex
│   ├── paper.pdf
│   ├── references.bib
│   └── figures/
├── scripts/
│   ├── run_paper_experiments.sh
│   ├── run_local_experiments.sh
│   ├── generate_figures.py
│   ├── build_variant_figures.py
│   ├── plot_mde_sweep.py
│   └── aggregate_paper_stats.py
├── src/
│   └── mlkem_leakage/
│       ├── collector.py
│       ├── analysis.py
│       ├── paper_artifacts.py
│       ├── palette.py
│       └── cli.py
└── tests/
    └── test_collector.py
```

实验生成结果会写入 `results/`。该目录已被 Git 忽略，因为多轮实验输出可能很大。

## 快速开始

创建虚拟环境并安装项目：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

运行测试：

```bash
.venv/bin/python -m pytest -q
```

预期结果：

```text
5 passed
```

运行一个小规模冒烟实验：

```bash
.venv/bin/python -m mlkem_leakage.cli \
  --output-dir results/smoke_test \
  --samples-per-class 40 \
  --repetitions 5 \
  --groups 5 \
  --warmup 20 \
  --variants 768 \
  --invalid-strategies single_bit
```

运行默认实验：

```bash
.venv/bin/python -m mlkem_leakage.cli
```

默认输出目录：

```text
results/latest/
```

## 实验设计

每次运行都会生成新的 ML-KEM 密钥对，创建基础密文，派生配对的无效密文，
随机打乱测量顺序，并使用 `time.perf_counter_ns()` 记录解封装时间。

实验采集两个场景：

| 场景 | 含义 | 作用 |
| --- | --- | --- |
| `real` | 直接测量有效密文与无效密文的解封装时间 | 检测实现级时间差异 |
| `positive_control` | 使用同一条管线，但给无效密文额外加入人为延迟 | 确认采集和分析管线能识别已知信号 |

正对照非常关键。如果正对照失败，那么真实场景中的阴性结果并不充分，
因为检测器可能只是对当前参数设置不够敏感。

## 密文构造策略

无效密文始终保持原始密文长度不变，使实验聚焦于解封装行为，
而不是简单的长度错误拒绝路径。

| 策略 | 说明 |
| --- | --- |
| `single_bit` | 通过 `group_id` 和 SHA-256 确定位置，翻转一个确定性 bit |
| `byte_flip` | 翻转一个确定性字节中的全部 bit |
| `random_bytes` | 使用等长的确定性伪随机字节替换密文 |
| `zero` | 使用等长全零字节替换密文 |

生成的 CSV 文件中使用以下标签：

| 标签 | 含义 |
| ---: | --- |
| `0` | 有效密文 |
| `1` | 无效密文或扰动密文 |

## 分析管线

对于每个聚合样本，采集器会重复执行多次解封装，并把时间序列汇总成特征。
当前特征集合包括：

```text
mean_ns, median_ns, std_ns, min_ns, max_ns,
p10_ns, p90_ns, iqr_ns, mad_ns,
trimmed_mean_ns, skewness, kurtosis, cv
```

分析阶段使用以下方法：

| 方法 | 作用 |
| --- | --- |
| Welch t 检验 | 比较两类样本均值，不要求方差相等 |
| Mann-Whitney U 检验 | 比较两类样本的秩分布 |
| Kolmogorov-Smirnov 检验 | 比较一维分布整体差异 |
| Cohen's d | 衡量实际效应量 |
| 置换检验 | 检查模型分数是否高于标签打乱后的基线 |
| 分组训练/测试切分 | 确保同一基础密文组不会同时出现在训练集和测试集 |

机器学习模型：

| 模型 | 说明 |
| --- | --- |
| `logistic_regression` | 带稳健缩放的线性基线 |
| `linear_svm` | 带稳健缩放的线性间隔分类器 |
| `random_forest` | 非线性树模型，也用于生成特征重要性 |
| `hist_gradient_boosting` | 用于检查非线性结构的梯度提升基线 |

主要分类指标是平衡准确率。随机猜测的期望值接近 `0.5`。

## 泄漏判定规则

`real` 场景只有在以下条件全部满足时，才报告 `leakage_detected: true`：

| 条件 | 阈值 |
| --- | ---: |
| 最佳分组平衡准确率 | `>= 0.65` |
| Welch p 值 | `< 0.01` |
| Cohen's d 绝对值 | `>= 0.2` |

正对照管线只有在以下条件同时满足时，才报告通过：

| 条件 | 阈值 |
| --- | ---: |
| 最佳分组平衡准确率 | `>= 0.90` |
| Welch p 值 | `< 0.001` |

这些阈值是本项目采用的保守判定规则，不是通用的密码学安全认证标准。

## 命令行用法

查看完整命令行帮助：

```bash
.venv/bin/python -m mlkem_leakage.cli --help
```

安装后的命令行入口：

```bash
mlkem-leakage --help
```

主要参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `--output-dir` | `results/latest` | 生成结果目录 |
| `--samples-per-class` | `400` | 每个标签的聚合样本数量 |
| `--repetitions` | `50` | 每个聚合样本包含的解封装重复次数 |
| `--groups` | `40` | 独立基础密文组数量 |
| `--warmup` | `500` | 正式测量前的预热解封装次数 |
| `--seed` | `20260602` | 随机顺序和数据切分使用的种子 |
| `--control-delay-ns` | `20000` | 正对照人为延迟，单位为纳秒 |
| `--variants` | `768` | 一个或多个参数集，可选 `512 768 1024` |
| `--invalid-strategies` | `single_bit` | 一个或多个无效密文构造策略 |
| `--delay-sweep` | 无 | 对正对照运行多档延迟灵敏度扫描 |

同时比较多个参数集和多种无效密文策略：

```bash
.venv/bin/python -m mlkem_leakage.cli \
  --output-dir results/comparison_run \
  --variants 512 768 1024 \
  --invalid-strategies single_bit byte_flip random_bytes zero
```

运行延迟灵敏度扫描：

```bash
.venv/bin/python -m mlkem_leakage.cli \
  --output-dir results/delay_sweep_run \
  --samples-per-class 120 \
  --repetitions 20 \
  --groups 20 \
  --delay-sweep 500 1000 2000 5000 10000 20000
```

## 输出文件

单次运行会写入以下文件：

| 文件 | 说明 |
| --- | --- |
| `REPORT.md` | 简短的人类可读结果摘要 |
| `summary.json` | 参数、环境元数据和两个场景的完整结果 |
| `real_traces.csv` | 真实场景的聚合样本 |
| `real_raw_timings.csv` | 真实场景的逐次重复计时 |
| `real_analysis.json` | 真实场景的统计检验和模型结果 |
| `real_timing_histogram.png` | 真实场景计时分布图 |
| `real_feature_importance.png` | 真实场景的随机森林特征重要性图 |
| `positive_control_traces.csv` | 正对照场景的聚合样本 |
| `positive_control_raw_timings.csv` | 正对照场景的逐次重复计时 |
| `positive_control_analysis.json` | 正对照场景的统计检验和模型结果 |
| `positive_control_timing_histogram.png` | 正对照计时分布图 |
| `positive_control_feature_importance.png` | 正对照随机森林特征重要性图 |

论文级多轮实验建议用 `summary.json` 制作表格，用 `*_traces.csv` 做进一步诊断。

## 论文级复现实验

完整实验驱动脚本：

```bash
source .venv/bin/activate
LOKY_MAX_CPU_COUNT=8 MLKEM_PERMUTATIONS=20 bash scripts/run_paper_experiments.sh
```

默认实验矩阵：

| 参数 | 默认值 |
| --- | ---: |
| 独立轮次 | `5` |
| 参数集 | `512 768 1024` |
| 无效密文策略 | `single_bit byte_flip random_bytes zero` |
| 每类样本数 | `400` |
| 每个样本重复次数 | `50` |
| 基础密文组数 | `60` |
| 预热次数 | `500` |

完整默认矩阵会生成 `60` 个完成的运行目录：

```text
5 轮 x 3 个参数集 x 4 种策略 = 60 个 summary.json
```

快速验证可以缩小矩阵：

```bash
RUNS=1 \
SAMPLES_PER_CLASS=20 \
REPETITIONS=5 \
N_GROUPS=5 \
VARIANTS="768" \
INVALID_STRATEGIES="single_bit" \
MLKEM_PERMUTATIONS=5 \
bash scripts/run_paper_experiments.sh
```

论文实验脚本会写入：

```text
results/paper_runs/
results/paper_artifacts/
```

论文图表和质量报告包括：

| 文件 | 说明 |
| --- | --- |
| `DATA_QUALITY_REPORT.md` | 数据完整性和质量审计报告 |
| `data_quality.json` | 机器可读审计细节 |
| `real_distribution.png` | 跨轮真实场景计时分布 |
| `positive_control_distribution.png` | 正对照计时分布 |
| `model_accuracy_comparison.png` | 模型平衡准确率对比 |
| `run_stability.png` | 跨轮时间差稳定性 |
| `trace_order_diagnostic.png` | 采集顺序漂移诊断 |

更详细的异地运行说明见 `RUN_EXPERIMENTS_README.md`。

## 环境变量

分析脚本和实验脚本提供以下常用调节项：

| 变量 | 默认值 | 说明 |
| --- | ---: | --- |
| `MLKEM_PERMUTATIONS` | `200` | 模型显著性置换检验次数 |
| `MLKEM_N_JOBS` | `1` | 支持并行的模型和检验使用的 scikit-learn 并行度 |
| `LOKY_MAX_CPU_COUNT` | 未设置 | 可选 joblib CPU 数量提示，macOS 上可减少 warning |
| `PYTHON` | `.venv/bin/python` | 论文脚本使用的 Python 解释器 |
| `OUTPUT_ROOT` | `results/paper_runs` | 多轮实验输出根目录 |
| `RUNS` | `5` | 独立重复运行次数 |
| `SAMPLES_PER_CLASS` | `400` | 每个标签的聚合样本数量 |
| `REPETITIONS` | `50` | 每个聚合样本的解封装重复次数 |
| `N_GROUPS` | `60` | 论文实验中的基础密文组数量 |
| `WARMUP` | `500` | 预热解封装次数 |
| `VARIANTS` | `512 768 1024` | 论文脚本使用的参数集 |
| `INVALID_STRATEGIES` | `single_bit byte_flip random_bytes zero` | 论文脚本使用的无效密文策略 |

## 复现注意事项

为了得到更稳定的计时数据，建议：

- 使用外接电源运行，避免低电量模式。
- 关闭浏览器、同步客户端、编译任务、下载任务和备份任务。
- 长时间运行前，让机器处于相对稳定的温度状态。
- 采集期间避免大量磁盘和网络活动。
- 保留原始 CSV 和 JSON 汇总，方便重新审计结果。
- 只有正对照通过时，才谨慎解释真实场景的阴性结果。

软件计时天然带有噪声。本项目保留离群值，而不是静默删除它们，
因为调度噪声和瞬时系统状态本身就是测量环境的一部分。

## 开发

运行测试：

```bash
.venv/bin/python -m pytest -q
```

直接查看模块帮助：

```bash
.venv/bin/python -m mlkem_leakage.cli --help
.venv/bin/python -m mlkem_leakage.paper_artifacts --help
```

主要实现文件：

| 文件 | 职责 |
| --- | --- |
| `src/mlkem_leakage/collector.py` | 密钥生成、密文扰动、计时采集和 CSV 写入 |
| `src/mlkem_leakage/analysis.py` | 统计检验、机器学习模型、绘图和泄漏判定规则 |
| `src/mlkem_leakage/cli.py` | 单次运行和多参数集运行的命令行编排 |
| `src/mlkem_leakage/paper_artifacts.py` | 数据质量审计和多轮实验图表生成 |
| `tests/test_collector.py` | 密文扰动策略和样本平衡性的单元测试 |

## 当前范围和限制

- 实验目标是所选 `pqcrypto` ML-KEM 绑定的时间行为。
- 标签区分的是有效密文和无效密文，不是私钥 bit。
- 项目没有实现自适应选择密文攻击。
- 项目没有尝试恢复密钥。
- 单一操作系统、CPU、Python 版本或库构建上的结果不应直接泛化。
- 未检测到泄漏只能表述为“在当前设置下未检测到”，不能表述为“已证明安全”。

## 报告中的建议表述

可以谨慎表述为：

> 在本软件计时实验条件下，针对所测试的 ML-KEM 参数集和无效密文构造策略，
> 本项目根据统计检验和分组机器学习阈值判断是否检测到稳定时间差异。
> 报告真实场景结果时，应同时报告正对照结果，因为正对照用于验证检测管线
> 是否足以识别已知注入的时间信号。

避免直接写成：

```text
ML-KEM 不存在侧信道泄漏。
```

这个结论超出了本实验能够支持的范围。
