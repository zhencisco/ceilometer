# -*- encoding: utf-8 -*-
#
# Author: John Tran <jhtran@att.com>
#         Julien Danjou <julien@danjou.info>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import distutils.version as dist_version
import os

import migrate
from migrate.versioning import util as migrate_util
import sqlalchemy

from ceilometer.openstack.common import log


INIT_VERSION = 1
LOG = log.getLogger(__name__)


@migrate_util.decorator
def patched_with_engine(f, *a, **kw):
    url = a[0]
    engine = migrate_util.construct_engine(url, **kw)

    try:
        kw['engine'] = engine
        return f(*a, **kw)
    finally:
        if isinstance(engine, migrate_util.Engine) and engine is not url:
            migrate_util.log.debug('Disposing SQLAlchemy engine %s', engine)
            engine.dispose()


# TODO(jkoelker) When migrate 0.7.3 is released and nova depends
#                on that version or higher, this can be removed
MIN_PKG_VERSION = dist_version.StrictVersion('0.7.3')
if (not hasattr(migrate, '__version__')
        or dist_version.StrictVersion(migrate.__version__) < MIN_PKG_VERSION):
    migrate_util.with_engine = patched_with_engine


# NOTE(jkoelker) Delay importing migrate until we are patched
from migrate import exceptions as versioning_exceptions
from migrate.versioning import api as versioning_api
from migrate.versioning.repository import Repository

_REPOSITORY = None


def db_sync(engine, version=None):
    if version is not None:
        try:
            version = int(version)
        except ValueError:
            raise Exception(_("version should be an integer"))

    current_version = db_version(engine)
    repository = _find_migrate_repo()
    if version is None or version > current_version:
        return versioning_api.upgrade(engine, repository, version)
    else:
        return versioning_api.downgrade(engine, repository,
                                        version)


def db_version(engine):
    repository = _find_migrate_repo()
    try:
        return versioning_api.db_version(engine,
                                         repository)
    except versioning_exceptions.DatabaseNotControlledError:
        meta = sqlalchemy.MetaData()
        meta.reflect(bind=engine)
        tables = meta.tables
        if len(tables) == 0:
            db_version_control(engine, 0)
            return versioning_api.db_version(engine, repository)


def db_version_control(engine, version=None):
    repository = _find_migrate_repo()
    versioning_api.version_control(engine, repository, version)
    return version


def _find_migrate_repo():
    """Get the path for the migrate repository."""
    global _REPOSITORY
    path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                        'migrate_repo')
    assert os.path.exists(path)
    if _REPOSITORY is None:
        _REPOSITORY = Repository(path)
    return _REPOSITORY
