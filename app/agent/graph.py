from langgraph.graph import END, StateGraph

from app.agent.nodes import generate_outline, load_docs
from app.agent.state import GraphState

workflow = StateGraph(GraphState)

workflow.add_node("load_docs", load_docs)
workflow.add_node("generate_outline", generate_outline)

workflow.set_entry_point("load_docs")
workflow.add_edge("load_docs", "generate_outline")
workflow.add_edge("generate_outline", END)

app = workflow.compile()
