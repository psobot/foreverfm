import time
import config


def generate(get_listeners, **queues):
    while True:
        time.sleep(config.monitor_update_time)
        yield {"listeners": [dict(dict(g.request.headers).items() + [("remote_ip", g.request.remote_ip)])
                            for g in get_listeners()],
               "queues": dict([(n, q.buffered) for n, q in queues.iteritems()])}
