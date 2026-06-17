# ML-KEM 实验运行手册

这份文档用于在另一台电脑上运行完整实验，并把结果带回当前项目。

## 1. 目标

实验会重复运行 ML-KEM 解封装时间侧信道筛查，覆盖：

- 参数集：`ML-KEM-512`、`ML-KEM-768`、`ML-KEM-1024`
- 无效密文策略：`single_bit`、`byte_flip`、`random_bytes`、`zero`
- 场景：真实场景 `real` 和正对照 `positive_control`
- 默认轮次：`5` 轮

结果会写入：

```bash
results/paper_runs/
results/paper_artifacts/
```

## 2. 准备环境

进入项目目录：

```bash
cd /path/to/PostQuantum
```

创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

检查依赖：

```bash
python -m pip check
python -m pytest -q
```

预期测试结果：

```text
10 passed
```

## 3. 推荐运行方式

### 3.1 完整但更耗时

如果另一台电脑性能较好，并且可以长时间运行，使用：

```bash
source .venv/bin/activate
LOKY_MAX_CPU_COUNT=8 MLKEM_PERMUTATIONS=20 bash scripts/run_paper_experiments.sh
```

说明：

- `LOKY_MAX_CPU_COUNT=8`：避免 macOS 下 joblib 探测物理核心时刷 warning。
- `MLKEM_PERMUTATIONS=20`：每个模型做 20 次置换检验，比默认 200 次快很多。
- 默认仍然跑 `5` 轮、`3` 个参数集、`4` 种无效密文策略。

如果要使用更严格但更慢的置换检验：

```bash
LOKY_MAX_CPU_COUNT=8 MLKEM_PERMUTATIONS=200 bash scripts/run_paper_experiments.sh
```

### 3.2 先跑小规模冒烟测试

建议正式运行前先跑一个小规模测试，确认环境没问题：

```bash
source .venv/bin/activate
RUNS=1 \
SAMPLES_PER_CLASS=20 \
REPETITIONS=5 \
N_GROUPS=5 \
VARIANTS="768" \
INVALID_STRATEGIES="single_bit" \
MLKEM_PERMUTATIONS=5 \
bash scripts/run_paper_experiments.sh
```

跑完后检查：

```bash
ls results/paper_runs
ls results/paper_artifacts
```

如果能看到 `DATA_QUALITY_REPORT.md`，说明流程打通。

### 3.3 分批运行

如果完整矩阵太慢，可以分批跑。比如先只跑 ML-KEM-768：

```bash
RUNS=5 \
VARIANTS="768" \
INVALID_STRATEGIES="single_bit byte_flip random_bytes zero" \
LOKY_MAX_CPU_COUNT=8 \
MLKEM_PERMUTATIONS=20 \
bash scripts/run_paper_experiments.sh
```

或者先只跑默认单比特策略的三个参数集：

```bash
RUNS=5 \
VARIANTS="512 768 1024" \
INVALID_STRATEGIES="single_bit" \
LOKY_MAX_CPU_COUNT=8 \
MLKEM_PERMUTATIONS=20 \
bash scripts/run_paper_experiments.sh
```

## 4. 运行期间注意事项

为了减少软件计时噪声，建议：

- 插电运行，关闭低电量模式。
- 关闭浏览器、同步软件、下载任务、备份任务和大型编译任务。
- 尽量保持散热稳定，不要一边跑实验一边高负载使用机器。
- 不要在运行过程中移动、删除 `results/paper_runs/`。
- 如果终端出现 `RuntimeWarning: overflow` 或 `invalid value encountered`，通常来自 scikit-learn 内部数值计算 warning；只要程序继续运行并生成报告，可以先保留。

## 5. 怎么判断跑完

脚本最后会打印类似：

```text
Wrote paper artifacts to results/paper_artifacts
```

确认汇总文件存在：

```bash
ls results/paper_artifacts
```

至少应该看到：

```text
DATA_QUALITY_REPORT.md
data_quality.json
model_accuracy_comparison.png
positive_control_distribution.png
real_distribution.png
run_stability.png
trace_order_diagnostic.png
```

检查完成了多少组结果：

```bash
find results/paper_runs -name summary.json | wc -l
```

完整默认矩阵应为：

```text
60
```

计算方式：`5` 轮 × `3` 参数集 × `4` 无效密文策略。

## 6. 跑完后带回哪些文件

把这两个目录整体拷回来：

```bash
results/paper_runs/
results/paper_artifacts/
```

如果要压缩：

```bash
tar -czf mlkem_experiment_results.tar.gz results/paper_runs results/paper_artifacts
```

回到当前电脑后解压到项目根目录：

```bash
tar -xzf mlkem_experiment_results.tar.gz
```

## 7. 如果中断了怎么办

如果中途断电或手动停止，先看已经完成多少：

```bash
find results/paper_runs -name summary.json | wc -l
```

目前脚本会从 `run_1` 开始重新执行，可能覆盖已有同名目录。为了避免混淆，重新跑之前可以改输出目录：

```bash
OUTPUT_ROOT=results/paper_runs_retry \
ARTIFACTS=results/paper_artifacts_retry \
LOKY_MAX_CPU_COUNT=8 \
MLKEM_PERMUTATIONS=20 \
bash scripts/run_paper_experiments.sh
```

如果只想对已有 retry 结果重新生成汇总，也可以单独运行：

```bash
python -m mlkem_leakage.paper_artifacts \
  --input-root results/paper_runs_retry \
  --output-dir results/paper_artifacts_retry
```

## 8. 推荐给论文使用的配置

如果时间允许，推荐：

```bash
RUNS=5 \
SAMPLES_PER_CLASS=400 \
REPETITIONS=50 \
N_GROUPS=60 \
WARMUP=500 \
VARIANTS="512 768 1024" \
INVALID_STRATEGIES="single_bit byte_flip random_bytes zero" \
LOKY_MAX_CPU_COUNT=8 \
MLKEM_PERMUTATIONS=20 \
bash scripts/run_paper_experiments.sh
```

如果发现某个组合结果可疑，再单独对该组合用更高置换次数复跑，例如：

```bash
python -m mlkem_leakage.cli \
  --output-dir results/deep_check/ml_kem_768_single_bit \
  --variants 768 \
  --invalid-strategies single_bit \
  --samples-per-class 400 \
  --repetitions 50 \
  --groups 60 \
  --warmup 500 \
  --seed 20260602
```

运行前设置：

```bash
export LOKY_MAX_CPU_COUNT=8
export MLKEM_PERMUTATIONS=200
```
