from flask import Flask, g


def create_app() -> Flask:
    app = Flask(__name__)

    from .routes import bp as web_bp, _seconds_to_ts

    app.register_blueprint(web_bp)
    app.jinja_env.filters["ts"] = _seconds_to_ts

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            if exc is None:
                db.conn.commit()
            db.conn.close()

    return app
