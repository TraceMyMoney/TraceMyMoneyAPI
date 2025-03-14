# Library imports
import time
from flask.cli import FlaskGroup

# Direct Imports
from src.main import create_app
from src.extensions import scheduler
import src.scheduler_jobs as scheduler_jobs

# Creating the app
flask_app = create_app()


@flask_app.cli.command("scheduler")
def execute_scheduler():
    scheduler.init_app(flask_app)
    scheduler.start()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    cli = FlaskGroup(create_app)
    cli()
