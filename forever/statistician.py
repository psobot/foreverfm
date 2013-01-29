import time
import config
from cube import emit


def generate(get_listeners, get_stats, **queues):
    while True:
        time.sleep(config.monitor_update_time)
        listeners = get_listeners()
        emit("listeners", {"count": len(listeners)})
        yield {"listeners": [dict(dict(g.request.headers).items() + [("remote_ip", g.request.remote_ip)])
                            for g in listeners],
               "queues": dict([(n, q.buffered) for n, q in queues.iteritems()]),
               "info": get_stats()}
