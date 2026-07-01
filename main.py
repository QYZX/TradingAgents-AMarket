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
company_name = "300750.SZ"
# 股票日期
trade_date = str(datetime.date.today() - datetime.timedelta(days=0))

stream = 1
if stream == 1:
    # --- 方式一：流式传输（token 级别实时输出）---
    for token, metadata in ta.propagate_stream(company_name, trade_date):
        print(token, end="", flush=True)
    print("\n")

    # 结束
    # 保存报告
    ta.save_reports(ta.curr_state, company_name)
    # 获取最终决策
    decision = ta.process_signal(ta.curr_state["final_trade_decision"])
    print(f"\n最终决策: {decision}")

elif stream == 2:
    # --- 方式二：传统阻塞调用（向后兼容）---
    _, decision = ta.propagate(company_name, trade_date)
    
    # 结束
    # 保存报告
    ta.save_reports(ta.curr_state, company_name)
    # 获取最终决策
    print(f"\n最终决策: {decision}")

elif stream == 3:
    # --- 方式三：生成流程图（Mermaid）---
    png_data = ta.graph.get_graph().draw_mermaid_png()
    with open("graph.png", "wb") as f:
      f.write(png_data)
    print("流程图已保存为 graph.png")

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
