"""Student-scoped, local-first retrieval over the authenticated student's document vault.
Document text is never sent to Gemini by this module; answers use local Ollama only.
"""
from __future__ import annotations
import re
from pathlib import Path
from backend.embeddings import LocalNomicIndex, EmbeddingUnavailable


def _chunks(text: str, size: int = 900, overlap: int = 120):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out=[]; start=0
    while start < len(text):
        end=min(len(text), start+size)
        piece=text[start:end].strip()
        if piece: out.append(piece)
        if end == len(text): break
        start=max(start+1, end-overlap)
    return out


def retrieve_student_documents(db, student_id: str, query: str, top_k: int = 4):
    """Return matching excerpts and safe source labels; only the owner's records are queried."""
    rows=db().execute(
        "SELECT id, original_name, extraction_text, extraction_status FROM student_documents "
        "WHERE student_id=? AND extraction_text<>'' ORDER BY created_at DESC LIMIT 30", (student_id,)
    ).fetchall()
    chunks=[]; metadata=[]
    for row in rows:
        for part_no, part in enumerate(_chunks(row["extraction_text"])):
            chunks.append(part)
            metadata.append({"document_id":row["id"], "document_name":row["original_name"],
                             "part":part_no+1, "extraction_status":row["extraction_status"]})
    if not chunks:
        return {"excerpts":[], "sources":[], "method":"no_document_text"}
    # Each request builds a short-lived local index. It avoids cross-student vector reuse.
    try:
        index=LocalNomicIndex(index_dir=str(Path("data")/"student_rag"/student_id))
        index.ensure(chunks)
        found=index.search(query[:500], top_k)
        method="local_nomic_"+index.backend
    except Exception:
        terms=set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked=[]
        for i, chunk in enumerate(chunks):
            words=set(re.findall(r"[a-z0-9]+", chunk.lower()))
            score=len(terms & words)/max(1,len(terms))
            if score: ranked.append((i,score))
        found=sorted(ranked,key=lambda x:x[1],reverse=True)[:top_k]
        method="lexical_fallback"
    selected=[(i,score) for i,score in found if i < len(chunks) and score > 0][:top_k]
    return {"excerpts":[{"text":chunks[i], "score":round(float(score),4), **metadata[i]} for i,score in selected],
            "sources":[{k:v for k,v in metadata[i].items() if k in ("document_id","document_name")} for i,_ in selected],
            "method":method}
