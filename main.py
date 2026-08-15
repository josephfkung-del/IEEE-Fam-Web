import base64

from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from api.index import app, fetch_all, fetch_one, serialize_row, templates


@app.get("/media", response_class=HTMLResponse)
def media_page(request: Request):
    return templates.TemplateResponse("media.html", {"request": request})


@app.get("/api/media")
def media_feed(limit: int = 18, offset: int = 0, family: str = ""):
    limit = max(1, min(limit, 48))
    offset = max(0, offset)
    params = []
    family_clause = ""
    if family.strip():
        family_clause = " AND family_name = ?"
        params.append(family.strip())
    params.extend([limit + 1, offset])
    rows = fetch_all(
        f"""
        SELECT id, family_name, event_title, event_date, event_type, description,
               member_count, points_awarded, reviewed_at
        FROM familieee_submissions
        WHERE status = 'approved'{family_clause}
        ORDER BY event_date DESC, reviewed_at DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "events": [serialize_row(row) for row in rows],
        "has_more": has_more,
        "next_offset": offset + len(rows),
    }


@app.get("/api/media/{submission_id}/photo")
def media_photo(submission_id: str):
    row = fetch_one(
        "SELECT photo_data, photo_mime FROM familieee_submissions WHERE id = ? AND status = 'approved'",
        (submission_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    data_url = row.get("photo_data") or ""
    try:
        header, payload = data_url.split(",", 1)
        media_type = row.get("photo_mime") or header.split(";", 1)[0].replace("data:", "") or "image/jpeg"
        image_bytes = base64.b64decode(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Invalid stored photo") from exc
    return Response(
        content=image_bytes,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"},
    )
