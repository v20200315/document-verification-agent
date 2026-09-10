from typing import Any

from app.agent.chains.generate_outline_chain import generate_outline_chain
from app.agent.chains.generate_outline_chain2 import generate_outline_chain2
from app.agent.state import GraphState
from app.logger_config import logger


def generate_outline(state: GraphState) -> dict[str, Any]:
    logger.info("---GENERATE OUTLINE (X_OUTLINE_V2)---")
    summarizations = state["documents"]

    response = generate_outline_chain.invoke(
        {"summarizations": summarizations, "tier": 1}
    )

    response2 = generate_outline_chain2.invoke(
        {"summarizations": summarizations, "outline": response}
    )

    response3 = generate_outline_chain2.invoke(
        {"summarizations": summarizations, "outline": response2}
    )

    return {"outline": response3}
