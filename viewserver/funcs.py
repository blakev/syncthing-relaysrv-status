import math

import gevent

from viewserver.constants import TIME_REG

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
    pre = 'kmgtpe'[int(exp-1)]
    return '%.1f %sb' % (val / math.pow(unit, exp), pre)


def schedule(delay, fnc, *args, **kwargs):
    gevent.spawn_later(0, fnc, *args, **kwargs)
    gevent.spawn_later(delay, schedule, delay, fnc, *args, **kwargs)
