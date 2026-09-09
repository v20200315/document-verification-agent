from typing import TypedDict

from langchain_core.documents import Document


class GraphState(TypedDict):
    """
    Represents the state of our graph.
    """

    openai_api_key: str
    paths: list[str]
    documents: list[Document]
    summarizations: list[str]
    outline: str
