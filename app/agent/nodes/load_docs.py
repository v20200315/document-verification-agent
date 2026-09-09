from typing import Any

from langchain_community.document_loaders import PyPDFLoader
from logger_config import logger
from state import GraphState


def load_docs(state: GraphState) -> dict[str, Any]:
    logger.info("---LOAD DOCS (X_OUTLINE_V2)---")
    paths = state["paths"]

    docs = [PyPDFLoader(path).load() for path in paths]
    documents = [item for sublist in docs for item in sublist]

    return {"documents": documents}
