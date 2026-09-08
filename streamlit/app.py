from __future__ import annotations

from pathlib import Path

import streamlit as st

IMAGE_TYPES = ("png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp")
PDF_TYPES = ("pdf",)
ALLOWED_TYPES = [*PDF_TYPES, *IMAGE_TYPES]


def upload_files():
    """Show a file uploader and return the selected PDF and image files."""
    return st.file_uploader(
        "Upload documents",
        type=list(ALLOWED_TYPES),
        accept_multiple_files=True,
        help="PDF or image files (PNG, JPG, JPEG, WEBP, TIF, TIFF, BMP).",
        key="document_uploader",
    )


def _is_pdf(name: str, mime_type: str | None) -> bool:
    suffix = Path(name).suffix.lower()
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    return suffix == ".pdf" or mime == "application/pdf"


def _is_image(name: str, mime_type: str | None) -> bool:
    suffix = Path(name).suffix.lower().lstrip(".")
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    return suffix in IMAGE_TYPES or mime.startswith("image/")


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def _store_uploads(files) -> list[dict]:
    documents = [
        {
            "name": item.name,
            "mime_type": item.type,
            "size": item.size,
            "data": item.getvalue(),
        }
        for item in files
    ]
    st.session_state["uploaded_documents"] = documents
    return documents


def _preview_file(uploaded) -> None:
    name = uploaded.name
    mime_type = uploaded.type
    if _is_image(name, mime_type):
        st.image(uploaded, caption=name, width="stretch")
        return
    if _is_pdf(name, mime_type):
        st.pdf(uploaded, height=420, key=f"pdf-{uploaded.file_id}")
        return
    st.warning(f"{name} is not a supported PDF or image file.")


def main() -> None:
    st.set_page_config(
        page_title="Document Verification Agent",
        layout="wide",
    )
    st.title("Document Verification")
    st.caption("Upload a PDF or image to start verification.")

    files = upload_files()
    if not files:
        st.session_state.pop("uploaded_documents", None)
        st.info("No files yet. Upload a PDF or image to continue.")
        return

    documents = _store_uploads(files)
    total_bytes = sum(item["size"] for item in documents)
    count_col, size_col = st.columns(2)
    count_col.metric("Files uploaded", str(len(documents)))
    size_col.metric("Total size", _format_size(total_bytes))

    st.subheader("Preview")
    for row_start in range(0, len(files), 2):
        columns = st.columns(2)
        for offset, uploaded in enumerate(files[row_start : row_start + 2]):
            with columns[offset], st.container(border=True):
                st.markdown(f"**{uploaded.name}**")
                st.caption(
                    f"{uploaded.type or 'unknown type'} · {_format_size(uploaded.size)}"
                )
                _preview_file(uploaded)


main()
