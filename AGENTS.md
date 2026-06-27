# Repository Guidelines

## 项目概述

TradingAgents 是一个基于多智能体 LLM 的金融交易分析框架，使用 LangGraph 编排多个 AI 角色（分析师、研究员、交易员、风控）协同完成投资决策。

## 项目结构与模块组织

```
TradingAgents/
├── tradingagents/          # 核心包
│   ├── agents/             # 智能体定义（analysts, researchers, trader, risk_mgmt, managers）
│   ├── dataflows/          # 数据源接口（yfinance, akshare, alpha_vantage, fred, polymarket 等）
│   ├── graph/              # LangGraph 图编排（trading_graph, signal_processing 等）
│   ├── llm_clients/        # LLM 客户端适配层（openai, anthropic, google, bedrock, azure）
│   ├── default_config.py   # 默认配置（支持 TRADINGAGENTS_* 环境变量覆盖）
│   └── reporting.py        # 报告生成
├── cli/                    # Typer CLI 入口（tradingagents 命令）
├── tests/                  # pytest 测试目录
├── scripts/                # 辅助脚本
├── main.py                 # 快速启动入口
├── pyproject.toml          # 项目元数据与构建配置
└── .env.example            # 环境变量模板
```

## 构建、测试与开发命令

```bash
# 安装项目（含开发依赖）
pip install -e ".[dev]"

# 运行全部测试
pytest

# 运行指定测试文件
pytest tests/test_symbol_utils.py

# Lint 检查
ruff check .

# 运行 CLI
tradingagents --help

# 运行主程序
python main.py
```

## 代码风格与命名规范

- **Python 版本**：>= 3.14
- **行宽限制**：100 字符（E501 已忽略，由格式化工具统一处理）
- **Linter**：`ruff`，规则集包含 E/W/F/I/B/UP/C4/SIM
- **缩进**：4 空格，不使用 Tab
- **导入排序**：`isort`（通过 ruff 集成），合并 `as` 别名导入
- **命名**：模块和函数使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`
- **`__init__.py`**：允许有意的 re-export（F401 已忽略）

## 测试规范

- **框架**：`pytest`，支持 `pytest-subtests`
- **测试目录**：`tests/`
- **命名约定**：测试文件 `test_<feature>.py`，测试函数 `test_<行为描述>`
- **运行命令**：`pytest`（全部）或 `pytest tests/test_<name>.py`（单个）
- **配置文件**：`pyproject.toml` 中的 `[tool.pytest.ini_options]`

## 提交与 Pull Request 规范

基于 Git 历史，提交信息遵循 **Conventional Commits** 格式：

```
<type>(<scope>): <简短描述>
```

常用类型：`fix`、`feat`、`refactor`、`chore`、`test`、`docs`

示例：
- `fix(graph): dedupe the trailing message in the debug stream`
- `feat(reporting): share the report-tree writer between the CLI and the API`
- `test: make the API-key fixture robust to empty-string env vars`

Pull Request 要求：
- 清晰描述变更内容和动机
- 关联相关 Issue
- 确保 `pytest` 和 `ruff check` 通过

## 环境配置

- 复制 `.env.example` 为 `.env`，填入 API 密钥
- 支持 `TRADINGAGENTS_*` 前缀的环境变量覆盖配置项
- 可选安装 Bedrock 支持：`pip install -e ".[bedrock]"`

## Agent 特别说明

- 修改 `tradingagents/` 下的代码后，运行 `pytest` 验证无回归
- 数据源接口位于 `tradingagents/dataflows/`，新增数据源需实现 `interface.py` 中定义的接口
- LLM 客户端扩展位于 `tradingagents/llm_clients/`，继承 `base_client.py`
- `results/` 和 `worklog/` 目录已被 ruff 排除检查
