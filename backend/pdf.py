"""Dependency-free text PDF writer (Helvetica, A4, paginated)."""
def make_pdf(title, lines):
    esc = lambda t: t.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    pages = [lines[i:i + 46] for i in range(0, len(lines), 46)] or [[]]
    n = len(pages)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(n))}] /Count {n} >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, pg in enumerate(pages):
        st = ("BT /F1 14 Tf 50 800 Td (" + esc(title) + ") Tj /F1 10 Tf 0 -26 Td 14 TL\n" + "".join("(" + esc(l[:100]) + ") Tj T*\n" for l in pg) + "ET").encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {5 + 2 * i} 0 R /Resources << /Font << /F1 3 0 R >> >> >>".encode())
        objs.append(b"<< /Length " + str(len(st)).encode() + b" >>\nstream\n" + st + b"\nendstream")
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1): offs.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out); out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode()
