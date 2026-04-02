import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from extensions import db
from models import Note, Store, NoteLog, STATUS_CHOICES, PRIORITY_CHOICES
from admin.routes import call_llm

notes_bp = Blueprint("notes", __name__, url_prefix="/notes")

RANGE_DAYS = {"today": 0, "3d": 3, "5d": 5, "7d": 7}

# 異步 AI 任務存儲（in-memory）
_ai_tasks = {}


def _get_stores():
    return [s.name for s in Store.query.order_by(Store.name).all()]


def _date_filter(query, range_param):
    days = RANGE_DAYS.get(range_param, 3)
    if days == 0:
        since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        since = datetime.utcnow() - timedelta(days=days)
    return query.filter(Note.updated_at >= since)


@notes_bp.route("/")
@login_required
def index():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    range_param = request.args.get("range", "3d")
    stores = _get_stores()

    query = Note.query
    if current_user.is_admin():
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
    else:
        # 一般 user 只能看自己店的筆記
        query = query.filter_by(store=current_user.store)

    query = _date_filter(query, range_param)
    if status_filter in STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    notes = query.order_by(Note.updated_at.desc()).all()

    return render_template("notes/index.html", notes=notes, stores=stores,
                           current_store=store_filter, status_choices=STATUS_CHOICES,
                           current_status=status_filter, current_range=range_param,
                           priority_choices=PRIORITY_CHOICES)


@notes_bp.route("/new", methods=["GET"])
@login_required
def new_note():
    stores = _get_stores()
    return render_template("notes/editor.html", note=None, stores=stores,
                           status_choices=STATUS_CHOICES, priority_choices=PRIORITY_CHOICES)


@notes_bp.route("/api", methods=["GET"])
@login_required
def list_notes():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    range_param = request.args.get("range", "3d")
    stores = _get_stores()

    query = Note.query
    if current_user.is_admin():
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
    else:
        query = query.filter_by(store=current_user.store)

    query = _date_filter(query, range_param)
    if status_filter in STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    notes = query.order_by(Note.updated_at.desc()).all()

    return jsonify([{
        "id": n.id, "title": n.title, "content": n.content,
        "store": n.store, "status": n.status or "pending",
        "priority": n.priority or "medium",
        "author": n.author.username if n.author else "",
        "created_at": n.created_at.isoformat() if n.created_at else "",
        "updated_at": n.updated_at.isoformat() if n.updated_at else "",
    } for n in notes])


@notes_bp.route("/api", methods=["POST"])
@login_required
def create_note():
    data = request.get_json(silent=True) or {}
    stores = _get_stores()
    now = datetime.utcnow()
    if current_user.is_admin():
        store = data.get("store") if data.get("store") in stores else None
    else:
        store = current_user.store if current_user.store in stores else None
    status = data.get("status") if data.get("status") in STATUS_CHOICES else "pending"
    priority = data.get("priority") if data.get("priority") in PRIORITY_CHOICES else "medium"
    note = Note(
        user_id=current_user.id,
        title=data.get("title", "未命名筆記"),
        content=data.get("content", ""),
        store=store,
        status=status,
        priority=priority,
        created_at=now,
        updated_at=now,
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({"status": "ok", "id": note.id}), 201


@notes_bp.route("/api/<int:note_id>", methods=["GET"])
@login_required
def get_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    updater = None
    if note.updated_by:
        from models import User
        u = User.query.get(note.updated_by)
        updater = u.username if u else None
    return jsonify({
        "id": note.id, "title": note.title, "content": note.content,
        "store": note.store, "status": note.status or "pending",
        "priority": note.priority or "medium",
        "ai_summary": note.ai_summary, "ai_outline": note.ai_outline,
        "updated_by": updater,
        "created_at": note.created_at.isoformat() if note.created_at else "",
        "updated_at": note.updated_at.isoformat() if note.updated_at else "",
    })


@notes_bp.route("/api/<int:note_id>", methods=["PUT"])
@login_required
def update_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    data = request.get_json(silent=True) or {}
    stores = _get_stores()

    diff_parts = []
    if "title" in data and data["title"] != note.title:
        diff_parts.append(f"標題: {note.title} → {data['title']}")
        note.title = data["title"]
    if "content" in data and data["content"] != note.content:
        old_len = len(note.content)
        new_len = len(data["content"])
        diff_parts.append(f"內容長度: {old_len} → {new_len} 字")
        note.content = data["content"]
    if "store" in data and current_user.is_admin():
        note.store = data["store"] if data["store"] in stores else None
    if "status" in data and data["status"] in STATUS_CHOICES:
        if data["status"] != note.status:
            diff_parts.append(f"狀態: {note.status} → {data['status']}")
        note.status = data["status"]
    if "priority" in data and data["priority"] in PRIORITY_CHOICES:
        if data["priority"] != note.priority:
            diff_parts.append(f"優先度: {note.priority} → {data['priority']}")
        note.priority = data["priority"]

    note.updated_by = current_user.id
    note.updated_at = datetime.utcnow()
    db.session.flush()

    if diff_parts:
        log = NoteLog(
            note_id=note.id,
            note_title=note.title,
            user_id=current_user.id,
            action="edit",
            diff="; ".join(diff_parts),
        )
        db.session.add(log)

    db.session.commit()
    return jsonify({"status": "ok"})


@notes_bp.route("/api/<int:note_id>", methods=["DELETE"])
@login_required
def delete_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    log = NoteLog(
        note_id=note.id,
        note_title=note.title,
        user_id=current_user.id,
        action="delete",
    )
    db.session.add(log)
    db.session.delete(note)
    db.session.commit()
    return jsonify({"status": "ok"})


MANAGER_PROMPT = """# Role
你是一位專業的店務連鎖店總管，負責將各分店或各部門的雜亂筆記，快速整理成給老闆看的「每日彙整表」。

# Task
請將輸入的所有原始文字進行分類摘要。要求：
1. **不准遺漏**：每個提到的事件都必須轉換成一條列點。
2. **極度精簡**：刪除所有口語、形容詞、抱怨與重複資訊，僅保留「主語 + 動作 + 結果」。
3. **模糊分類**：若某事項不確定分類，優先放入【店務】，若完全無關則放入【雜項】。

# Categories
- 【人事】：請假、遲到、排班、人力短缺、獎懲。
- 【修繕】：設備故障、漏水、燈泡更換、報修進度。
- 【店務】：進貨、庫存、營收、活動、顧客反應、環境衛生。
- 【雜項】：不屬於上述三類的所有事項。

# Output Style
使用 Markdown 列表。範例：
- [修繕] 廚房冰箱漏水：已請廠商週三來修。
- [人事] 小明午班請假：已協調小華代班。
"""


def _run_ai_task(task_id, app, prompt, max_tokens, note_id=None, field=None):
    """在 gevent greenlet 中執行 LLM 呼叫"""
    with app.app_context():
        try:
            result = call_llm(prompt, max_tokens=max_tokens)
            if note_id and field:
                note = Note.query.get(note_id)
                if note:
                    setattr(note, field, result)
                    note.updated_at = datetime.utcnow()
                    db.session.commit()
            _ai_tasks[task_id] = {"status": "done", "result": result}
        except Exception as e:
            _ai_tasks[task_id] = {"status": "error", "message": str(e)}


@notes_bp.route("/ai/task/<task_id>", methods=["GET"])
@login_required
def get_ai_task(task_id):
    """輪詢 AI 任務狀態"""
    if not current_user.is_admin():
        return jsonify({"status": "error", "message": "僅限管理員"}), 403
    task = _ai_tasks.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": "任務不存在"}), 404
    if task["status"] == "done":
        result = task["result"]
        del _ai_tasks[task_id]
        return jsonify({"status": "done", "result": result})
    if task["status"] == "error":
        msg = task["message"]
        del _ai_tasks[task_id]
        return jsonify({"status": "error", "message": msg})
    return jsonify({"status": "processing"})


def _build_all_content(store_name=None):
    """收集同店所有筆記，合併成 all_content，每段標註來源"""
    query = Note.query
    if store_name:
        query = query.filter_by(store=store_name)
    notes = query.order_by(Note.updated_at.desc()).all()
    parts = []
    for n in notes:
        source = f"【檔名：{n.store or '未分店'}店_{n.author.username if n.author else '?'}_{n.updated_at.strftime('%m%d') if n.updated_at else ''}_{n.id}】"
        parts.append(f"{source}\n{n.title}\n{n.content}")
    return "\n\n---\n\n".join(parts), len(notes)


@notes_bp.route("/api/<int:note_id>/summarize", methods=["POST"])
@login_required
def summarize(note_id):
    if not current_user.is_admin():
        return jsonify({"status": "error", "message": "僅限管理員"}), 403
    note = Note.query.get_or_404(note_id)

    # 收集同店所有筆記合併，一次呼叫 API 做全體分類摘要
    all_content, count = _build_all_content(note.store)
    prompt = (
        MANAGER_PROMPT
        + f"\n# 待整理筆記（{note.store or '未分店'}店，共 {count} 筆）\n\n{all_content}"
    )
    task_id = uuid.uuid4().hex[:12]
    _ai_tasks[task_id] = {"status": "processing"}
    import gevent
    gevent.spawn(_run_ai_task, task_id, current_app._get_current_object(),
                 prompt, 2048, note_id, "ai_summary")
    return jsonify({"status": "accepted", "task_id": task_id})


@notes_bp.route("/api/<int:note_id>/outline", methods=["POST"])
@login_required
def outline(note_id):
    if not current_user.is_admin():
        return jsonify({"status": "error", "message": "僅限管理員"}), 403
    note = Note.query.get_or_404(note_id)

    # 單筆大綱：只處理這一篇
    source = f"【檔名：{note.store or '未分店'}店_{note.author.username if note.author else '?'}_{note.id}】"
    prompt = (
        MANAGER_PROMPT
        + "\n# 額外要求\n請將此筆記整理成條列式大綱，保留所有細節。\n"
        + f"\n# 待整理筆記\n\n{source}\n{note.title}\n{note.content}"
    )
    task_id = uuid.uuid4().hex[:12]
    _ai_tasks[task_id] = {"status": "processing"}
    import gevent
    gevent.spawn(_run_ai_task, task_id, current_app._get_current_object(),
                 prompt, 1024, note_id, "ai_outline")
    return jsonify({"status": "accepted", "task_id": task_id})


@notes_bp.route("/ai/summary", methods=["POST"])
@login_required
def notes_ai_summary():
    if not current_user.is_admin():
        return jsonify({"status": "error", "message": "僅限管理員"}), 403
    data = request.get_json(silent=True) or {}
    store = data.get("store", "all")
    days = int(data.get("days", 7))
    since = datetime.utcnow() - timedelta(days=days)

    valid_stores = [s.name for s in Store.query.all()]
    query = Note.query.filter(Note.updated_at >= since)
    if store != "all" and store in valid_stores:
        query = query.filter_by(store=store)
    notes = query.order_by(Note.store, Note.updated_at.desc()).all()

    if not notes:
        return jsonify({"status": "ok", "summary": "（近期無筆記）"})

    # 合併所有筆記成 all_content，每段標註檔名來源
    parts = []
    for n in notes:
        source = f"【檔名：{n.store or '未分店'}店_{n.author.username if n.author else '?'}_{n.updated_at.strftime('%m%d') if n.updated_at else ''}_{n.id}】"
        parts.append(f"{source}\n{n.title}\n{n.content}")
    all_content = "\n\n---\n\n".join(parts)

    store_label = f"「{store}店」" if store != "all" else "全店"
    extra = ""
    if store == "all":
        extra = "\n# 額外要求\n請在輸出最前面依「店別」分組，每組內再依上述分類排列。\n"
    else:
        extra = f"\n# 額外要求\n請在輸出最前面標明這是「{store}店」的彙整。\n"

    prompt = (
        MANAGER_PROMPT + extra
        + f"\n# 待整理筆記（{store_label}近 {days} 天，共 {len(notes)} 筆）\n\n{all_content}"
    )

    task_id = uuid.uuid4().hex[:12]
    _ai_tasks[task_id] = {"status": "processing"}
    import gevent
    gevent.spawn(_run_ai_task, task_id, current_app._get_current_object(),
                 prompt, 2048)
    return jsonify({"status": "accepted", "task_id": task_id})


@notes_bp.route("/<int:note_id>")
@login_required
def edit_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    stores = _get_stores()
    return render_template("notes/editor.html", note=note, stores=stores,
                           status_choices=STATUS_CHOICES, priority_choices=PRIORITY_CHOICES)
