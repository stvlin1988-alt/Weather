# Nine Feature Changes — Design Spec

**Date**: 2026-04-08
**Status**: Approved

---

## 1. AI Summary "Today" = 08:00–08:00 Business Day

The "today" / "1 day" time range uses a business-day concept anchored at 08:00 Taiwan time (UTC+8).

- If current time (UTC+8) >= 08:00 → range = today 08:00 ~ tomorrow 08:00
- If current time (UTC+8) < 08:00 → range = yesterday 08:00 ~ today 08:00

Applies to:
- `_date_filter()` for "today" range in notes list
- `notes_ai_summary()` when `days=1`
- `saveSummaryAsNote()` title date should reflect the business day

## 2. Enlarge Author/Time in Notes

- `editor.html` `.updated-by-info` font: 0.78rem → 0.85rem
- `index.html` note card author/time meta: 0.72rem → 0.85rem
- `created_at` is never modified on edit (already the case)
- `updated_at` updates on edit, NoteLog records diff (already the case)

## 3. Mutually Exclusive Filters

Three filter groups on the notes index page: **Priority**, **Date Range**, **Status**.

Only one group active at a time (mutually exclusive):
- Add **Priority tabs**: All / High / Medium / Low
- Selecting a priority filter → ignores date range and status, shows all notes with that priority
- Selecting a status filter → ignores date range and priority
- Selecting a date range → ignores priority and status

Backend: determine which filter is active via query param (`priority`, `status`, or `range`). Only one filter type applied per request.

## 4. WASM Timeout 15s → 6s

Change `TIMEOUT_MS` in `wasm/src/lib.rs` from 15000.0 to 6000.0. Recompile WASM. The existing `ACT_CLEANUP` → `_x()` already clears all injected DOM.

## 5. Remove Tap Animation on Weather Page

Add CSS to weather `index.html` to suppress all visual feedback on `#tap-target`:
```css
#tap-target { -webkit-tap-highlight-color: transparent; user-select: none; outline: none; }
```

## 6. Admin Restricted to Own Store

- `notes/routes.py` `index()`, `list_notes()`, `get_note()`, `update_note()`, `delete_note()`: admin sees only their own store's notes; super_admin sees all
- AI summary: admin can only summarize their own store (no "all stores" option); super_admin retains all-store access
- Frontend: admin sees no store tabs and no "all stores" AI option
- `editor.html`: admin's store selector is read-only (shows their store)

## 7. Admin/Super_admin Can Edit Any (In-Scope) Note + Log

- super_admin: can edit any note across all stores
- admin: can edit any note in their own store (enforced by #6)
- Both already update `updated_by` and create `NoteLog` entries on edit — no additional backend changes needed beyond #6 scope restrictions

## 8. Add User Panel in Admin Dashboard

New card in `admin/dashboard.html` with fields:
- Username (text)
- PIN (4-digit, password)
- Store (dropdown, required for admin/user roles)
- Role (dropdown: user/admin/super_admin)
- Face photo (camera button + capture)

**Validation**: admin and user roles MUST select a store. super_admin does not require store. Show error toast if store is missing.

Backend: uses existing `/admin/users/create` API. Add `role` field support to that endpoint.

## 9. Multi-User Login on Same Device

- Keep existing device approval flow (approve creates account + binds user_id)
- Change `is_device_authorized()`: only check `is_approved && !is_revoked`, ignore user_id/user state
- Login via `/auth/verify`: PIN + face match against ALL active users, not limited to device-bound user
- Store OFF check remains at login verification time (already in place)

Result: any approved device allows any registered active user to log in with PIN + face.
