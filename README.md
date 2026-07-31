# E-commerce Content Agent

> 电商内容生产 Agent：商品理解 → 文案生成 → SEO → 合规检查 → 质量评分 → 自动重写 → 多平台适配

## 项目简介

本项目是一个面向电商卖家的内容生产 Agent。系统以商品结构化信息为核心输入，通过多 Agent 协作完成内容生成闭环，并接入 QLoRA 微调模型作为垂直文案生成引擎。

### 核心特点

- **Agent 闭环**：生成 → 评分 → 重写 → 再评分，低质量内容自动优化
- **微调模型接入**：QLoRA 微调的 Qwen3-14B 作为垂直文案生成器，可通过统一接口切换 base/fine-tuned 后端
- **多平台适配**：淘宝、Amazon、抖音、小红书 四种平台风格
- **四维质量评估**：LLM-as-Judge（准确性/吸引力/合规性/SEO）+ ROUGE-L + 确定性指标
- **三路对比**：base model vs fine-tuned vs fine-tuned+rewrite，量化微调和重写的价值
- **容器化部署**：Docker / Docker Compose 一键启动

## 架构

```
ProductProfile (商品信息输入)
       │
       ▼
┌──────────────────────────────────────┐
│  ProductUnderstandingAgent           │  ← 商品理解：解析属性、提炼卖点
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  CopywritingAgent                    │  ← 文案生成：标题/卖点/描述/社媒
│  (微调模型 / Base模型 / 外部API)       │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  SEOAgent                            │  ← SEO：搜索关键词、长尾词
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  ComplianceAgent                     │  ← 合规检查：违禁词 + LLM审核
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  JudgeAgent (LLM-as-Judge)           │  ← 四维评分
└──────────────┬───────────────────────┘
               ▼
        评分 >= 3.5 ?
       /          \
     是            否
     │              │
     ▼              ▼
  输出结果    RewriteAgent → 回到 JudgeAgent
```

## 项目结构

```
ecommerce-copywriter-llm/
├── src/
│   ├── schemas.py                  # ProductProfile, ContentPackage, QualityScore
│   ├── agents/
│   │   ├── base.py                 # BaseAgent 基类
│   │   ├── product_understanding.py
│   │   ├── copywriting.py          # 文案生成（多平台适配）
│   │   ├── seo.py
│   │   ├── compliance.py           # 合规检查（确定性规则 + LLM）
│   │   ├── judge.py                # LLM-as-Judge 四维评分
│   │   ├── rewrite.py              # 自动重写
│   │   └── orchestrator.py         # Agent 编排器
│   ├── inference/
│   │   └── model_client.py         # 统一模型接口（vLLM/Transformers/API/Mock）
│   ├── evaluation/
│   │   ├── metrics.py              # ROUGE-L + 确定性指标
│   │   └── judge.py                # 批量评估 + 三路对比
│   └── api/
│       └── server.py               # FastAPI 服务
├── data/                           # 数据工程（保留原有结构）
│   ├── labeled/                    # Alpaca 格式数据集
│   ├── raw/                        # 原始数据集
│   ├── preprocess.py
│   └── download_datasets.py
├── configs/                        # 训练配置
│   ├── train_config.yaml
│   └── grpo_config.yaml
├── scripts/                        # 环境搭建/模型下载/训练脚本
│   ├── setup_env.ps1
│   ├── download_model.py
│   ├── train_local.ps1
│   ├── serve.ps1
│   ├── serve_api.ps1
│   └── compare_models.py           # 三路对比评估
├── examples/
│   └── sample_products.json        # 示例商品
├── quick_start.py                  # 快速启动（Mock 模式，无需 GPU）
├── Dockerfile                      # Docker 构建
├── docker-compose.yml              # Docker Compose 编排
├── README.md
└── LICENSE
```

## 快速开始

### 1. 验证 Agent 闭环（无需 GPU）

```powershell
python quick_start.py
```

使用 Mock 模型客户端，演示完整的生成→评分→重写流程。示例输出：

```
[1/6] 商品理解...
  卖点: ['主动降噪技术', '30小时超长续航', ...]
  目标人群: 18-35岁都市白领、通勤族、运动爱好者

[2/6] 文案生成...
  标题: 【主动降噪】TWS Pro真无线蓝牙耳机 30小时续航 IPX5防水
  卖点数: 5

[3/6] SEO 关键词...
  关键词: ['降噪耳机', '真无线蓝牙耳机', ...]

[4/6] 合规检查...
  合规: 通过

[5/6] 质量评分...
  准确性: 4/5
  吸引力: 4/5
  合规性: 5/5
  SEO: 3/5
  总分: 4.05/5 (通过)

[6/6] 质量达标，无需重写
```

### 2. Docker 部署

```bash
# 构建镜像
docker build -t ecommerce-agent .

# 启动 API 服务 (Mock 模式，无需模型)
docker run -p 8888:8888 ecommerce-agent

# 或使用 Docker Compose
docker-compose up -d
```

### 3. 启动 API 服务（本地开发）

```powershell
# Mock 模式
python -m uvicorn src.api.server:app --port 8888

# 接入 vLLM 推理服务
$env:MODEL_BACKEND="vllm"
$env:API_BASE="http://localhost:8000/v1"
python -m uvicorn src.api.server:app --port 8888
```

API 调用示例：

```bash
# 生成文案
curl -X POST http://localhost:8888/generate \
  -H "Content-Type: application/json" \
  -d '{
    "title": "无线蓝牙耳机",
    "category": "3c_digital",
    "platform": "taobao",
    "attributes": {"蓝牙版本": "5.3", "续航": "30小时"}
  }'

# 健康检查
curl http://localhost:8888/health
```

### 4. 数据工程

```powershell
# 下载数据集
python data/download_datasets.py

# 预处理为 Alpaca 格式
python data/preprocess.py
```

### 5. 模型微调

```powershell
# 安装环境
.\scripts\setup_env.ps1

# 下载模型
python scripts\download_model.py --model qwen3-14b

# 开始训练
.\scripts\train_local.ps1
```

### 6. 三路对比评估

```powershell
# Mock 模式（验证流程）
python scripts/compare_models.py --mock

# 真实模型对比（需要 GPU）
python scripts/compare_models.py \
  --base models/Qwen3-14B-Instruct \
  --lora output/ecommerce_qlora_sft \
  --test data/labeled/test.json
```

## 数据工程

### 数据来源

全部为真实公开数据集，无模拟数据。

| 数据集 | 来源 | 规模 | 本项目用量 |
|--------|------|------|-----------|
| AdvertiseGen | 清华 CoAI | 114K 条 | 2,000 条（服装类专家样本） |
| 天池商品描述 | 阿里云天池 | 212 万条 | 18,000 条（9 品类均衡） |

最终数据集：19,885 条，9 品类均衡，Alpaca 格式，8:1:1 划分。

### 数据结构

**输入 (ProductProfile)**：
```json
{
  "title": "商品标题",
  "category": "3c_digital",
  "attributes": {"蓝牙版本": "5.3", "续航": "30小时"},
  "selling_points": [],
  "target_audience": "",
  "platform": "taobao",
  "tone": "professional"
}
```

**输出 (ContentPackage)**：
```json
{
  "optimized_title": "优化后的标题",
  "selling_points": ["卖点1", "卖点2", ...],
  "description": "详情页文案",
  "seo_keywords": ["关键词1", ...],
  "social_copy": "社媒推广文案",
  "quality_score": {
    "accuracy": {"score": 4, "reason": "..."},
    "attractiveness": {"score": 4, "reason": "..."},
    "compliance": {"score": 5, "reason": "..."},
    "seo": {"score": 3, "reason": "..."},
    "total": 4.05,
    "passed": true
  }
}
```

## 模型与训练

### 双轨策略

| 轨道 | 模型 | 硬件 | 显存 |
|------|------|------|------|
| 本地 | Qwen3-14B Dense | RTX 5070 Ti 12GB | ~10-11GB (QLoRA 4-bit) |
| 云端 | Qwen3.5-35B-A3B MoE | A100 40GB+ | ~17.5GB (QLoRA 4-bit) |

### QLoRA 配置

| 参数 | 值 |
|------|-----|
| 量化 | 4-bit NF4 + 双重量化 |
| LoRA rank | 64 |
| LoRA target | all |
| 学习率 | 2e-4 (cosine) |
| batch size | 4 × 4 (有效 16) |
| epochs | 3 |

### 模型切换

通过统一接口切换后端，无需修改 Agent 代码：

```python
from src.inference.model_client import create_client, ModelConfig

# Mock 模式（开发测试）
client = create_client(ModelConfig(backend="mock"))

# Transformers + LoRA（本地推理）
client = create_client(ModelConfig(
    backend="transformers",
    model_path="models/Qwen3-14B-Instruct",
    lora_path="output/ecommerce_qlora_sft"
))

# vLLM 服务（高性能推理）
client = create_client(ModelConfig(
    backend="vllm",
    api_base="http://localhost:8000/v1"
))
```

## 评估体系

### LLM-as-Judge 四维评估

| 维度 | 权重 | 评估内容 |
|------|------|---------|
| 准确性 | 35% | 属性值、规格、品牌是否与原文一致 |
| 吸引力 | 30% | 语言流畅度、卖点突显、购买欲望 |
| 合规性 | 20% | 广告法违禁词、虚假宣传检测 |
| SEO覆盖 | 15% | 关键词密度、标题结构、标签覆盖 |

### 三路对比

| 模型 | 说明 |
|------|------|
| base_model | 基座模型直接生成 |
| fine_tuned | QLoRA 微调后生成 |
| fine_tuned_rewrite | 微调 + Judge 重写闭环 |

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 架构 | 自研多 Agent 编排（BaseAgent + Orchestrator） |
| 训练框架 | LLaMA-Factory |
| 微调方法 | QLoRA 4-bit (bitsandbytes) |
| 评估 | LLM-as-Judge + ROUGE-L |
| 推理引擎 | vLLM |
| API 服务 | FastAPI |
| 容器化 | Docker + Docker Compose |
| 基座模型 | Qwen3-14B / Qwen3.5-35B-A3B MoE |

## 迭代计划

| 阶段 | 目标 | 状态 |
|------|------|------|
| Iteration 0 | 项目整理与范围收敛 | 完成 |
| Iteration 1 | 文案生成 Agent MVP | 完成 |
| Iteration 2 | 接入微调模型 + 三路对比 | 待训练 |
| Iteration 3 | Listing 优化 Agent | 规划中 |
| Iteration 4 | 图片创意 Agent | 规划中 |
| Iteration 5 | 短视频脚本 Agent | 规划中 |

## License

MIT License - 详见 [LICENSE](LICENSE)

数据集遵循各自原始协议：
- AdvertiseGen: CC BY-NC 4.0
- 天池商品描述: CC BY-NC 4.0
