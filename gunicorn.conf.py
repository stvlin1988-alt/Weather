def post_fork(server, worker):
    from wsgi import app
    from extensions import db
    with app.app_context():
        db.engine.dispose()
