from __future__ import annotations

from pathlib import Path

from sandbox.src.classifier import DocumentClassifier
from sandbox.src.config import Settings
from sandbox.src.extractor import ContentExtractor, merge_pages
from sandbox.src.llm import build_models
from sandbox.src.loaders import DocumentLoader
from sandbox.src.schemas import DocumentResult


class DocumentPipeline:
    """Compose narrow stages so loaders and models remain replaceable."""

    def __init__(
        self,
        loader: DocumentLoader,
        extractor: ContentExtractor,
        classifier: DocumentClassifier,
    ) -> None:
        self.loader = loader
        self.extractor = extractor
        self.classifier = classifier

    @classmethod
    def from_settings(cls, settings: Settings) -> DocumentPipeline:
        text_model, vision_model = build_models(settings)
        return cls(
            loader=DocumentLoader(
                scanned_text_threshold=settings.scanned_text_threshold,
                pdf_render_dpi=settings.pdf_render_dpi,
            ),
            extractor=ContentExtractor(
                text_model=text_model,
                vision_model=vision_model,
                max_attempts=settings.max_retries,
            ),
            classifier=DocumentClassifier(
                model=text_model,
                max_attempts=settings.max_retries,
            ),
        )

    @classmethod
    def from_env(cls) -> DocumentPipeline:
        return cls.from_settings(Settings.from_env())

    def run(self, file_path: str | Path) -> DocumentResult:
        document = self.loader.load(file_path)
        pages = self.extractor.extract(document)
        full_content = merge_pages(pages)
        classification = self.classifier.classify(full_content)

        return DocumentResult(
            file_name=document.file_name,
            file_type=document.file_type,
            doc_category=classification.doc_category,
            category_confidence=classification.category_confidence,
            category_reasoning=classification.category_reasoning,
            full_content=full_content,
            page_count=document.page_count,
        )
