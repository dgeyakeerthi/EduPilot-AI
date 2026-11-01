"""
Admin-assisted scholarship ingestion:
extract -> validate -> deduplicate -> human review -> publish.

No automatic publishing.
"""

import hashlib
import json
import re
import uuid

from datetime import date
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends
from pydantic import BaseModel, Field

from backend.ai import router as ai


FIELDS = {
    "gender",
    "state",
    "social_category",
    "annual_family_income",
    "education_level",
    "course_name",
    "institution_type",
    "institution_name",
    "academic_score_value",
}

REQUIRED = [
    "scholarship_name",
    "provider_name",
    "closing_date",
    "eligible_education_levels",
    "criteria",
]


PROMPT = """
You are an intelligent scholarship announcement extraction system.

Your task is to identify and extract ONE genuine scholarship announcement
from the supplied text.

First determine whether the supplied content actually contains a scholarship
announcement.

Return JSON only using this structure:

{
    "is_scholarship": true,
    "scholarship_name": null,
    "provider_name": null,
    "description": null,
    "benefit_amount": null,
    "closing_date": null,
    "eligible_education_levels": [],
    "required_documents": [],
    "criteria": []
}

STRICT RULES:

1. Return is_scholarship=false for:
   - Generic website homepages.
   - Navigation pages.
   - Welcome messages.
   - Contact pages.
   - General news unrelated to scholarships.
   - Pages that merely link to scholarship information.
   - Content that does not describe an actual scholarship.

2. Extract only information explicitly supported by the supplied text.

3. Never invent:
   - Scholarship names.
   - Provider names.
   - Application deadlines.
   - Eligibility requirements.
   - Scholarship benefits.
   - Required documents.

4. Use null when information is unavailable.

5. closing_date must use YYYY-MM-DD format when explicitly available.

6. eligible_education_levels must be a list.

7. required_documents must be a list.

8. criteria must be a list of objects containing:
   field, op and value.

9. Valid criteria operators:
   eq, in, lte, gte.

10. Do not confuse a general government announcement with a scholarship.

11. Extract only one scholarship announcement.

12. If the content is not clearly about an actual scholarship,
    return is_scholarship=false.

Return valid JSON only. Do not include Markdown or explanations.

TEXT:
"""


class Ingest(BaseModel):
    source_url: str = Field(
        pattern=r"^https://\S+$",
        max_length=500
    )

    raw_text: str = Field(
        min_length=50,
        max_length=20000
    )


class Decision(BaseModel):
    decision: Literal["publish", "reject"]

    verification: Literal["Human_Verified"] = "Human_Verified"

    verification_notes: str = Field(
        min_length=10,
        max_length=2000
    )

    allow_duplicate: bool = False


def tokens(record):
    return set(
        re.findall(
            r"\w+",
            f'{record.get("scholarship_name") or ""} '
            f'{record.get("provider_name") or ""}'.lower()
        )
    )


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


# --------------------------------------------------
# AI SCHOLARSHIP EXTRACTION
# --------------------------------------------------

def extract(text):

    try:
        response_data = ai.complete(
            PROMPT + text[:12000],
            task="extraction"
        )

        response = response_data.get("text", "")

        if response:

            response = response.strip()

            # Remove optional Markdown JSON fences.
            response = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                response,
                flags=re.IGNORECASE
            ).strip()

            # Locate the JSON object.
            start = response.find("{")
            end = response.rfind("}")

            if start != -1 and end > start:

                record = json.loads(
                    response[start:end + 1]
                )

                if not isinstance(record, dict):
                    return {"is_scholarship": False}, "invalid_response"

                # Reject irrelevant webpages.
                if record.get("is_scholarship") is not True:
                    return {"is_scholarship": False}, response_data.get(
                        "provider", "AI"
                    )

                return record, response_data.get("provider", "AI")

    except Exception:
        pass

    # IMPORTANT:
    # Never use the first line of a webpage as a scholarship name.
    # If AI extraction fails, do not create a scholarship record.

    return {
        "is_scholarship": False
    }, "unavailable"


# --------------------------------------------------
# DATA CLEANING AND VALIDATION
# --------------------------------------------------

def clean(record):

    if not isinstance(record, dict):
        record = {}

    # Validate scholarship name.
    name = record.get("scholarship_name")

    if not isinstance(name, str) or not name.strip():
        record["scholarship_name"] = None
    else:
        record["scholarship_name"] = name.strip()[:200]

    # Validate provider.
    provider = record.get("provider_name")

    if not isinstance(provider, str) or not provider.strip():
        record["provider_name"] = None
    else:
        record["provider_name"] = provider.strip()[:200]

    # Validate closing date.
    closing_date = record.get("closing_date")

    if closing_date:

        try:
            parsed_date = date.fromisoformat(str(closing_date))

            if parsed_date.isoformat() != str(closing_date):
                record["closing_date"] = None

        except (ValueError, TypeError):
            record["closing_date"] = None

    # Validate eligibility levels.
    levels = record.get("eligible_education_levels")

    if not isinstance(levels, list):
        record["eligible_education_levels"] = None
    else:
        record["eligible_education_levels"] = [
            str(level).strip()
            for level in levels
            if isinstance(level, str) and level.strip()
        ]

    # Validate required documents.
    documents = record.get("required_documents")

    if not isinstance(documents, list):
        record["required_documents"] = []
    else:
        record["required_documents"] = [
            str(document).strip()
            for document in documents
            if isinstance(document, str) and document.strip()
        ]

    # Validate scholarship criteria.
    criteria = record.get("criteria")

    if not isinstance(criteria, list):
        criteria = []

    valid_criteria = []

    for criterion in criteria:

        if not isinstance(criterion, dict):
            continue

        if (
            criterion.get("field") in FIELDS
            and criterion.get("op") in ("eq", "in", "lte", "gte")
            and criterion.get("value") is not None
        ):
            valid_criteria.append(criterion)

    record["criteria"] = valid_criteria or None

    # Validate benefit amount.
    benefit = record.get("benefit_amount")

    if benefit is not None:

        try:
            benefit = float(benefit)

            if benefit < 0:
                benefit = None

        except (ValueError, TypeError):
            benefit = None

    record["benefit_amount"] = benefit

    return record


# --------------------------------------------------
# ROUTE REGISTRATION
# --------------------------------------------------

def setup(app, user, db, err, now, SCH, el):

    def tdb():

        connection = db()

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ingested(
                id TEXT PRIMARY KEY,
                status TEXT,
                data TEXT
            );

            CREATE TABLE IF NOT EXISTS ingestion_audit(
                id TEXT PRIMARY KEY,
                ingest_id TEXT NOT NULL,
                admin_id TEXT NOT NULL,
                action TEXT NOT NULL,
                notes TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ingestion_source_versions(
                id TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                ingest_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                observed_at TEXT NOT NULL,
                UNIQUE(source_url, content_sha256)
            );
            """
        )

        return connection

    def admin(current_user):

        if current_user["role"] != "admin":
            raise err(
                "forbidden",
                "Administrator access required",
                403
            )

    # Load already published scholarships.
    for row in tdb().execute(
        "SELECT data FROM ingested WHERE status='Published'"
    ):

        SCH.append(
            json.loads(row["data"])["published_record"]
        )

    # --------------------------------------------------
    # INGEST SCHOLARSHIP
    # --------------------------------------------------

    @app.post(
        "/api/admin/sources/ingest",
        status_code=201
    )
    def ingest(b: Ingest, u=Depends(user)):

        admin(u)

        connection = tdb()

        # Extract scholarship using AI.
        record, method = extract(b.raw_text)

        # Reject irrelevant webpages.
        if not record.get("is_scholarship"):

            raise err(
                "not_scholarship",
                "The supplied content does not contain a valid scholarship announcement.",
                422
            )

        # Clean extracted information.
        record = clean(record)

        # Identify missing required fields.
        missing = [
            field
            for field in REQUIRED
            if not record.get(field)
        ]

        # Check possible duplicates.
        pool = [
            (scholarship["scholarship_id"], tokens(scholarship))
            for scholarship in SCH
        ]

        pending_records = connection.execute(
            "SELECT * FROM ingested WHERE status='Pending_Review'"
        )

        for row in pending_records:

            existing_data = json.loads(row["data"])

            pool.append(
                (
                    row["id"],
                    tokens(existing_data["record"])
                )
            )

        duplicates = []

        for existing_id, existing_tokens in pool:

            similarity = jaccard(
                tokens(record),
                existing_tokens
            )

            if similarity >= 0.90:

                duplicates.append(
                    {
                        "id": existing_id,
                        "similarity": round(similarity, 2)
                    }
                )

        # Generate ingestion ID.
        ingestion_id = str(uuid.uuid4())

        # Calculate source content hash.
        digest = hashlib.sha256(
            b.raw_text.encode("utf-8")
        ).hexdigest()

        # Check whether this exact source snapshot was processed before.
        prior = connection.execute(
            """
            SELECT ingest_id
            FROM ingestion_source_versions
            WHERE source_url=? AND content_sha256=?
            """,
            (b.source_url, digest)
        ).fetchone()

        if prior:

            existing = connection.execute(
                "SELECT status,data FROM ingested WHERE id=?",
                (prior["ingest_id"],)
            ).fetchone()

            if existing:

                return {
                    "ingest_id": prior["ingest_id"],
                    "status": existing["status"],
                    "duplicate_snapshot": True,
                    **json.loads(existing["data"])
                }

        # Calculate source version.
        version = connection.execute(
            """
            SELECT COALESCE(MAX(version_number),0)+1 AS n
            FROM ingestion_source_versions
            WHERE source_url=?
            """,
            (b.source_url,)
        ).fetchone()["n"]

        # Store source provenance.
        data = {
            "record": record,
            "missing_fields": missing,
            "possible_duplicates": duplicates,
            "provenance": {
                "source_url": b.source_url,
                "source_host": urlparse(b.source_url).hostname,
                "extracted_at": now(),
                "extraction_method": method,
                "content_sha256": digest,
                "source_version": version
            }
        }

        # Every extracted scholarship requires human review.
        connection.execute(
            "INSERT INTO ingested VALUES(?,?,?)",
            (
                ingestion_id,
                "Pending_Review",
                json.dumps(data)
            )
        )

        connection.execute(
            "INSERT INTO ingestion_source_versions VALUES(?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                b.source_url,
                digest,
                ingestion_id,
                version,
                now()
            )
        )

        connection.commit()

        return {
            "ingest_id": ingestion_id,
            "status": "Pending_Review",
            "verification_status": "Needs_Review",
            **data
        }

    # --------------------------------------------------
    # LIST INGESTED SCHOLARSHIPS
    # --------------------------------------------------

    @app.get("/api/admin/ingested")
    def lst(u=Depends(user)):

        admin(u)

        return [
            {
                "ingest_id": row["id"],
                "status": row["status"],
                **json.loads(row["data"])
            }
            for row in tdb().execute(
                "SELECT * FROM ingested ORDER BY rowid DESC"
            )
        ]

    # --------------------------------------------------
    # SOURCE VERSION HISTORY
    # --------------------------------------------------

    @app.get("/api/admin/ingested/source-versions")
    def source_versions(source_url: str, u=Depends(user)):

        admin(u)

        connection = tdb()

        rows = connection.execute(
            """
            SELECT version_number,content_sha256,ingest_id,observed_at
            FROM ingestion_source_versions
            WHERE source_url=?
            ORDER BY version_number DESC
            """,
            (source_url,)
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    # --------------------------------------------------
    # INGESTION DETAILS
    # --------------------------------------------------

    @app.get("/api/admin/ingested/{iid}")
    def detail(iid: str, u=Depends(user)):

        admin(u)

        connection = tdb()

        row = connection.execute(
            "SELECT * FROM ingested WHERE id=?",
            (iid,)
        ).fetchone()

        if not row:

            raise err(
                "not_found",
                "Ingestion record not found",
                404
            )

        data = json.loads(row["data"])

        audits = [
            dict(item)
            for item in connection.execute(
                """
                SELECT action,notes,created_at
                FROM ingestion_audit
                WHERE ingest_id=?
                ORDER BY created_at
                """,
                (iid,)
            )
        ]

        return {
            "ingest_id": iid,
            "status": row["status"],
            **data,
            "review_history": audits
        }

    # --------------------------------------------------
    # ADMIN PUBLISH / REJECT DECISION
    # --------------------------------------------------

    @app.post("/api/admin/ingested/{iid}/decision")
    def decide(iid: str, b: Decision, u=Depends(user)):

        admin(u)

        connection = tdb()

        row = connection.execute(
            "SELECT * FROM ingested WHERE id=?",
            (iid,)
        ).fetchone()

        if not row or row["status"] != "Pending_Review":

            raise err(
                "not_found",
                "No pending record with this id",
                404
            )

        data = json.loads(row["data"])

        # REJECT
        if b.decision == "reject":

            connection.execute(
                "UPDATE ingested SET status='Rejected' WHERE id=?",
                (iid,)
            )

            connection.execute(
                "INSERT INTO ingestion_audit VALUES(?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    iid,
                    u["id"],
                    "Rejected",
                    b.verification_notes,
                    now()
                )
            )

            connection.commit()

            return {
                "status": "Rejected"
            }

        # PUBLISH
        if b.verification != "Human_Verified":

            raise err(
                "human_verification_required",
                "Automated checks cannot certify a scholarship source",
                409
            )

        if data["missing_fields"]:

            raise err(
                "incomplete",
                "Required fields are missing; cannot publish",
                409,
                {
                    "missing": data["missing_fields"]
                }
            )

        if data["possible_duplicates"] and not b.allow_duplicate:

            raise err(
                "possible_duplicate",
                "Possible duplicate; review or set allow_duplicate",
                409,
                {
                    "duplicates": data["possible_duplicates"]
                }
            )

        record = data["record"]

        published_record = {
            "scholarship_id": str(uuid.uuid4()),
            "scholarship_name": record["scholarship_name"],
            "provider_name": record["provider_name"],
            "provider_type": "Other",
            "description": record.get("description") or "",
            "benefit_amount": record.get("benefit_amount") or 0,
            "currency": "INR",
            "benefit_frequency": "Unknown",
            "eligible_education_levels": record["eligible_education_levels"],
            "required_documents": record["required_documents"],
            "opening_date": None,
            "closing_date": record["closing_date"],
            "application_url": None,
            "official_source_url": data["provenance"]["source_url"],
            "renewal_available": False,
            "verification_status": b.verification,
            "last_verified_at": now(),
            "is_demo": False,
            "criteria": record["criteria"]
        }

        data["published_record"] = published_record

        data["verification"] = {
            "status": "Human_Verified",
            "verified_by": u["id"],
            "verified_at": now(),
            "notes": b.verification_notes
        }

        SCH.append(published_record)

        connection.execute(
            """
            UPDATE ingested
            SET status='Published',data=?
            WHERE id=?
            """,
            (
                json.dumps(data),
                iid
            )
        )

        connection.execute(
            "INSERT INTO ingestion_audit VALUES(?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                iid,
                u["id"],
                "Published",
                b.verification_notes,
                now()
            )
        )

        connection.commit()

        return {
            "status": "Published",
            "scholarship_id": published_record["scholarship_id"],
            "verification_status": "Human_Verified"
        }

    # --------------------------------------------------
    # AI USAGE
    # --------------------------------------------------

    @app.get("/api/admin/ai-usage")
    def usage(u=Depends(user)):

        admin(u)

        return {
            "requests_by_provider": ai.usage,
            "estimated_cost": "0 (free tier / local only; paid usage is never enabled)",
            "note": "In-memory; resets on restart."
        }