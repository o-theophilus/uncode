from flask import Flask
from flask_cors import CORS

from . import api
from . import post
from . import post_get
from . import comment
from . import post_rating
from . import photo
from . import tag
from . import user
from . import auth
from . import admin
from . import auth_password_forgot
from . import report


def create_app(conf=None):
    app = Flask(__name__)
    app.config.from_prefixed_env()
    if conf:
        app.config.from_pyfile(conf)
    CORS(app)

    app.register_blueprint(api.bp)
    app.register_blueprint(post.bp)
    app.register_blueprint(post_get.bp)
    app.register_blueprint(comment.bp)
    app.register_blueprint(post_rating.bp)
    app.register_blueprint(photo.bp)
    app.register_blueprint(user.bp)
    app.register_blueprint(tag.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(auth_password_forgot.bp)
    app.register_blueprint(report.bp)

    return app
