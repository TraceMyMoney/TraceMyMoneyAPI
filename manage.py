# Library imports
from flask.cli import FlaskGroup

# Direct Imports
from src.main import create_app

# Creating the app
app, celery = create_app()

if __name__ == "__main__":
    cli = FlaskGroup(create_app)
    cli()
