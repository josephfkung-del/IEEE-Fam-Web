# IEEE FamilIEEEs Event Review App

A small FastAPI web app for FamilIEEE event proof submissions and admin approval.

## Features
- Member event submissions with photo proof, description, family name, date, attendees, and rule confirmations.
- Client-side image resizing/compression before upload.
- Password-protected admin dashboard.
- Approve / deny workflow with editable point awards and reviewer notes.
- Rule flags for the FamilIEEE minimum-event requirements.
- Public leaderboard based only on approved points.
- Neon Postgres in production; SQLite fallback for local development.

## Local run
```bash
export ADMIN_PASSWORD='your-password'
export SESSION_SECRET='your-long-random-secret'
uvicorn api.index:app --reload
```
Open http://127.0.0.1:8000

## Production variables
Set `DATABASE_URL`, `ADMIN_PASSWORD`, and `SESSION_SECRET`.
