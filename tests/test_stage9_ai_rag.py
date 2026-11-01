import sqlite3
from backend.ai.rag import retrieve_student_documents, _chunks


def test_chunking_overlaps_and_ignores_empty():
    assert _chunks("   ") == []
    parts = _chunks("a" * 1500, size=900, overlap=100)
    assert len(parts) == 2
    assert parts[0][-100:] == parts[1][:100]


def test_document_retrieval_is_scoped_to_student_and_lexical_fallback(monkeypatch, tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE student_documents(id TEXT, student_id TEXT, original_name TEXT, extraction_text TEXT, extraction_status TEXT, created_at TEXT)")
    conn.execute("INSERT INTO student_documents VALUES('d1','student-a','income-certificate.pdf','Annual family income is recorded as a value for scholarship review.','Completed','2026-01-01')")
    conn.execute("INSERT INTO student_documents VALUES('d2','student-b','private.pdf','Secret unrelated personal document content.','Completed','2026-01-02')")
    def db(): return conn
    result = retrieve_student_documents(db, "student-a", "annual family income", top_k=3)
    assert result["excerpts"]
    assert all(x["document_id"] == "d1" for x in result["excerpts"])
    assert all("student-b" not in str(x) and "Secret unrelated" not in str(x) for x in result["excerpts"])
