import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 1
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
timeout = 600
keepalive = 2
accesslog = "-"
errorlog = "-"
loglevel = "info"


def post_fork(server, worker):
    from wsgi import app
    from extensions import db
    with app.app_context():
        db.engine.dispose()
