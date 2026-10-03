from flask import Flask, redirect, render_template, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

from habitual.config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"

    from habitual import models  # noqa: F401 registers models with SQLAlchemy/Migrate
    from habitual.auth import auth as auth_blueprint
    from habitual.habits import habits as habits_blueprint
    from habitual.rooms import rooms as rooms_blueprint
    from habitual.cli import dev_backdate
    from habitual.errors import not_found, server_error

    app.register_blueprint(auth_blueprint)
    app.register_blueprint(habits_blueprint)
    app.register_blueprint(rooms_blueprint)
    app.cli.add_command(dev_backdate)
    app.register_error_handler(404, not_found)
    app.register_error_handler(500, server_error)

    @app.get("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("habits.dashboard"))
        return render_template("landing.html")

    # Dev-only logo preview - not linked anywhere, remove once a variation
    # is picked (see CLAUDE.md's Logo roadmap note).
    @app.get("/dev/logos")
    def dev_logos():
        variations = [
            {
                "letter": "A", "name": "Framed", "file": "logo-icon-a.svg",
                "description": "Navy-framed capsules (navy outer pill, yellow inset) with a crimson check - closest to the reference's two-tone capsules, flattened.",
            },
            {
                "letter": "B", "name": "Tile badge", "file": "logo-icon-b.svg",
                "description": "Navy rounded-square tile with solid yellow capsules and a crimson check - app-icon shaped, built for favicon contrast.",
            },
            {
                "letter": "C", "name": "Bold flat", "file": "logo-icon-c.svg",
                "description": "Solid yellow capsules, no frame, crimson check - the simplest shapes, for the best legibility at 16px.",
            },
        ]
        return render_template("dev/logos.html", variations=variations)

    return app
