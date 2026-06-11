# 基于机器学习的 ML-KEM-768 实现时间侧信道泄漏检测

本项目提供一个可复现的软件计时实验，用于筛查 ML-KEM-768 解封装实现中是否
存在可被统计方法和机器学习模型区分的时间差异。项目适合作为“基于机器学习的
ML-KEM 实现侧信道泄漏检测研究”期末论文的实验基础。

实验使用 Python `pqcrypto` 包提供的 `ML-KEM-768` 绑定，围绕解封装
（decapsulation）阶段采集时间数据。选择解封装阶段的原因是：该阶段需要使用
私钥，因此是实现安全分析中更值得关注的环节。

## 1. 研究问题

本实验尝试回答以下问题：

> 对同一个 ML-KEM-768 解封装实现，有效密文和经过单比特扰动的密文是否会表现出
> 可被统计检验或机器学习模型识别的执行时间差异？

项目不是完整的侧信道攻击，也不会尝试恢复私钥。它是一项实现级泄漏筛查：

- 若模型能够稳定区分两类密文，说明实现可能存在值得进一步研究的时间差异。
- 若模型接近随机猜测，只能说明当前实验条件下未检测到可区分信号。
- 负结果不能证明实现绝对安全。

## 2. 实验设计概览

实验包含两个场景：

| 场景 | 说明 | 作用 |
| --- | --- | --- |
| `real` | 直接测量真实 ML-KEM-768 解封装时间 | 检查实现中是否存在可区分差异 |
| `positive_control` | 对扰动密文人为加入默认 `20,000 ns` 延迟 | 验证采集和分析管线确实能够识别已知信号 |

每次实验首先生成 ML-KEM-768 密钥对，再生成多组有效密文。对于每个有效密文，
程序构造一个仅改变一个比特的配对扰动密文。之后随机打乱样本顺序，分别采集有效
密文和扰动密文的解封装时间。

正对照非常重要。如果正对照也无法被模型识别，那么真实场景中的负结果可能只是
采集参数不足或检测流程失效。只有正对照通过时，真实场景的负结果才具有解释价值。

## 3. 项目结构

```text
.
├── README.md
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── src/
│   └── mlkem_leakage/
│       ├── __init__.py
│       ├── collector.py
│       ├── analysis.py
│       └── cli.py
├── tests/
│   └── test_collector.py
└── results/
    └── latest/
        ├── REPORT.md
        ├── summary.json
        ├── real_traces.csv
        ├── real_analysis.json
        ├── real_timing_histogram.png
        ├── positive_control_traces.csv
        ├── positive_control_analysis.json
        └── positive_control_timing_histogram.png
```

主要模块职责如下：

| 文件 | 职责 |
| --- | --- |
| `collector.py` | 生成密钥和密文、构造单比特扰动密文、采集时间、提取特征 |
| `analysis.py` | 运行 Welch's t-test、计算 Cohen's d、训练和评估分类器、生成图像 |
| `cli.py` | 解析参数、组织两个实验场景、写入汇总报告 |
| `test_collector.py` | 检查单比特扰动逻辑和样本类别平衡 |

## 4. 环境要求

已验证环境：

- macOS arm64
- Python `3.9.6`
- `pqcrypto==0.3.4`
- `numpy==2.0.2`
- `scipy==1.13.1`
- `scikit-learn==1.6.1`
- `matplotlib==3.9.4`

所有 Python 依赖均安装到项目目录内的 `.venv` 虚拟环境，不会污染系统 Python。

## 5. 安装步骤

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

检查环境是否完整：

```bash
source .venv/bin/activate
python -m pip check
```

预期输出：

```text
No broken requirements found.
```

## 6. 运行实验

使用默认参数运行：

```bash
source .venv/bin/activate
python -m mlkem_leakage.cli
```

实验结果默认写入 `results/latest/`。程序结束后会在终端打印简短结论，同时生成
机器可读的 JSON、原始聚合数据 CSV 和直方图 PNG。

为了保留不同实验轮次，可以指定独立输出目录：

```bash
python -m mlkem_leakage.cli --output-dir results/run_003
```

## 7. 命令行参数

查看完整帮助：

```bash
python -m mlkem_leakage.cli --help
```

默认参数如下：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `--output-dir` | `results/latest` | 输出目录 |
| `--samples-per-class` | `400` | 每个类别的聚合样本数量 |
| `--repetitions` | `50` | 每个聚合样本包含的重复解封装次数 |
| `--groups` | `40` | 独立基础密文组数量 |
| `--warmup` | `500` | 正式采集前的预热解封装次数 |
| `--seed` | `20260602` | 样本顺序和数据切分使用的随机种子 |
| `--control-delay-ns` | `20000` | 正对照人为加入的延迟，单位为纳秒 |
| `--variants` | `768` | 要测试的 ML-KEM 参数集，可选 `512 768 1024` |
| `--invalid-strategies` | `single_bit` | 要测试的无效密文构造策略 |
| `--delay-sweep` | 无 | 对正对照运行多档人为延迟灵敏度扫描 |

采集更多样本的示例：

```bash
python -m mlkem_leakage.cli \
  --output-dir results/run_large \
  --samples-per-class 400 \
  --repetitions 50 \
  --groups 80
```

同时比较三个参数集和多种无效密文策略：

```bash
python -m mlkem_leakage.cli \
  --output-dir results/comparison_run \
  --variants 512 768 1024 \
  --invalid-strategies single_bit byte_flip random_bytes zero
```

样本数量和重复次数越多，实验运行时间越长，但通常能够降低操作系统调度噪声对结果
的影响。正式论文实验建议在机器空闲时运行，并保留多轮结果。

## 8. 数据采集方法

### 8.1 密文配对

程序为每个基础密文构造一个无效密文版本。默认策略只改变一个比特：

```python
altered[sha256(group_id) % len(ciphertext)] ^= 1 << bit_position
```

支持的无效密文构造策略如下：

| 策略 | 说明 | 作用 |
| --- | --- | --- |
| `single_bit` | 基于 `group_id` 的 SHA-256 摘要选择字节和 bit，只翻转一位 | 精细扰动，适合观察最小输入变化 |
| `byte_flip` | 基于 SHA-256 选择一个字节并整体取反 | 中等强度扰动，扩大局部差异 |
| `random_bytes` | 生成同长度确定性伪随机密文 | 模拟完全随机无效输入 |
| `zero` | 构造同长度全零密文 | 模拟极端结构化无效输入 |
 
所有策略都保持密文长度不变，避免把“长度错误导致的异常路径”混入主要实验。

标签约定：

| 标签 | 含义 |
| ---: | --- |
| `0` | 有效密文 |
| `1` | 按当前策略构造的无效密文 |

### 8.2 聚合时间特征

单次系统计时容易受进程调度、后台任务和缓存状态影响。因此，一个聚合样本会重复
执行多次解封装，再从时间序列中提取特征。

`*_traces.csv` 中的字段如下：

| 字段 | 说明 |
| --- | --- |
| `scenario` | 实验场景：`real` 或 `positive_control` |
| `trace_id` | 当前聚合样本编号 |
| `group_id` | 基础密文组编号 |
| `label` | 类别标签：有效密文为 `0`，扰动密文为 `1` |
| `mean_ns` | 平均解封装时间 |
| `median_ns` | 中位数解封装时间 |
| `std_ns` | 标准差 |
| `min_ns` | 最小值 |
| `max_ns` | 最大值 |
| `p10_ns` | 第 10 百分位数 |
| `p90_ns` | 第 90 百分位数 |
| `iqr_ns` | 四分位距 |
| `mad_ns` | 中位绝对偏差 |

所有时间字段的单位均为纳秒。

## 9. 分析方法

### 9.1 Welch's t-test

项目对两类样本的 `mean_ns` 执行 Welch's t-test。该方法不要求两个总体具有相同
方差，适合用于比较有效密文和扰动密文的平均执行时间是否存在显著差异。

### 9.2 Cohen's d

Cohen's d 用于描述效应大小。仅依赖 p-value 可能在样本量很大时将极小差异判断为
统计显著，因此项目同时要求效应大小达到阈值。

### 9.3 机器学习模型

项目使用两个分类器：

| 模型 | 作用 |
| --- | --- |
| 线性支持向量机（SVM） | 提供线性可分性的分类基线 |
| 随机森林 | 检查非线性特征组合是否具有区分能力 |

线性 SVM 之前使用 `RobustScaler` 做稳健缩放，并裁剪缩放后的极端值。相比普通
标准化，它更适合带有少量长尾计时样本的数据，同时不会修改原始 CSV。

### 9.4 防止数据泄漏

模型评估使用 `GroupShuffleSplit`。来自同一个基础密文的样本会被分配到同一个
训练集或测试集，不会同时出现在两边。

这样可以降低模型记住特定密文计时特征而获得虚高准确率的风险。模型必须在未见过的
密文组上完成分类，结果才更接近真实的泛化能力。

### 9.5 评价指标

主要机器学习指标为 balanced accuracy（平衡准确率）。本实验两类样本数量相同，
因此随机猜测的期望值约为 `0.5`：

- 接近 `0.5`：模型基本无法区分两类样本。
- 明显高于 `0.5`：可能存在可利用的时间差异。
- 接近 `1.0`：两类样本几乎完全可分。

## 10. 泄漏判定规则

真实场景只有在以下三个条件全部满足时，才报告 `leakage_detected: true`：

| 条件 | 阈值 |
| --- | ---: |
| 最佳模型平均 balanced accuracy | `>= 0.65` |
| Welch's t-test p-value | `< 0.01` |
| Cohen's d 绝对值 | `>= 0.2` |

正对照通过条件：

| 条件 | 阈值 |
| --- | ---: |
| 最佳模型平均 balanced accuracy | `>= 0.90` |
| Welch's t-test p-value | `< 0.001` |

这些阈值用于降低偶然噪声造成误判的风险。它们是当前课程实验的保守判定规则，不是
通用侧信道安全认证标准。

## 11. 多轮重复实验、跨参数集和跨策略汇总

论文实验使用 `scripts/run_paper_experiments.sh` 独立运行 5 轮。默认每轮覆盖
ML-KEM-512、ML-KEM-768、ML-KEM-1024 三个参数集，并对 `single_bit`、`byte_flip`、
`random_bytes`、`zero` 四种无效密文策略分别运行真实场景和正对照场景。

一键重新运行并生成质量报告和论文图表：

```bash
source .venv/bin/activate
bash scripts/run_paper_experiments.sh
```

如果机器性能有限，可以通过环境变量缩小规模：

```bash
RUNS=2 SAMPLES_PER_CLASS=120 REPETITIONS=20 N_GROUPS=20 \
VARIANTS="768" INVALID_STRATEGIES="single_bit byte_flip" \
bash scripts/run_paper_experiments.sh
```

分析阶段默认使用单进程和 200 次置换检验以提高复现稳定性；如需加速，可设置
`MLKEM_N_JOBS=-1` 允许 scikit-learn 使用全部可用核心。快速 smoke test 可临时设置
`MLKEM_PERMUTATIONS=5`，正式论文实验建议保留默认值。

### 11.1 数据质量

汇总脚本会递归读取 `results/paper_runs/**/summary.json`，对每个参数集、每种策略和
每轮实验分别检查：

| 检查项 | 目的 |
| --- | --- |
| 标签数量平衡 | 确认有效/无效密文样本数量一致 |
| group 覆盖和 group-label 覆盖 | 确认分组评估有足够基础密文组 |
| 缺失值和非有限数值 | 排除 CSV 记录损坏 |
| 重复 trace ID | 排除样本编号冲突 |
| IQR 离群点数量 | 观察操作系统调度造成的长尾噪声 |
| 采集顺序 Spearman 相关 | 诊断实验过程中是否存在时间漂移 |

软件计时存在有限范围内的长尾样本和阶段性漂移。项目保留原始值，不静默删除异常点。
完整审计结果见 `results/paper_artifacts/DATA_QUALITY_REPORT.md`。

### 11.2 结果解释

跨轮汇总时，应分别报告每个参数集和每种无效密文策略的真实场景结果，至少包括：

| 指标 | 解释 |
| --- | --- |
| `mean_difference_ns` 的均值和标准差 | 时间差方向是否稳定 |
| 最佳模型 balanced accuracy 的均值和标准差 | 分类信号是否稳定高于随机水平 |
| Welch p-value 和 Cohen's d | 均值差异是否同时具备统计显著性和实际效应量 |
| 正对照最佳 balanced accuracy | 管线在该轮、该参数集、该策略下是否有效 |

只有正对照通过时，真实场景的阴性结果才具有解释价值。若真实场景某一策略出现高
balanced accuracy，但统计检验或效应量不支持，应作为“可疑信号”而不是直接判定
泄漏。

## 12. 实验环境控制建议

软件计时实验容易受到系统状态影响。正式采集前建议记录并尽量控制以下条件：

| 项目 | 建议 |
| --- | --- |
| 机器负载 | 关闭浏览器、同步软件、构建任务等后台高负载进程 |
| 电源状态 | 使用外接电源，避免低电量模式 |
| 温度和散热 | 避免刚启动或过热状态，保证散热稳定 |
| CPU 频率 | 如平台允许，固定性能模式；若不能固定，在论文中说明限制 |
| 网络和 I/O | 避免采集期间大量下载、索引、备份或外接磁盘活动 |
| 运行顺序 | 使用随机化采集顺序，并保留 `trace_order_diagnostic.png` |
| 重复性 | 至少运行 5 轮独立实验，报告均值、标准差和异常轮次 |
| 环境记录 | 保留 `summary.json` 中的 Python、平台、依赖版本和参数 |

这些控制不能把通用操作系统变成硬件侧信道实验台，但可以减少明显的混杂因素，使
“未检测到泄漏”的结论更可信。

## 13. 输出文件说明

| 文件 | 说明 |
| --- | --- |
| `REPORT.md` | 自动生成的简短结论，适合快速查看 |
| `summary.json` | 环境、运行参数和两个场景完整结果 |
| `real_traces.csv` | 真实场景原始聚合样本 |
| `real_analysis.json` | 真实场景统计结果和模型结果 |
| `real_timing_histogram.png` | 真实场景计时分布图 |
| `positive_control_traces.csv` | 正对照原始聚合样本 |
| `positive_control_analysis.json` | 正对照统计结果和模型结果 |
| `positive_control_timing_histogram.png` | 正对照计时分布图 |

论文中需要制作表格时，优先使用 `summary.json`；需要进一步分析异常样本时，使用
`*_traces.csv`。

论文实验的汇总产物位于 `results/paper_artifacts/`：

| 文件 | 说明 |
| --- | --- |
| `DATA_QUALITY_REPORT.md` | 自动数据质量审计报告 |
| `data_quality.json` | 机器可读质量审计结果 |
| `real_distribution.png` | 真实场景计时分布 |
| `positive_control_distribution.png` | 正对照计时分布 |
| `model_accuracy_comparison.png` | 模型性能对比 |
| `run_stability.png` | 跨轮时间差稳定性 |
| `trace_order_diagnostic.png` | 采集顺序漂移诊断 |

标准论文初稿位于 `docs/PAPER_DRAFT.md`。

## 14. 运行测试

安装开发依赖：

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

运行测试：

```bash
pytest -q
```

当前预期输出：

```text
.....                                                                    [100%]
5 passed
```

## 15. 实验限制

解释结果时需要明确以下边界：

1. 本实验检测的是有效密文与若干无效密文策略之间的实现级时间差异。
2. 标签不直接表示私钥比特，因此本实验不能直接证明存在私钥相关泄漏。
3. 本实验没有构造密钥恢复攻击。
4. 软件计时会受到操作系统调度、后台进程、CPU 状态和缓存行为影响。
5. 多参数集对比只覆盖当前 `pqcrypto` 绑定，不应直接推广到其他实现。
6. 随机无效密文和全零密文可以扩大输入覆盖，但不等价于完整选择密文攻击。
7. 没有检测到泄漏不等于证明实现不存在任何侧信道风险。

## 16. 后续可扩展方向

在期末论文中，可以将当前实验作为基础版本，并选择一到两个方向扩展：

1. 在机器空闲条件下重复运行更多轮实验，报告均值、标准差和置信区间。
2. 调整 `--control-delay-ns`，测试检测管线能够识别的最小人为延迟。
3. 增加支持向量机、梯度提升树等分类器，对比模型性能。
4. 在更多无效密文生成策略上扩展，例如格式边界密文或结构化半随机密文。
5. 在不同硬件或操作系统上重复实验，分析平台差异。
6. 在具备实验设备时扩展到功耗或电磁侧信道数据。

## 17. 论文中可使用的谨慎表述

可以使用：

> 在本实验的软件计时条件下，针对所测试的 ML-KEM 参数集和无效密文构造策略，
> 机器学习分类器的平衡准确率整体接近随机猜测水平，且 Welch's t-test 与 Cohen's d
> 未共同支持存在稳定均值差异。与此同时，正对照实验能够被模型稳定识别。因此，
> 本实验未检测到当前实现对有效密文和所测试无效密文表现出稳定、可区分的时间泄漏。

不建议直接写成：

> ML-KEM 不存在侧信道泄漏。

后者超出了当前实验能够支持的结论范围。
