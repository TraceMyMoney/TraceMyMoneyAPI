# Library imports
from flask.cli import FlaskGroup

# Direct Imports
from src_restful.main import create_app

# Creating the app
app = create_app()

if __name__ == "__main__":
    cli = FlaskGroup(app)
    cli()
