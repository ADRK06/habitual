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

    app.register_blueprint(auth_blueprint)
    app.register_blueprint(habits_blueprint)
    app.register_blueprint(rooms_blueprint)
    app.cli.add_command(dev_backdate)

    @app.get("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("habits.dashboard"))
        return render_template("landing.html")

    return app
