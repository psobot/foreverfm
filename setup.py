#!/usr/bin/env python

__author__ = "psobot"

from setuptools import setup
import os
import subprocess

SUCCESSFUL = 0


class DependencyError(Exception):
    pass


class InstallError(Exception):
    pass

platform = os.uname()[0] if hasattr(os, 'uname') else 'Windows'


def has(package):
    return subprocess.call(["which", package], ) == SUCCESSFUL


def apt_get_install(packages):
    return install_with_package_manager('apt-get', packages)


def brew_install(packages):
    return install_with_package_manager('brew', packages)


def install_with_package_manager(manager, packages):
    if not has(manager):
        raise DependencyError(manager + " is not installed.")
    if not isinstance(packages, list):
        packages = [packages]
    return_code = subprocess.call([manager, "install"] + packages)
    if return_code is not SUCCESSFUL:
        raise InstallError(return_code)
    else:
        return return_code


def ensure_installed(packages):
    if not isinstance(packages, list):
        packages = [packages]
    for package in packages:
        if not has(package):
            if platform == "Linux":
                apt_get_install(package)
            elif platform == "Darwin":
                brew_install(package)


def get_enremix():
    #   If we're on linux, we need to get our own ffmpeg, build tools, and git-core
    if platform == "Linux":
        ensure_installed(['ffmpeg', 'build-essential', 'git-core'])
    elif platform == "Darwin" and not has("gcc"):
        raise DependencyError("Need Xcode installed to build.")


def get_nodejs():
    ensure_installed('node')


def get_pil_dependencies():
    #   We need to have zlib (for PNG) and libjpeg installed
    pass

get_enremix()
get_pil_dependencies()
get_nodejs()

setup(name='Forever.FM',
    version='1.0',
    description='Infinite Radio Station',
    author='Peter Sobot',
    author_email='forever@petersobot.com',
    url='http://forever.fm/',
    packages=['forever'],
    ext_modules=[],
    dependency_links = [
        'https://github.com/echonest/pyechonest/tarball/master#egg=pyechonest'
    ],
    install_requires=[
        'PyYAML',
        'tornado',
        'tornadio2',
        'sqlalchemy',
        "MySQL_python",
        'numpy',
        'pyechonest',
        'PIL',
        'soundcloud',
        'requests',
    ]
)
