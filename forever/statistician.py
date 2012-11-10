import time

poll = 1


def generate(get_listeners, **queues):
    while True:
        time.sleep(poll)
        yield {"listeners": [dict(dict(g.request.headers).items() + [("remote_ip", g.request.remote_ip)])
                            for g in get_listeners()],
               "queues": dict([(n, q.buffered) for n, q in queues.iteritems()])}
