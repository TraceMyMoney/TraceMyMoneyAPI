# import libraries
from os import environ
from config import config as app_config
from flask.config import Config
from mongoengine import connect

config = Config('')
env = environ.get('KOKO_PROMO_ENV', 'local').lower()

if env == 'test':
    config.from_object(app_config['test'])
elif env == 'production':
    config.from_object(app_config['production'])
else:
    config.from_object(app_config['development'])

def connect_mongo():
    mongo_engine = connect(config['MONGO_DATABASE'],
                       host=config['MONGO_DATABASE_URI'])
