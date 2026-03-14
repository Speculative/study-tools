from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    from .routes import bp as web_bp

    app.register_blueprint(web_bp)

    return app
