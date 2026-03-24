def post_fork(server, worker):
    from extensions import db
    db.engine.dispose()
