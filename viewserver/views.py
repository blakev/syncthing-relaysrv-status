from functools import partial, reduce

from flask import Blueprint, jsonify, render_template
from cachetools import cached, hashkey

from viewserver.funcs import pretty_bytes
from viewserver.ext.caching import TTL_CACHE
from viewserver.ext.periodic import relay_state

blu = Blueprint('core', __name__)



@cached(TTL_CACHE, key=partial(hashkey, 'status'))
def get_frame_data(frames):
    results = {}
    frames = max(1, frames)

    for key, val in relay_state.items():
        # only get the most recent status
        # from the collected states
        if frames == 1:
            results[key] = val[-1]
        else:
            results[key] = list(val)[(-1 * frames):]
    return results

@blu.route('/')
@cached(TTL_CACHE, key=partial(hashkey, 'index'))
def index():
    data = get_frame_data(1)

    mapped = list(map(lambda x: (x['meta']['uptime'], x['host'], x['meta']['provided_by']), data.values()))

    newest, oldest = {}, {}

    if mapped:
        newest['uptime'], newest['ip'], newest['owner'] = min(mapped)
        oldest['uptime'], oldest['ip'], oldest['owner'] = max(mapped)

    total_bytes = sum(map(lambda x: x['meta']['bytes_proxied']['raw'], data.values())) or 0
    total_bytes = pretty_bytes(total_bytes).upper()

    return render_template('index.html',
                           top_data=data,
                           newest=newest,
                           oldest=oldest,
                           total_bytes=total_bytes)

@blu.route('/status/')
@blu.route('/status/<int:frames>')
def status(frames=1):
    results = get_frame_data(frames)
    return jsonify(results)
