from flask import Flask
from .api import api
from .db import init_db
from ..config import Config

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize directories
    config_class.init_app(app)

    # Initialize MongoDB
    init_db(app)

    # Register blueprints
    app.register_blueprint(api)

    return app
