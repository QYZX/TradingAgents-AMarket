import logging

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

stream = 2
if stream == 1:
    # --- 方式一：流式传输（token 级别实时输出）---
    for token, metadata in ta.propagate_stream("300750.SZ", "2026-06-26"):
        print(token, end="", flush=True)
    print("\n")

    # 流式结束后，从实例获取最终决策
    decision = ta.process_signal(ta.curr_state["final_trade_decision"])
    print(f"\n最终决策: {decision}")

elif stream == 2:
    # --- 方式二：传统阻塞调用（向后兼容）---
    _, decision = ta.propagate("300750.SZ", "2026-06-26")
    print(decision)

elif stream == 3:
    # --- 方式三：生成流程图（Mermaid）---
    png_data = ta.graph.get_graph().draw_mermaid_png()
    with open("graph.png", "wb") as f:
      f.write(png_data)
    print("流程图已保存为 graph.png")

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
