import time
import math
import json
import urllib.request
import urllib.parse
from collections import deque

import gevent
from viewserver.objects import RelaySrv
from viewserver.funcs import pretty_bytes

# global singletons for our data
relay_servers = dict()
relay_state = dict()

def fetch(url):
    with urllib.request.urlopen(url) as resp:
        content = resp.read()
        try:
            content = json.loads(content.decode('utf-8'))
        except Exception as e:
            raise e
        else:
            return content


def get_relay_stats(app):
    if not relay_servers:
        return

    jobs = list()
    relay_poll_int = app.config.get('RELAY_POLL_INT')

    for key, obj in relay_servers.items():
        jobs.append(gevent.spawn(single_server, obj, app.config.get('STATUS_URL')))

    gevent.joinall(jobs, timeout=5)

    for job in jobs:
        val = job.value

        if val is not None:
            one_hour = math.ceil(3600 / relay_poll_int)
            results = relay_state.setdefault(val['host'], deque(maxlen=one_hour))
            results.append(val)


def get_relay_list(app):
    data = fetch(app.config.get('SYNC_ENDPOINT'))

    sync_attr_url = app.config.get('SYNC_ATTR_URL')
    sync_attr = app.config.get('SYNC_ATTR')

    if not data:
        raise ValueError('Could not obtain relay server data.')

    relay_list = data.get(sync_attr)
    relay_list = map(lambda x: x.get(sync_attr_url, None), relay_list)
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
        relay_servers.setdefault(server.hostname, relaysrv)

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
        'global_rate': pretty_bytes(raw_options['global_rate']) + 'ps',
        'session_rate': pretty_bytes(raw_options['session_rate']) + 'ps'
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
        pretty_speed[key] = pretty_bytes(val * 1000) + 'ps'

    ret = {
        'host': obj.host,
        'obtained': int(time.time()),
        'meta': {
            'arch': {
                'go': contents.get('goAarch', None),
                'go_version': contents.get('goVersion', None),
                'go_max_procs': contents.get('goMaxProcs', -1),
                'os': contents.get('goOS')
            },
            'bytes_proxied': {
                'raw': contents.get('bytesProxied', -1),
                'pretty': pretty_bytes(contents.get('bytesProxied', -1))
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


def single_server(obj, root_url):
    try:
        url = root_url.format(obj.host, obj.qs['statusAddr'])
        contents = fetch(url)
    except urllib.error.URLError as e:
        pass
    else:
        return parse_contents(obj, contents)
