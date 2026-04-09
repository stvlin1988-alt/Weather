# Note Attachments — Design Spec

**Date**: 2026-04-09
**Status**: Approved

---

## Overview

Allow users to upload images and videos as attachments to notes. Files are stored in Cloudflare R2 (existing infrastructure). Attachments follow note permissions — anyone who can view the note can view its attachments.

---

## Storage

- **Backend**: Cloudflare R2 (S3-compatible), reuse existing `storage.py` module
- **Path format**: `attachments/{note_id}/{uuid}.{ext}`
- **Allowed image types**: JPEG, PNG, GIF, WebP
- **Allowed video types**: MP4, MOV, WebM
- **Max file size**: 50 MB per file
- **Max count**: Unlimited
- **Retention**: Permanent — deleted only when attachment is manually deleted or parent note is deleted (cascade)

---

## Database

New model `NoteAttachment`:

```python
class NoteAttachment(db.Model):
    __tablename__ = "note_attachments"

    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.Integer, db.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    object_key = db.Column(db.Text, nullable=False)       # R2 path
    filename = db.Column(db.Text, nullable=False)          # original filename
    content_type = db.Column(db.Text, nullable=False)      # MIME type
    file_size = db.Column(db.Integer, nullable=False)      # bytes
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    note = db.relationship("Note", backref=db.backref("attachments", lazy=True, cascade="all, delete-orphan"))
    uploader = db.relationship("User", foreign_keys=[user_id])
```

---

## API Endpoints

All endpoints require authentication. Permission follows note visibility (same store = can access).

### Upload

`POST /notes/api/attachments/upload`

- Content-Type: `multipart/form-data`
- Fields: `file` (the file), `note_id` (integer)
- Validates: file type, file size (50 MB), note exists, user has access to note
- Uploads to R2, creates `NoteAttachment` record
- Returns: `{ "status": "ok", "attachment": { "id", "filename", "content_type", "file_size", "url" } }`

### List (per note)

`GET /notes/api/attachments?note_id=<id>`

- Returns all attachments for a note with signed URLs
- User must have access to the note (same store check)

### Delete

`DELETE /notes/api/attachments/<attachment_id>`

- Only note author, admin (same store), or super_admin can delete
- Deletes from R2 + database record

### Note Deletion Cascade

When a note is deleted (HTTP or WebSocket), all associated `NoteAttachment` records are cascade-deleted by SQLAlchemy. R2 objects are also deleted in a loop before the DB delete.

---

## Frontend

### Upload UI (in note editor)

- Add upload button below the note content textarea (camera icon + paperclip icon)
- On mobile: offers camera capture or file picker
- Upload via `fetch` with `FormData`, show progress bar during upload
- After upload: append thumbnail/filename to attachment list below editor

### Attachment Display (in note view & editor)

- Below note content, show attachment list
- **Images**: thumbnail preview (max 200px width), click to view full-screen overlay
- **Videos**: show video element with native controls, poster frame if available
- Each attachment shows: filename, file size, delete button (if permitted)

### Full-screen Image Preview

- Click thumbnail → full-screen dark overlay with the image centered
- Click overlay or X button to close
- Pinch-to-zoom on mobile via CSS `touch-action: pinch-zoom`

---

## Permission Rules

| Action | user (same store) | admin (same store) | super_admin |
|--------|-------------------|--------------------|-------------|
| View attachments | Yes | Yes | Yes |
| Upload to own note | Yes | Yes | Yes |
| Upload to others' note | No | Yes | Yes |
| Delete own attachment | Yes | Yes | Yes |
| Delete others' attachment | No | Yes | Yes |

---

## Files Changed

| File | Change |
|------|--------|
| `models.py` | Add `NoteAttachment` model |
| `storage.py` | Add `upload_attachment()`, `delete_attachment()`, `list_attachment_urls()` |
| `notes/routes.py` | Add upload/list/delete API endpoints |
| `notes/ws.py` | Include attachment count/URLs in note list/get responses; delete R2 files on note delete |
| `templates/notes/index.html` | Upload UI, attachment display, full-screen preview |
| `templates/notes/editor.html` | Upload button + attachment list in editor |
