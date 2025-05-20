# Library imports
import time
from flask.cli import FlaskGroup

# Direct Imports
from src.main import create_app
from src.extensions import scheduler
import src.scheduler_jobs as scheduler_jobs

# Creating the app
app, celery = create_app()

if __name__ == "__main__":
    cli = FlaskGroup(create_app)
    cli()
