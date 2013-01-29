import time
import config
from cube import emit


def generate(get_relays, get_stats, **queues):
    while True:
        time.sleep(config.monitor_update_time)
        relays = get_relays()
        emit("relays", {"count": len(relays)})
        yield {"listeners": [dict(dict(g.request.headers).items() + [("remote_ip", g.request.remote_ip)])
                            for g in relays],
               "queues": dict([(n, q.buffered) for n, q in queues.iteritems()]),
               "info": get_stats()}
