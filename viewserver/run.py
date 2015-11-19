__author__ = 'Blake VandeMerwe <blakev@null.net>'
__version__ = '0.1'

import sys

from gevent.wsgi import WSGIServer
from gevent import monkey

monkey.patch_all()

# syncthing-relaysrv view-status server
# .. main
if __name__ == '__main__':
    from viewserver import create_app

    # create a new flask application
    app = create_app(debug=True)

    host = app.config.get('HOST', 'localhost')
    port = app.config.get('PORT', 5000)

    try:
        # start the server
        print('Serving on http://{}:{}'.format(host, port))
        http_server = WSGIServer((host, port,), app)
        http_server.serve_forever()

    except KeyboardInterrupt as e:
        # cleanup on SIGINT
        print('Closing webserver..')

    except Exception as e:
        raise e

    sys.exit(0)