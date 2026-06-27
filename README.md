# TradingAgents-AMarket

本项目基于 `TauricResearch/TradingAgents` 的多智能体框架，并融合了 `simonlin1212/TradingAgents-astock` 的 A 股分析角色设计，重点适配中国 A 股市场分析。

## 项目概述

`TradingAgents-AMarket` 目标是通过多智能体 LLM 协同决策，为证券分析提供结构化判断与交易建议。系统包含：

- 多角色分析师（市场、舆情、新闻、基本面、政策等）
- 研究团队与对冲研究员
- 交易决策代理
- 风控与组合管理

本仓库特别使用 `easy-tdx` 与 `akshare` 作为主要数据源，支持 A 股行情、技术指标、基本面、新闻与信号数据。

## 核心特点

- 参考 `TauricResearch/TradingAgents` 全部代码结构与多智能体流程
- 参考 `simonlin1212/TradingAgents-astock` A 股分析角色与中国市场适配
- 默认使用 `easy-tdx` 优先获取 A 股行情与技术指标
- 使用 `akshare` 补充 A 股基本面与新闻数据
- 支持 `.SS` / `.SZ` A 股代码，例如 `600519.SS`, `000001.SZ`
- 提供交互式 CLI 和直接脚本调用方式
- 支持多个 LLM 提供商与 OpenAI 兼容接口

## 数据源说明

默认数据供应链：

- `core_stock_apis = easy_tdx,akshare`
- `technical_indicators = easy_tdx,akshare`
- `signal_data = easy_tdx,akshare`
- `fundamental_data = akshare`
- `news_data = akshare`

其中：

- `easy-tdx` 优先用于 A 股行情、历史 K 线、技术指标和信号数据
- `akshare` 用于 A 股基本面、新闻、宏观数据和兜底数据获取

## 安装步骤

```bash
git clone https://github.com/your-org/TradingAgents-AMarket.git
cd TradingAgents-AMarket
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

如需开发依赖：

```bash
pip install -e ".[dev]"
```

## 配置环境变量

复制 `.env.example` 并填写所需 API Key：

```bash
copy .env.example .env
```

推荐填写：

```bash
OPENAI_API_KEY=
GOOGLE_API_KEY=
ANTHROPIC_API_KEY=
```

如果使用 OpenAI-compatible、本地 Ollama 或 AWS Bedrock，请根据 `.env.example` 中的说明配置对应项。

## 使用方法

### 1. 运行 CLI

安装完成后，可直接执行：

```bash
tradingagents
```

或者运行源代码：

```bash
python -m cli.main
```

CLI 会引导你选择：

- 分析标的
- 分析日期
- LLM 提供商与模型
- 研究深度
- 检查点策略

### 2. 直接运行示例脚本

`main.py` 提供演示入口：

```bash
python main.py
```

示例中会调用 `TradingAgentsGraph` 并执行一次推理。

### 3. 代码级调用

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"

# 若需要中文输出可保持默认 config["output_language"] = "Chinese"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("600519.SS", "2026-06-26")
print(decision)
```

## A 股支持说明

本项目已适配中国 A 股标的，支持：

- 上海证券交易所：`*.SS`
- 深圳证券交易所：`*.SZ`

示例代码：

```python
_, decision = ta.propagate("600519.SS", "2026-06-26")
```

## 配置说明

默认配置位于 `tradingagents/default_config.py`，其中重要字段包括：

- `llm_provider`：选择 LLM 提供商
- `deep_think_llm`, `quick_think_llm`：复杂与快速推理模型
- `output_language`：默认中文输出
- `checkpoint_enabled`：是否启用检查点恢复
- `data_vendors`：数据源供应链配置

你也可以通过 `TRADINGAGENTS_*` 环境变量覆盖配置，例如：

```bash
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.5
TRADINGAGENTS_CHECKPOINT_ENABLED=true
```

## 额外命令

清除检查点缓存：

```bash
tradingagents analyze --clear-checkpoints
```

## 项目结构

- `cli/`：命令行入口与交互界面
- `tradingagents/`：核心框架、数据流、代理定义与图编排
- `tests/`：测试用例
- `main.py`：演示脚本
- `.env.example`：环境变量模板

## 免责声明

本项目仅供研究与学习使用，不构成任何投资建议。模型结果、市场行情和交易决策存在风险，请谨慎评估。

## 贡献

欢迎贡献：

- 改进 A 股数据适配与信号策略
- 扩展更多 LLM 模型和本地服务支持
- 丰富中文分析角色与输出格式

---


