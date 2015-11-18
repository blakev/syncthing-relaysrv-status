__author__ = 'Blake VandeMerwe <blakev@null.net>'
__version__ = '0.1'

import re
import sys
import urllib
import json
import math
import time
from collections import namedtuple, deque
from functools import partial

import gevent
from flask import Flask, jsonify
from flask.ext.compress import Compress
from gevent.wsgi import WSGIServer
from gevent import monkey
from cachetools import cached, TTLCache, hashkey

monkey.patch_all()

# Ghetto Namespacing
class Config(object):
	HOST = 'localhost'
	PORT = 5000

	# syncthing-relaysrv specific attributes
	SYNC_ENDPOINT = r'https://relays.syncthing.net/endpoint'
	SYNC_ATTR = 'relays'
	SYNC_ATTR_URL = 'url'
	SYNC_POLL_INT = 60
	RELAY_POLL_INT = 20
	STATUS_URL = 'http://{}{}/status'


class G(object):
	relay_servers = dict()
	relay_state = dict()

# Globalsss
TIME_REG = re.compile(r'(?P<hour>\d+[hH])?(?P<minute>\d+[mM])?(?P<second>\d+[sS])?')
TTL_CACHE = TTLCache(maxsize=256, ttl=math.floor(Config.RELAY_POLL_INT * 0.85))

class fn:
	def parse_timestr(t):
	    if isinstance(t, (int, float)):
	        t = str(int(t)) + 's'

	    x = TIME_REG.match(t).groups()

	    if not any(x): 
	    	return 0

	    hours, minutes, seconds = x
	    hours = int(hours.strip('hH')) if hours else 0
	    minutes = int(minutes.strip('mM')) if minutes else 0
	    seconds = int(seconds.strip('sS')) if seconds else 0
	    # return the result in seconds
	    return (hours * 60 * 60) + (minutes * 60) + seconds


	def pretty_bytes(val, unit=1024):
	    val = int(val)
	    if val < unit:
	        return str(val) + ' B'
	    exp = int(math.log(val) / math.log(unit))
	    pre = 'kMGTPE'[int(exp-1)]
	    return '%.1f %sB' % (val / math.pow(unit, exp), pre)


# Custom MicroObjects
RelaySrv = namedtuple('RelaySrv', 'host port qs')

# create the web application
app = Flask(__name__)
app.config.update({
	'COMPRESS_LEVEL': 8,
	'COMPRESS_MIN_SIZE': 64
})

Compress(app)

# ==============
def fetch(url):
	with urllib.request.urlopen(url) as resp:
		content = resp.read()
		try:
			content = json.loads(content.decode('utf-8'))
		except Exception as e:
			raise e
		else:
			return content


def schedule(delay, fnc, *args, **kwargs):
	gevent.spawn_later(0, fnc, *args, **kwargs)
	gevent.spawn_later(delay, schedule, delay, fnc, *args, **kwargs)


def parse_contents(obj, contents):
	o = contents.get('options', {}).get

	raw_options = {
		'global_rate': int(o('global-rate', -1)),
		'session_rate': int(o('per-session-rate', -1)),
		'message_timeout': int(o('message-timeout', -1)),
		'network_timeout': int(o('network-timeout', -1)),
		'ping_interval': int(o('ping-interval', -1))
	}

	pretty_options = dict(raw_options)
	pretty_options.update({
		'global_rate': fn.pretty_bytes(raw_options['global_rate']).upper() + 'ps',
		'session_rate': fn.pretty_bytes(raw_options['session_rate']).upper() + 'ps'
	})

	raw_speed = contents.get('kbps10s1m5m15m30m60m', range(6))

	raw_speed = {
		'array': raw_speed,
		'last_10s': raw_speed[0],
		'last_1m': raw_speed[1],
		'last_5m': raw_speed[2],
		'last_15m': raw_speed[3],
		'last_30m': raw_speed[4],
		'last_60m': raw_speed[5]
	}

	pretty_speed = dict(raw_speed)
	pretty_speed.pop('array')

	for key, val in pretty_speed.items():
		pretty_speed[key] = fn.pretty_bytes(val * 1000) + 'ps'

	ret = {
		'host': obj.host,
		'obtained': int(time.time()),
		'meta': {
			'arch': {
				'go': contents.get('goArch', None),
				'go_version': contents.get('goVersion', None),
				'go_max_procs': contents.get('goMaxProcs', -1),
				'os': contents.get('goOS')
			},
			'bytes_proxied': {
				'raw': contents.get('bytesProxied', -1),
				'pretty': fn.pretty_bytes(contents.get('bytesProxied', -1))
			},
			'uptime': contents.get('uptimeSeconds', -1),
			'pools': o('pools', []),
			'provided_by': o('provided-by', 'Unknown'),
			'relay_port': obj.port,
			'status_port': int(obj.qs.get('statusAddr', -1).strip(':'))
		},
		'session': {
			'active': int(contents.get('numActiveSessions', 0)),
			'connections': int(contents.get('numConnections', 0)),
			'pending': int(contents.get('numPendingSessionKeys', 0)),
			'proxies': int(contents.get('numProxies', 0)),
			'speed': {
				'raw_kbps': raw_speed,
				'pretty': pretty_speed
			}
		},
		'options': {
			'raw': raw_options,
			'pretty': pretty_options
		}
	}

	return ret


def single_server(obj):
	try:
		url = Config.STATUS_URL.format(obj.host, obj.qs['statusAddr'])
		contents = fetch(url)
	except urllib.error.URLError as e:
		pass
	else:
		return parse_contents(obj, contents)


def get_relay_stats():
	if not G.relay_servers:
		# skip
		return

	jobs = list()

	for key, obj in G.relay_servers.items():
		jobs.append(gevent.spawn(single_server, obj))

	gevent.joinall(jobs, timeout=5)

	for job in jobs:
		val = job.value

		if val is not None:
			one_hour = math.ceil(3600 / Config.RELAY_POLL_INT)
			results = G.relay_state.setdefault(val['host'], deque(maxlen=one_hour))
			results.append(val)


def get_relay_list():
	data = fetch(Config.SYNC_ENDPOINT)

	if not data:
		raise ValueError('Could not obtain relay server data.')
	
	relay_list = data.get(Config.SYNC_ATTR)
	relay_list = map(lambda x: x.get(Config.SYNC_ATTR_URL, None), relay_list)
	relay_list = filter(None, relay_list)

	for server_url in relay_list:
		# grab the hostname/ip and port, as well as protocol
		server = urllib.parse.urlparse(server_url)	
		# parse the query string to determine other 'relevent'
		# attributes that have been assigned to this relaysrv
		qs = urllib.parse.parse_qs(server.query)

		# convert the qs-parsed url into JSON where 
		# each value isn't a list of single values...
		for key, value in qs.items():
			if hasattr(value, '__iter__'):
				qs[key] = value[0]

		# keep a new RelaySrv instance that we can use to
		# track the progress of this node.
		relaysrv = RelaySrv(server.hostname, server.port, qs)

		# track that isshhh
		G.relay_servers.setdefault(server.hostname, relaysrv)	

@app.after_request
def middleware_gzip(resp):
	# passthrough
	return resp

@app.route('/')
@cached(TTL_CACHE, key=partial(hashkey, 'index'))
def index():
	return 'syncthing-relasrv status server'

@app.route('/status/')
@app.route('/status/<int:frames>')
@cached(TTL_CACHE, key=partial(hashkey, 'status'))
def status(frames=1):
	status = {}
	frames = max(1, frames)

	for key, val in G.relay_state.items():
		# only get the most recent status
		# from the collected states	
		if frames == 1:
			status[key] = val[-1]
		else:
			status[key] = list(val)[(-1 * frames):]

	return jsonify(status)

# syncthing-relaysrv view-status server
# .. main
if __name__ == '__main__':
	schedule(Config.SYNC_POLL_INT, get_relay_list)
	schedule(Config.RELAY_POLL_INT, get_relay_stats)

	host, port = Config.HOST, Config.PORT

	try:
		# start the server
		print('Serving on http://{}:{}'.format(host, port))
		http_server = WSGIServer((host, port,), app)
		http_server.serve_forever()
	except KeyboardInterrupt as e:
		# cleanup on SIGINT
		print('Closing webserver..')

	except Exception as e:
		print('Error: ', e.message)
		raise e

	sys.exit(0)