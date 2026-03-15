from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    from .routes import bp as web_bp, _seconds_to_ts

    app.register_blueprint(web_bp)
    app.jinja_env.filters["ts"] = _seconds_to_ts

    return app
