from flask import Flask
from flask_compress import Compress

from viewserver.funcs import schedule
from viewserver.ext.periodic import get_relay_list, get_relay_stats
from viewserver.ext.caching import configure as configure_caching
from viewserver.views import blu

def create_app(**settings):
    app = Flask(__name__)

    # create the app configuration from the default settings file
    # .. `settings/default.py`
    app.config.from_object('viewserver.settings.default')

    # update app configuration with kwargs `settings`
    app.config.update(settings)

    # add compression to our flask app
    # Compress(app)

    # enable caching
    configure_caching(app)

    # schedule our periodic tasks
    schedule(app.config.get('SYNC_POLL_INT'), get_relay_list, app)
    schedule(app.config.get('RELAY_POLL_INT'), get_relay_stats, app)

    @app.add_template_filter
    def time_str(seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return "%dh %02dm %02ds" % (h, m, s)

    app.register_blueprint(blu)

    return app