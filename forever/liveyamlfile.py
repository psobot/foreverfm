"""
liveyamlfile.py
Live Pythonic attribute access to properties in a yaml file.
by Peter Sobot (hi@psobot.com), August 8, 2012
"""

import os
import time
import yaml
import logging


class LiveYamlFile(object):
    """
    Magical class that allows for real-time access of variables in a yaml
    file via Pythonic attribute-like access.

    Any functions, objects or properties on the class (or its subclasses)
    will not be looked up in the yaml file. Every access may result in at
    worst, a YAML load and at best, an os.stat call at most every __timeout
    seconds.

    Simple example usage:
        > my_object = yaml_file("file.yml")
        > my_object.some_changing_property
        5
        > # (now here, file.yml has changed outside of python)
        > my_object.some_changing_property
        6
        > my_object.blah     # blah is not defined in the yaml file
        AttributeError: object my_object has no attribute 'blah'
    """

    __last_updated = 0
    __timeout = 5  # seconds
    __exclude = []
    __overwrite = False

    def __init__(self, filename, overwrite=False):
        self.__file = filename
        self.__overwrite = overwrite

        #   Any subclass's properties will be ignored here
        supers = LiveYamlFile.__dict__
        subs = self.__class__.__dict__
        self.__exclude = [k for k, _ in
                        dict(supers.items() + subs.items()).iteritems()
                        if not k.startswith("_")]

    def __repr__(self):
        #   Note:  order is important here. Class variables get overriden
        #          by instance vars, so we have to add the dicts in that order.
        return dict.__repr__(dict((key, val) for key, val in
                             dict(self.__class__.__dict__.items() +
                                  self.__dict__.items()).iteritems()
                             if not key.startswith("_")))

    def __update(self):
        """
        Update the object's attributes from the YAML file.
        """
        if self.__file:
            target_file = open(self.__file)
            for attr in dir(self):
                if not attr.startswith("_") and \
                    (self.__overwrite or (attr not in self.__exclude)) \
                    and not self.__is_attr_callable(attr):
                        try:
                            delattr(self, attr)
                        except AttributeError:
                            pass
            pool = yaml.load(target_file)
            target_file.close()
            if pool:  # could be None
                for key, val in pool.iteritems():
                    if not key.startswith("_") and \
                        (self.__overwrite or (key not in self.__exclude)) \
                        and not self.__is_attr_callable(key):
                        setattr(self, key, val)
            if hasattr(self, 'log_config_file_changes')\
                    and self.log_config_file_changes:
                logging.getLogger(__name__).info("Config file has updated.")

    def __getattribute__(self, name):
        """
        When trying to access an attribute, check if the underlying file
        has changed first. Best case: reads from Python cache. Worst case:
        performs an os.stat and a YAML load every __timeout seconds.
        """
        if not name.startswith("_") and self.__file \
                and name not in self.__exclude:
            last_updated = self.__last_updated

            #   Only check once every __timeout seconds
            if (time.time() - last_updated) > self.__timeout:
                fmod_time = os.stat(self.__file)[9]
                if last_updated < fmod_time:
                    self.__last_updated = fmod_time
                    self.__update()
        return object.__getattribute__(self, name)

    def __is_attr_callable(self, attr):
        try:
            return hasattr(object.__getattribute__(self, attr), "__call__")
        except AttributeError:
            return None

    __sentinel = object()

    def get(self, key, default=__sentinel):
        try:
            return self.__getattribute__(key)
        except AttributeError:
            if default is not self.__sentinel:
                return default
            else:
                raise
