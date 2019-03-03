import os
import dateutil
from jsonfield import JSONField
from flask import Flask, request, g, url_for
from flask_login import LoginManager, current_user
from flask_restful import Api

from peewee import SqliteDatabase
from peewee import MySQLDatabase

from app import filters
from app.utils import common_context, url_for as common_url_for

from social_flask.utils import load_strategy
from social_flask.routes import social_auth
from social_flask.template_filters import backends
from social_flask_peewee.models import init_social

from werkzeug.contrib.fixers import ProxyFix

from .models.base_model import database_proxy
from .models.user import User


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# App
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'app', 'templates')
)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.config.from_object('app.settings')

try:
    app.config.from_object('app.local_settings')
except ImportError:
    pass

# API
api = Api(app)

# DB
database = None
if settings.USE_SQLITE_DATABASE == 'true':
    database = SqliteDatabase(app.config['SQLITE_DATABASE_URI'])
else:
    database = MySQLDatabase(
        app.config['MYSQL_DATABASE'],
        user = app.config['MYSQL_USERNAME'],
        password = app.config['MYSQL_PASSWORD'],
        host = app.config['MYSQL_HOSTNAME']
    )
database_proxy.initialize(database)

app.register_blueprint(social_auth)
init_social(app, database)

login_manager = LoginManager()
login_manager.login_view = 'main'
login_manager.login_message = ''
login_manager.init_app(app)

from app import models
from app import routes


@login_manager.user_loader
def load_user(userid):
    try:
        return User.get(User.id == userid)
    except User.DoesNotExist:
        pass


@login_manager.unauthorized_handler
def unauthorized():
    return { 'error': 'UNAUTHORIZED' }, 401


@app.before_request
def before_request_handler():
    if database.is_closed():
        database.connect()
        if type(database) is MySQLDatabase:
            database.execute_sql('SET @@auto_increment_increment=1;')
    # evaluate proxy value
    g.user = current_user._get_current_object()


@app.after_request
def after_request_handler(response):
    for func in getattr(g, 'call_after_request', ()):
        response = func(response)
    if not database.is_closed():   
        database.close()
    # write is_authenticated cookie
    is_authenticated = str(current_user.is_authenticated).lower()
    if request.cookies.get('is_authenticated') != is_authenticated:
        response.set_cookie('is_authenticated', is_authenticated)
    return response


@app.context_processor
def inject_user():
    try:
        return {'user': g.user}
    except AttributeError:
        return {'user': None}


@app.context_processor
def load_common_context():
    return common_context(
        app.config['SOCIAL_AUTH_AUTHENTICATION_BACKENDS'],
        load_strategy(),
        getattr(g, 'user', None),
        app.config.get('SOCIAL_AUTH_GOOGLE_PLUS_KEY')
    )

app.context_processor(backends)
app.jinja_env.filters['backend_name'] = filters.backend_name
app.jinja_env.filters['backend_class'] = filters.backend_class
app.jinja_env.filters['icon_name'] = filters.icon_name
app.jinja_env.filters['social_backends'] = filters.social_backends
app.jinja_env.filters['legacy_backends'] = filters.legacy_backends
app.jinja_env.filters['oauth_backends'] = filters.oauth_backends
app.jinja_env.filters['filter_backends'] = filters.filter_backends
app.jinja_env.filters['slice_by'] = filters.slice_by
app.jinja_env.globals['url'] = common_url_for
