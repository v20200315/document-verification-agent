from typing import Any

from chains.generate_outline_chain import generate_outline_chain
from chains.generate_outline_chain2 import generate_outline_chain2
from logger_config import logger
from state import GraphState


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
