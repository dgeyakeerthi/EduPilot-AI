"""Live source fetching: https only, SSRF-blocked, robots.txt respected, size/type limited, change-detected. Results go to human review, never auto-publish."""
import hashlib, ipaddress, json, os, socket, time, urllib.error, urllib.request, urllib.robotparser, uuid
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from fastapi import Depends
from pydantic import BaseModel, Field
from backend.ingest import extract, clean, tokens, jaccard, REQUIRED
from backend import scheduler

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
OPEN = urllib.request.build_opener(_NoRedirect)
UA = lambda: f"EduPilotBot/1.0 (+{os.environ.get('CRAWLER_CONTACT', 'set CRAWLER_CONTACT')})"

def check_url(url):
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname: raise ValueError("only https URLs are allowed")
    for a in socket.getaddrinfo(u.hostname, u.port or 443):
        ip = ipaddress.ip_address(a[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified: raise ValueError("address not allowed")
    return u

def robots_ok(u):
    try:
        r = OPEN.open(urllib.request.Request(f"https://{u.netloc}/robots.txt", headers={"User-Agent": UA()}), timeout=10)
        rp = urllib.robotparser.RobotFileParser(); rp.parse(r.read(200_000).decode("utf-8", "replace").splitlines()); return rp.can_fetch("EduPilotBot", u.geturl())
    except urllib.error.HTTPError as e: return e.code in (404, 410)  # no robots file = allowed; other errors = be conservative
    except Exception: return False

def fetch(url, maxb=1_000_000):
    for _ in range(4):  # follow up to 3 redirects, re-validating each hop
        u = check_url(url)
        if not robots_ok(u): raise ValueError("blocked by robots.txt or robots unavailable")
        time.sleep(float(os.environ.get("CRAWL_DELAY_S", "2")))
        try: r = OPEN.open(urllib.request.Request(url, headers={"User-Agent": UA(), "Accept": "text/html,text/plain"}), timeout=15)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"): url = urljoin(url, e.headers["Location"]); continue
            raise ValueError(f"HTTP {e.code}")
        if r.headers.get_content_type() not in ("text/html", "text/plain"): raise ValueError("unsupported content type")
        raw = r.read(maxb + 1)
        if len(raw) > maxb: raise ValueError("page too large")
        return raw.decode(r.headers.get_content_charset() or "utf-8", "replace")
    raise ValueError("too many redirects")

class _T(HTMLParser):
    def __init__(s): super().__init__(); s.o, s.skip = [], 0
    def handle_starttag(s, t, a):
        if t in ("script", "style", "noscript"): s.skip += 1
        if t in ("p", "br", "li", "tr", "h1", "h2", "h3", "div"): s.o.append("\n")
    def handle_endtag(s, t):
        if t in ("script", "style", "noscript") and s.skip: s.skip -= 1
    def handle_data(s, d):
        if not s.skip: s.o.append(d)
def html_to_text(h): p = _T(); p.feed(h); return "\n".join(l.strip() for l in "".join(p.o).splitlines() if l.strip())

class Src(BaseModel): url: str = Field(pattern=r"^https://\S+$", max_length=500); interval_hours: int = Field(24, ge=1, le=720)

def setup(app, user, db, err, now, SCH):
    def tdb():
        c = db(); c.executescript("""CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,url TEXT UNIQUE,interval_hours INT,last_ts REAL,last_hash TEXT,last_status TEXT);
        CREATE TABLE IF NOT EXISTS ingested(id TEXT PRIMARY KEY,status TEXT,data TEXT);"""); return c
    def admin(u):
        if u["role"] != "admin": raise err("forbidden", "Administrator access required", 403)
    def process(c, s):
        try: text = html_to_text(fetch(s["url"]))[:20000]
        except Exception as e: status = "error: " + str(e)[:120]
        else:
            h = hashlib.sha256(text.encode()).hexdigest()
            if h == s["last_hash"]: status = "unchanged"
            elif len(text) < 50: status = "too_short"
            else:
                prior = c.execute("SELECT ingest_id FROM ingestion_source_versions WHERE source_url=? AND content_sha256=?", (s["url"], h)).fetchone()
                if prior:
                    status = "unchanged_snapshot"
                else:
                    rec, method = extract(text); rec = clean(rec)  # fetched text is untrusted; output is validated and human-reviewed
                    pool = [(x["scholarship_id"], tokens(x)) for x in SCH] + [(r["id"], tokens(json.loads(r["data"])["record"])) for r in c.execute("SELECT * FROM ingested WHERE status='Pending_Review'")]
                    d = {"record": rec, "missing_fields": [k for k in REQUIRED if not rec.get(k)], "possible_duplicates": [{"id": i, "similarity": round(jaccard(tokens(rec), t), 2)} for i, t in pool if jaccard(tokens(rec), t) >= 0.90],
                         "provenance": {"source_url": s["url"], "extracted_at": now(), "extraction_method": method, "content_sha256": h, "source_version": c.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM ingestion_source_versions WHERE source_url=?", (s["url"],)).fetchone()[0]}}
                    iid = str(uuid.uuid4())
                    c.execute("INSERT INTO ingested VALUES(?,?,?)", (iid, "Pending_Review", json.dumps(d)))
                    c.execute("INSERT INTO ingestion_source_versions VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), s["url"], h, iid, d["provenance"]["source_version"], now()))
                    c.execute("UPDATE sources SET last_hash=? WHERE id=?", (h, s["id"])); status = "queued_for_review"
        c.execute("UPDATE sources SET last_ts=?,last_status=? WHERE id=?", (time.time(), status, s["id"])); c.commit(); return status
    def run_due():
        c, out = tdb(), []
        for s in c.execute("SELECT * FROM sources").fetchall():
            if not s["last_ts"] or time.time() - s["last_ts"] >= s["interval_hours"] * 3600: out.append(process(c, s))
        return f"{len(out)} sources checked: {out}"
    scheduler.register("source_crawl", int(os.environ.get("CRAWL_CHECK_MIN", "60")) * 60, run_due)

    @app.post("/api/admin/sources", status_code=201)
    def add(b: Src, u=Depends(user)):
        admin(u); c = tdb()
        try: check_url(b.url)
        except Exception as e: raise err("invalid_source", str(e), 422)
        try: c.execute("INSERT INTO sources VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), b.url, b.interval_hours, None, None, None)); c.commit()
        except Exception: raise err("duplicate_source", "Source already watched", 409)
        return {"url": b.url, "interval_hours": b.interval_hours}
    @app.get("/api/admin/sources")
    def lst(u=Depends(user)): admin(u); return [dict(r) for r in tdb().execute("SELECT id,url,interval_hours,last_ts,last_status FROM sources")]
    @app.delete("/api/admin/sources/{sid}")
    def rm(sid: str, u=Depends(user)): admin(u); c = tdb(); c.execute("DELETE FROM sources WHERE id=?", (sid,)); c.commit(); return {"deleted": True}
    @app.post("/api/admin/sources/{sid}/fetch-now")
    def now_(sid: str, u=Depends(user)):
        admin(u); c = tdb(); s = c.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        if not s: raise err("not_found", "Source not found", 404)
        return {"result": process(c, s)}
    @app.get("/api/admin/scheduler")
    def sched(u=Depends(user)): admin(u); return scheduler.status
