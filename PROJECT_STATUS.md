# 项目现状报告

> 更新时间：2026-08-03  
> 项目：电商内容 Agent (ecommerce-copywriter-llm)

---

## 一、项目概述

面向电商卖家的多 Agent 内容生产系统，以商品结构化信息为输入，通过 Agent 协作完成「商品理解 → 文案生成 → SEO → 合规检查 → 质量评分 → 自动重写」闭环，并接入 QLoRA 微调的 Qwen3-14B 作为垂直文案生成引擎。

---

## 二、已完成工作

### 2.1 代码与架构

| 模块 | 状态 | 说明 |
|------|------|------|
| Agent 架构 | ✅ 完成 | 7 个 Agent（产品理解/文案/SEO/合规/Judge/重写/编排器） |
| 统一模型接口 | ✅ 完成 | 支持 vLLM / Transformers / API / Mock 四种后端切换 |
| 评估体系 | ✅ 完成 | LLM-as-Judge 四维评分 + ROUGE-L + 确定性指标 |
| FastAPI 服务 | ✅ 完成 | `/generate`、`/health` 接口 |
| Docker 部署 | ✅ 完成 | Dockerfile + docker-compose.yml（含 vLLM profile） |
| Mock 闭环验证 | ✅ 通过 | `python quick_start.py` 完整跑通生成→评分→重写流程 |

### 2.2 数据工程

| 项目 | 数据 |
|------|------|
| 训练集 | 15,908 条（train.json, 13.6 MB） |
| 验证集 | 1,988 条（val.json, 1.7 MB） |
| 测试集 | 1,988 条（test.json, 1.7 MB） |
| 数据来源 | 天池商品描述（公开）+ AdvertiseGen（清华 CoAI） |
| 格式 | Alpaca（instruction / input / output） |
| 品类 | 9 品类均衡（3c_digital / clothing / beauty / food / home / other 等） |

### 2.3 环境与工具链

| 项目 | 版本/配置 |
|------|-----------|
| Python | 3.12（venv312 虚拟环境） |
| PyTorch | 2.11.0+cu128（支持 RTX 5070 Ti Blackwell sm_120） |
| transformers | 5.8.0 |
| bitsandbytes | 已安装（4-bit 量化） |
| LLaMA-Factory | 已 clone，配置完成 |
| 基座模型 | Qwen3-14B（ModelScope 下载，27.5 GB，8 个 safetensors 文件） |
| GPU | NVIDIA RTX 5070 Ti Laptop, 12 GB VRAM |
| 物理内存 | 16 GB |
| 页面文件 | 32 GB（C 盘 pagefile.sys） |
| 总虚拟内存 | ~47.7 GB |

### 2.4 Git 与敏感内容

- GitHub 仓库：`https://github.com/aaadanzghe/ecommerce-copywriter-llm`
- 最新 commit：`902deb8`（移除大数据文件，仅保留 test.json）
- 敏感内容检查：已完成
  - 邮箱暴露（2579543775@qq.com）：用户确认可接受
  - 大数据文件（train.json 13.6 MB, val.json 1.7 MB）：已从 git tracking 移除
  - 电商链接（juzizhe.com, tmall.com）：天池公开数据集，非敏感
- **待处理**：`902deb8` 尚未 push 到 GitHub（之前网络 443 端口连接失败）

---

## 三、当前阻塞问题

### 3.1 问题描述

QLoRA SFT 训练无法启动。模型权重加载在 **298/443（67%）** 处反复崩溃，退出代码为内存访问冲突。

### 3.2 崩溃详情

```
Loading weights:  67%|██████▋   | 298/443 [00:35<00:08, 19.13it/s]
# 进程退出，退出代码 -1 (0xC0000005 内存访问冲突)
```

- 崩溃位置：每次精确在 298/443，具有 100% 可复现性
- 崩溃进程：Python 解释器本身（非 TRAE 宿主进程）
- 无 Python traceback：进程被操作系统直接终止

### 3.3 根因分析

**核心矛盾**：14B 模型的 8 个 safetensors 文件总计 27.5 GB，transformers 使用 mmap（内存映射）方式加载。在 Windows 上，mmap 将文件映射到虚拟地址空间，当访问到特定区域时触发访问冲突。

已排除的原因：
- ❌ 不是物理内存不足：已将页面文件增至 32 GB，总虚拟内存 47.7 GB > 27.5 GB
- ❌ 不是模型文件损坏：用 `safetensors.safe_open()` 逐文件验证，8 个文件全部完好
- ❌ 不是 GPU 显存不足：崩溃发生在 CPU 端权重加载阶段，GPU 尚未使用
- ❌ 不是 TRAE 终端缓冲区溢出：已改为独立后台进程 + 日志文件重定向，仍然崩溃

实际原因：
- Windows 的 mmap 实现在处理大文件（>4 GB 单文件）时存在地址空间碎片问题
- safetensors 加载到第 298 个权重时，恰好跨越某个内存页边界，触发访问冲突
- 这是 Windows + 大模型 + safetensors 的已知兼容性问题

### 3.4 已尝试的解决方案

| 尝试 | 结果 |
|------|------|
| 增大页面文件至 32 GB | 无效，仍在 298/443 崩溃 |
| 修改 LLaMA-Factory 不强制 device_map | 无效，bnb 自动设置 device_map 后仍崩溃 |
| 纯 transformers 直接加载（device_map="auto"） | 不同错误：bnb 4-bit 不支持 CPU offload |
| 独立后台进程 + 日志重定向 | 排除了 TRAE 终端问题，但崩溃依旧 |
| 验证 safetensors 文件完整性 | 全部通过，文件无损坏 |

---

## 四、待办事项

### 4.1 紧急（解除训练阻塞）

按优先级排序的解决方案：

1. **禁用 mmap 加载**（最优先）
   - 修改 transformers 源码或设置环境变量，强制使用文件 I/O 而非 mmap
   - 尝试 `SAFETENSORS_FAST_GPU=1` 或在 `from_pretrained` 中传 `use_safetensors=False`

2. **换用更小模型**
   - Qwen3-8B（约 16 GB）：减少 mmap 压力，可能避开崩溃点
   - Qwen3-4B（约 8 GB）：几乎不会触发 mmap 问题
   - 代价：模型能力下降，但可完成训练流程验证

3. **云端训练**
   - 使用 AutoDL / 阿里云等 Linux GPU 实例（A100 40GB+）
   - Linux 的 mmap 实现更稳定，不会出现此问题
   - 项目代码已支持模型路径替换，迁移成本低

4. **转换模型格式**
   - 将 safetensors 转为 PyTorch checkpoint（.bin）
   - 或转换为 GGUF 格式，使用 llama.cpp 加载

### 4.2 训练完成后

- [ ] 三路对比评估（base vs fine-tuned vs fine-tuned+rewrite）
- [ ] 将 `902deb8` push 到 GitHub（需网络恢复或配置代理）
- [ ] 更新 README.md 中的训练状态（Iteration 2: 待训练 → 已完成）
- [ ] 补充消融实验和超参数敏感性分析

### 4.3 后续迭代

- [ ] Iteration 3: Listing 优化 Agent
- [ ] Iteration 4: 图片创意 Agent
- [ ] Iteration 5: 短视频脚本 Agent

---

## 五、项目文件结构

```
ecommerce-copywriter-llm/
├── src/
│   ├── agents/          # 7 个 Agent 实现
│   ├── inference/       # 统一模型接口
│   ├── evaluation/      # 评估指标 + 三路对比
│   └── api/             # FastAPI 服务
├── data/
│   ├── labeled/         # Alpaca 格式数据集
│   ├── preprocess.py
│   └── dataset_info.json
├── configs/
│   └── train_config.yaml  # QLoRA 训练配置
├── scripts/
│   ├── setup_env.ps1
│   ├── download_model.py
│   ├── train_local.ps1
│   └── compare_models.py
├── LLaMA-Factory/       # 训练框架（已 clone）
├── models/              # Qwen3-14B 模型文件（27.5 GB）
├── output/              # 训练输出目录（含日志）
├── venv312/             # Python 3.12 虚拟环境
├── quick_start.py       # Mock 模式快速验证
├── Dockerfile
├── docker-compose.yml
├── README.md
├── LICENSE
└── .gitignore
```

---

## 六、关键配置

### 训练配置 (configs/train_config.yaml)

| 参数 | 值 |
|------|-----|
| 基座模型 | Qwen3-14B |
| 微调方法 | QLoRA 4-bit (bnb NF4 + 双重量化) |
| LoRA rank | 64 |
| LoRA alpha | 128 |
| LoRA target | all |
| 学习率 | 2e-4 (cosine) |
| batch size | 4 × 4 (有效 16) |
| epochs | 3 |
| 序列长度 | 1024 |
| 混合精度 | bf16 |
| 优化器 | adamw_8bit |

### 模型加载修改 (LLaMA-Factory)

已修改 `src/llamafactory/model/model_utils/quantization.py` 和 `src/llamafactory/model/patcher.py`，对 bnb 4-bit 量化不强制设置 `device_map`，让 bitsandbytes 自行管理设备放置。但此修改未解决 mmap 崩溃问题。
---

## 2026-08-05 今日进度

- 已把本地训练方案切到 `Qwen3-8B`，并新增 `configs/train_config_8b.yaml`。
- 已更新 `scripts/download_model.py`，8B 模型会落到 `models/Qwen3-8B`。
- 已更新 `scripts/train_local.ps1`，支持配置化模型路径和 `-SmokeTest`。
- 已确认 `models/Qwen3-8B` 下载完整，约 `15.27 GiB`，5 个权重分片均存在。
- 已删除 14B 主体缓存目录，释放约 `27.52 GiB`。
- 已完成脚本语法检查；smoke test 仍需再跑一次最小训练验证。
