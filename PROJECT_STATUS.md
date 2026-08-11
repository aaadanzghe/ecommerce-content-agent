# 项目现状报告

> 更新时间：2026-08-11  
> 项目：电商内容 Agent (ecommerce-content-agent)

---

## 一、项目概述

面向电商卖家的多 Agent 内容生产系统，以商品结构化信息为输入，通过 Agent 协作完成「商品理解 → 文案生成 → SEO → 合规检查 → 质量评分 → 自动重写 → 图片生成 → 视频生成」闭环，并接入 QLoRA 微调的 Qwen3-8B 作为垂直文案生成引擎。

---

## 二、已完成工作

### 2.1 代码与架构

| 模块 | 状态 | 说明 |
|------|------|------|
| Agent 架构 | ✅ 完成 | 8 个 Agent（产品理解/文案/SEO/合规/Judge/重写/图片生成/视频生成） |
| 统一模型接口 | ✅ 完成 | 支持 vLLM / Transformers+LoRA / API / Mock 四种后端切换 |
| 评估体系 | ✅ 完成 | LLM-as-Judge 四维评分 + ROUGE-L + 确定性指标 + 三路对比 |
| FastAPI 服务 | ✅ 完成 | v0.5.0，7 个端点（/generate /image /video /all /tasks /health /ready） |
| 图片生成 | ✅ 完成 | Seedream API 已生成真实产品展示图（见 docs/showcase/） |
| 视频生成 | ✅ 完成 | Seedance API 已生成真实产品短视频（见 docs/showcase/），异步任务+SQLite持久化 |
| Docker 部署 | ✅ 完成 | Dockerfile + docker-compose.yml（Mock 可直接用，GPU profile 已更新为 8B） |
| Mock 闭环验证 | ✅ 通过 | `python quick_start.py` 完整跑通 8 步流程 |
| 配置管理 | ✅ 完成 | `.env` 全量配置 + MediaSettings 校验 + .env.example 模板 |
| 测试覆盖 | ✅ 完成 | 客户端协议、API 契约、任务恢复、配置校验 4 类测试 |

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
| 基座模型 | Qwen3-8B（15.27 GB，5 个 safetensors 文件） |
| GPU | NVIDIA RTX 5070 Ti Laptop, 12 GB VRAM |
| API 服务 | uvicorn + FastAPI（端口 8888） |
| 任务队列 | SQLite + WAL 模式（异步视频/图片生成） |

### 2.4 Git 与仓库

- GitHub 仓库：`https://github.com/aaadanzghe/ecommerce-content-agent`
- 仓库状态：公开，已推送最新代码
- 敏感内容：已排除（.env 不在 Git 中，.gitignore 已配置）
- 真实产物：docs/showcase/ 包含 Seedream 产品图 + Seedance 短视频

---

## 三、当前训练状态

### 3.1 14B → 8B 切换

14B 模型在 Windows 上因 mmap 兼容性问题无法加载（27.5GB safetensors 文件在 298/443 处触发内存访问冲突），已切换至 Qwen3-8B（15.27 GB，5 个分片，最大 3.72 GB），避开 mmap 崩溃点。

### 3.2 8B 训练配置

| 参数 | 值 |
|------|-----|
| 基座模型 | Qwen3-8B |
| 微调方法 | QLoRA 4-bit (bnb NF4 + 双重量化) |
| LoRA rank | 64 |
| LoRA alpha | 128 |
| LoRA target | all |
| 学习率 | 2e-4 (cosine) |
| batch size | 1 × 16 (有效 16) |
| epochs | 3 |
| 序列长度 | 768 |
| 混合精度 | bf16 |
| 优化器 | adamw_8bit |

### 3.3 训练执行结果

| 步骤 | 说明 | 状态 | 备注 |
|------|------|------|------|
| Smoke Test | max_steps=5，验证 8B 模型在 Windows 上可正常加载训练 | ✅ 完成 | 5 steps 正常完成，loss 从 3.71 降至 2.94 |
| 完整训练 | 3 epochs，完整 15,908 条训练数据 | ✅ 完成 | 2985 steps，7h14m，最终 loss 6.19 |
| 三路对比评估 | base vs fine-tuned vs fine-tuned+rewrite | ⚠️ 部分完成 | Mock 流程验证通过；真实模型因 VRAM 限制未完成 |

### 3.4 训练分析

**关键发现：梯度爆炸**

| 指标 | 值 |
|------|-----|
| 初始 loss (step 10) | 3.71 |
| 最佳 loss 区间 | ~2.94-3.05 (step 20-100) |
| 梯度爆炸点 | step 350 (grad_norm 101.6, loss 12.47) |
| 最终 loss (step 2980) | 5.96 |
| 最终平均 loss | 6.19 |
| LoRA Adapter 大小 | 666 MB |

**根因分析**：学习率 2e-4 对 Qwen3-8B + QLoRA 偏高，在 warmup 结束后（~step 150）梯度逐渐增大，step 340 处 grad_norm 从 27.2 跳升至 101.6（梯度爆炸），之后 loss 从 ~3.1 崩溃到 12.5，虽然后期逐步回落至 ~6.0，但未能恢复到初始水平。

**改进方向**：降低学习率至 5e-5 ~ 1e-4，或使用 gradient clipping 更严格的值。

### 3.5 端到端效果验证（DeepSeek API）

使用 DeepSeek API 驱动 8-Agent 全流程，测试 3 个品类：

| 品类 | 商品 | 评分 | 耗时 | 合规 |
|------|------|------|------|------|
| 玩具 | NERF 水龙海啸发射器 | 4.20/5 | 17.5s | 有问题（极限词） |
| 食品 | 华参堂淡干海参礼盒 | 4.15/5 | 15.8s | 有问题（功效宣称） |
| 家居 | 转角电脑桌 | 4.20/5 | 13.6s | 通过 |

所有商品均通过质量阈值（3.5/5），合规 Agent 准确识别了广告法违禁词和虚假功效宣称。详细结果见 `output/eval_results/e2e_demo_results.json`。

---

## 四、后续迭代

| 阶段 | 目标 | 优先级 |
|------|------|--------|
| Iteration 5 | Listing 优化 Agent（竞品分析 + 平台规则） | 高 |
| Iteration 6 | RAG 知识库（平台规则 + 品牌资料 + 商品目录） | 高 |
| Iteration 7 | LangGraph 编排 + Supervisor 路由 + Checkpoint | 中 |
| Iteration 8 | 异步任务队列 + SSE + 批量生成 | 低 |

详见 [AGENT_MODERNIZATION_PLAN.md](AGENT_MODERNIZATION_PLAN.md) 中的 LangGraph 架构设计。

---

## 五、项目文件结构

```
ecommerce-content-agent/
├── src/
│   ├── agents/          # 8 个 Agent 实现
│   ├── inference/       # 统一模型接口 + 图片/视频客户端
│   ├── evaluation/      # 评估指标 + 三路对比
│   └── api/             # FastAPI 服务
├── data/
│   ├── labeled/         # Alpaca 格式数据集
│   ├── preprocess.py
│   └── dataset_info.json
├── configs/
│   ├── train_config_8b.yaml   # Qwen3-8B QLoRA 配置（当前主线）
│   ├── train_config.yaml      # Qwen3-14B QLoRA 配置（备用）
│   └── grpo_config.yaml       # GRPO 实验配置
├── scripts/
│   ├── setup_env.ps1
│   ├── download_model.py
│   ├── train_local.ps1
│   ├── serve.ps1
│   ├── serve_api.ps1
│   └── compare_models.py
├── docs/showcase/      # 真实产物（Seedream 图片 + Seedance 视频）
├── models/             # Qwen3-8B 模型文件（15.27 GB）
├── output/             # 训练输出目录
├── tests/              # 测试文件
├── quick_start.py      # Mock 模式快速验证
├── Dockerfile
├── docker-compose.yml
├── README.md
└── LICENSE
```