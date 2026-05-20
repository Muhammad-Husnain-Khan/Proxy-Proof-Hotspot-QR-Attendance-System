from flask import Flask
from config import Config
from extensions import db
from routes import main

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    app.register_blueprint(main)

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    # Binding to 0.0.0.0 is critical for local network access
    app.run(host='0.0.0.0', port=5000, debug=True)
