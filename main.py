import logging
import datetime

logging.basicConfig(
    # level=logging.DEBUG,   # 或 INFO / WARNING
    # format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# DEFAULT_CONFIG already applies TRADINGAGENTS_* env-var overrides
# (llm_provider, deep_think_llm, quick_think_llm, backend_url, etc.),
# so users can switch models or endpoints purely via .env without
# editing this script. Override individual keys here only when you
# want a hard-coded value that should ignore the environment.
config = DEFAULT_CONFIG.copy()

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# 股票代码
company_name = "300502.SZ"
# 股票日期
trade_date = str(datetime.date.today() - datetime.timedelta(days=0))

# forward propagate
_, decision = ta.propagate(company_name, trade_date)

# 结束
# 保存报告
ta.save_reports(ta.curr_state, company_name)
# 获取最终决策
print(f"\n最终决策: {decision}")


# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
