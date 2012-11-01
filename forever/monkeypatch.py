__author__ = 'psobot'

def monkeypatch_class(name, bases, namespace):
    assert len(bases) == 1, "Exactly one base class required"
    base = bases[0]
    for name, value in namespace.iteritems():
        if name != "__metaclass__" and name != "__doc__":
            setattr(base, name, value)
    return base