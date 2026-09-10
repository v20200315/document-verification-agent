from typing import Any

from langchain_community.document_loaders import PyPDFLoader

from app.agent.state import GraphState
from app.logger_config import logger


def load_docs(state: GraphState) -> dict[str, Any]:
    logger.info("---LOAD DOCS (X_OUTLINE_V2)---")
    paths = state["paths"]

    docs = [PyPDFLoader(path).load() for path in paths]
    documents = [item for sublist in docs for item in sublist]

    return {"documents": documents}
