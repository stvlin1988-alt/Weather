from datetime import datetime, timedelta
from flask import request
from flask_login import current_user
from flask_socketio import emit
from extensions import db
from models import Note, Store, NoteLog, User, STATUS_CHOICES, PRIORITY_CHOICES


def register_ws_events(socketio):

    @socketio.on('connect')
    def handle_connect():
        if not current_user.is_authenticated:
            return False

    @socketio.on('d')
    def handle_data(data):
        if not current_user.is_authenticated:
            emit('r', {'op': 'er', 'message': 'unauthorized'})
            return
        op = data.get('op', '')
        try:
            if op == 'ln': _list_notes(data)
            elif op == 'cn': _create_note(data)
            elif op == 'un': _update_note(data)
            elif op == 'dn': _delete_note(data)
            elif op == 'gn': _get_note(data)
            elif op == 'as': _ai_summary(data)
            else: emit('r', {'op': 'er', 'message': 'unknown op'})
        except Exception as e:
            emit('r', {'op': 'er', 'message': str(e)})

    @socketio.on('p')
    def handle_padding(data):
        pass

    def _get_stores():
        return [s.name for s in Store.query.order_by(Store.name).all()]

    def _list_notes(data):
        store_filter = data.get('store', '')
        status_filter = data.get('status', '')
        range_param = data.get('range', '3d')
        stores = _get_stores()
        query = Note.query
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
        range_days = {'today': 0, '3d': 3, '5d': 5, '7d': 7}
        days = range_days.get(range_param, 3)
        if days == 0:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Note.updated_at >= since)
        if status_filter in STATUS_CHOICES:
            query = query.filter_by(status=status_filter)
        notes = query.order_by(Note.updated_at.desc()).all()
        emit('r', {'op': 'ln', 'notes': [{
            'id': n.id, 'title': n.title, 'content': n.content,
            'store': n.store, 'status': n.status or 'pending',
            'priority': n.priority or 'medium',
            'author': n.author.username if n.author else '',
            'created_at': n.created_at.isoformat() if n.created_at else '',
            'updated_at': n.updated_at.isoformat() if n.updated_at else '',
        } for n in notes]})

    def _create_note(data):
        stores = _get_stores()
        now = datetime.utcnow()
        if current_user.is_admin():
            store = data.get('store') if data.get('store') in stores else None
        else:
            store = current_user.store if current_user.store in stores else None
        status = data.get('status') if data.get('status') in STATUS_CHOICES else 'pending'
        priority = data.get('priority') if data.get('priority') in PRIORITY_CHOICES else 'medium'
        note = Note(
            user_id=current_user.id,
            title=data.get('title', '未命名筆記'),
            content=data.get('content', ''),
            store=store, status=status, priority=priority,
            created_at=now, updated_at=now,
        )
        db.session.add(note)
        db.session.commit()
        emit('r', {'op': 'cn', 'status': 'ok', 'id': note.id})

    def _update_note(data):
        note_id = data.get('id')
        if current_user.is_admin():
            note = Note.query.get(note_id)
        else:
            note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
        if not note:
            emit('r', {'op': 'er', 'message': 'not found'})
            return
        stores = _get_stores()
        diff_parts = []
        if 'title' in data and data['title'] != note.title:
            diff_parts.append(f"標題: {note.title} → {data['title']}")
            note.title = data['title']
        if 'content' in data and data['content'] != note.content:
            diff_parts.append(f"內容長度: {len(note.content)} → {len(data['content'])} 字")
            note.content = data['content']
        if 'store' in data and current_user.is_admin():
            note.store = data['store'] if data['store'] in stores else None
        if 'status' in data and data['status'] in STATUS_CHOICES:
            if data['status'] != note.status:
                diff_parts.append(f"狀態: {note.status} → {data['status']}")
            note.status = data['status']
        if 'priority' in data and data['priority'] in PRIORITY_CHOICES:
            if data['priority'] != note.priority:
                diff_parts.append(f"優先度: {note.priority} → {data['priority']}")
            note.priority = data['priority']
        note.updated_by = current_user.id
        note.updated_at = datetime.utcnow()
        db.session.flush()
        if diff_parts:
            log = NoteLog(note_id=note.id, note_title=note.title, user_id=current_user.id, action='edit', diff='; '.join(diff_parts))
            db.session.add(log)
        db.session.commit()
        emit('r', {'op': 'un', 'status': 'ok'})

    def _delete_note(data):
        note_id = data.get('id')
        if current_user.is_admin():
            note = Note.query.get(note_id)
        else:
            note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
        if not note:
            emit('r', {'op': 'er', 'message': 'not found'})
            return
        log = NoteLog(note_id=note.id, note_title=note.title, user_id=current_user.id, action='delete')
        db.session.add(log)
        db.session.delete(note)
        db.session.commit()
        emit('r', {'op': 'dn', 'status': 'ok'})

    def _get_note(data):
        note_id = data.get('id')
        if current_user.is_admin():
            note = Note.query.get(note_id)
        else:
            note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
        if not note:
            emit('r', {'op': 'er', 'message': 'not found'})
            return
        updater = None
        if note.updated_by:
            u = User.query.get(note.updated_by)
            updater = u.username if u else None
        emit('r', {'op': 'gn', 'note': {
            'id': note.id, 'title': note.title, 'content': note.content,
            'store': note.store, 'status': note.status or 'pending',
            'priority': note.priority or 'medium', 'updated_by': updater,
            'created_at': n.created_at.isoformat() if n.created_at else '',
            'updated_at': n.updated_at.isoformat() if n.updated_at else '',
        }})

    def _ai_summary(data):
        if not current_user.is_admin():
            emit('r', {'op': 'er', 'message': '僅限管理員'})
            return
        from admin.routes import call_llm
        store = data.get('store', 'all')
        days = int(data.get('days', 7))
        since = datetime.utcnow() - timedelta(days=days)
        valid_stores = [s.name for s in Store.query.all()]
        query = Note.query.filter(Note.updated_at >= since)
        if store != 'all' and store in valid_stores:
            query = query.filter_by(store=store)
        notes = query.order_by(Note.store, Note.updated_at.desc()).all()
        if not notes:
            emit('r', {'op': 'as', 'status': 'ok', 'summary': '（近期無筆記）'})
            return
        STATUS_LABELS = {'pending': '待處理', 'in_progress': '處理中', 'resolved': '已解決'}
        PRIORITY_LABELS = {'high': '高', 'medium': '中', 'low': '低'}
        lines = []
        for n in notes:
            s_label = STATUS_LABELS.get(n.status or 'pending', n.status)
            p_label = PRIORITY_LABELS.get(n.priority or 'medium', n.priority)
            store_tag = f"[{n.store}店]" if n.store else "[未分店]"
            author = n.author.username if n.author else "?"
            date_str = n.updated_at.strftime("%m/%d") if n.updated_at else ""
            lines.append(f"{store_tag}[{date_str}][{author}][{s_label}][優先:{p_label}] {n.title}\n{n.content}")
        store_label = f"「{store}店」" if store != 'all' else "全店"
        if store == 'all':
            prompt = (f"以下是{store_label}近 {days} 天的員工筆記：\n\n" + "\n---\n".join(lines)
                + "\n\n請用繁體中文，依以下結構整理：\n1. 第一層：依「店別」分類\n2. 第二層：每間店內依「優先權」排列（高→中→低）\n3. 相關的事項請合併成一條摘要，不要逐條列出\n4. 最後給主管一個「建議優先處理順序」，說明應該先處理哪件事、為什麼\n請用 Markdown 格式回覆。")
        else:
            prompt = (f"以下是{store_label}近 {days} 天的員工筆記：\n\n" + "\n---\n".join(lines)
                + f"\n\n請用繁體中文，依以下結構整理：\n1. 先標明這是「{store}店」的摘要\n2. 依「優先權」排列（高→中→低）\n3. 相關的事項請合併成一條摘要，不要逐條列出\n4. 最後給主管一個「建議優先處理順序」，說明應該先處理哪件事、為什麼\n請用 Markdown 格式回覆。")
        try:
            summary = call_llm(prompt, max_tokens=2048)
            emit('r', {'op': 'as', 'status': 'ok', 'summary': summary})
        except Exception as e:
            emit('r', {'op': 'er', 'message': str(e)})
