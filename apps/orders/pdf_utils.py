from .document_inspector import inspect_pdf_pages, DocumentInspectionError


def extract_pdf_page_count(file_obj) -> int:
    """
    Attempts to read verified page count of uploaded PDF file.
    Raises DocumentInspectionError if corrupt, empty, or unreadable.
    """
    return inspect_pdf_pages(file_obj)
