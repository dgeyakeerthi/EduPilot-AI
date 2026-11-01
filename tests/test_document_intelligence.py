import pytest
from backend.documents.service import (
    DocumentError, validate_upload, detect_type, compare_extracted_fields,
    MAX_UPLOAD_BYTES,
)

def test_pdf_signature_is_detected():
    assert detect_type(b"%PDF-1.7 sample") == "application/pdf"

def test_rejects_unknown_content():
    with pytest.raises(DocumentError): detect_type(b"not a document")

def test_extension_must_match_signature():
    with pytest.raises(DocumentError): validate_upload("fake.jpg", b"%PDF-1.7 sample")

def test_upload_size_limit():
    with pytest.raises(DocumentError): validate_upload("large.pdf", b"%PDF-" + b"x" * MAX_UPLOAD_BYTES)

def test_safe_filename_and_valid_pdf():
    mime, name = validate_upload("my policy.pdf", b"%PDF-1.7 sample")
    assert mime == "application/pdf"
    assert "/" not in name and " " not in name

def test_conflicting_document_values_are_flagged_not_resolved():
    result = compare_extracted_fields([
        {"document_id": "a", "corrected_fields": {"name": "Asha"}},
        {"document_id": "b", "extracted_fields": {"name": "Ayesha"}},
    ])
    assert len(result) == 1
    assert result[0]["status"] == "requires_student_review"
    assert len(result[0]["values"]) == 2

def test_matching_values_are_not_flagged():
    assert compare_extracted_fields([
        {"document_id": "a", "corrected_fields": {"name": "Asha"}},
        {"document_id": "b", "corrected_fields": {"name": "asha"}},
    ]) == []
