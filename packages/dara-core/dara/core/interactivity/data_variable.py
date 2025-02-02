"""
Copyright 2023 Impulse Innovations Limited


Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

from typing import Optional, Union

from anyio.abc import TaskGroup
from pandas import DataFrame
from pydantic import BaseModel

from dara.core.base_definitions import CacheType
from dara.core.interactivity.any_data_variable import (
    AnyDataVariable,
    DataVariableRegistryEntry,
)
from dara.core.interactivity.filtering import (
    FilterQuery,
    Pagination,
    apply_filters,
    coerce_to_filter_query,
)
from dara.core.internal.hashing import hash_object
from dara.core.internal.pandas_utils import append_index
from dara.core.internal.store import Store
from dara.core.internal.websocket import WebsocketManager
from dara.core.logging import eng_logger


class DataVariable(AnyDataVariable):
    """
    DataVariable represents a variable that is specifically designed to hold datasets.


    Example use cases:

    Global data provided upfront
    >>> global_data = DataVariable(data=DataFrame({'a': [1, 2, 3]})) # implicit cache='global'

    User-specific data, cannot be provided upfront (top-level code does not have a user context)
    >>> user_data = DataVariable(cache='user')
    >>> UploadDropzone(target=user_data)

    Session-specific data, cannot be provided upfront (top-level code does not have a session context)
    >>> session_data = DataVariable(cache='session')
    >>> UpdateVariable(func=some_data_transformation, variable=session_data)
    """

    uid: str
    filters: Optional[FilterQuery] = None
    cache: Optional[CacheType] = None

    class Config:
        extra = 'forbid'
        arbitrary_types_allowed = True
        use_enum_values = True

    def __init__(
        self, data: Optional[DataFrame] = None, cache: CacheType = CacheType.GLOBAL, uid: Optional[str] = None, **kwargs
    ) -> None:
        """
        DataVariable represents a variable that is specifically designed to hold datasets.

        :param data: optional dataframe
        :param uid: the unique identifier for this variable; if not provided a random one is generated
        :param filters: a dictionary of filters to apply to the data
        :param cache: how to cache the result; 'user' per user, 'session' per session, 'global' for all users
        """
        if data is not None and cache is not CacheType.GLOBAL:
            raise ValueError('Data cannot be cached per session or per user if provided upfront')

        super().__init__(cache=cache, uid=uid, **kwargs)

        # Register the variable with the dataset
        from dara.core.internal.registries import data_variable_registry

        var_entry = DataVariableRegistryEntry(cache=cache, uid=str(self.uid), type='plain')
        data_variable_registry.register(
            str(self.uid),
            var_entry,
        )

        # Put the data entry into the store if not empty (so cache='global')
        # We don't create an entry in a different case since session key will be global anyway at this point
        if data is not None:
            from dara.core.internal.registries import utils_registry

            store: Store = utils_registry.get('Store')
            self._update(var_entry, store, data)

    @staticmethod
    def _get_cache_key(uid: str) -> str:
        """
        Get a unique cache key for the data variable.

        :param uid: uid of the DataVariable
        """
        return f'data-{uid}'

    @classmethod
    def _get_count_cache_key(cls, uid: str, filters: Optional[Union[FilterQuery, dict]]) -> str:
        return f'{cls._get_cache_key(uid)}_{hash_object(filters)}'

    @classmethod
    def _update(cls, var_entry: DataVariableRegistryEntry, store: Store, data: Optional[DataFrame]):
        """
        Internal helper which updates the data variable entry in store.

        TODO: for now data is always kept in store, in the future depending on the size data might be cached on disk
        """
        store.set(
            cls._get_cache_key(str(var_entry.uid)), DataStoreEntry(data=append_index(data)), cache_type=var_entry.cache
        )

    @classmethod
    def update_value(cls, var_entry: DataVariableRegistryEntry, store: Store, data: Optional[DataFrame]):
        """
        Update the data entry and notify all clients about the update.

        :param var_entry: the entry in the registry
        :param data: the data to update
        :param store: store instance
        """
        cls._update(var_entry, store, data)

        # Broadcast the update to all clients
        from dara.core.internal.registries import utils_registry

        ws_mgr: WebsocketManager = utils_registry.get('WebsocketManager')
        task_group: TaskGroup = utils_registry.get('TaskGroup')
        task_group.start_soon(
            ws_mgr.broadcast,
            {
                'data_id': str(var_entry.uid),
            },
        )

    @classmethod
    def get_value(
        cls,
        var_entry: DataVariableRegistryEntry,
        store: Store,
        filters: Optional[Union[FilterQuery, dict]] = None,
        pagination: Optional[Pagination] = None,
    ) -> Optional[DataFrame]:
        """
        Get the value of this DataVariable.
        """
        _uid_short = f'{var_entry.uid[:3]}..{var_entry.uid[-3:]}'
        eng_logger.info(
            f'Data Variable {_uid_short} get_value',
            {'uid': var_entry.uid, 'filters': filters, 'pagination': pagination},
        )

        cache_key = cls._get_cache_key(var_entry.uid)
        entry = store.get(cache_key, cache_type=var_entry.cache)

        eng_logger.debug(
            f'Data Variable {_uid_short}',
            'retrieved from cache',
            {'uid': var_entry.uid, 'size': len(entry.data.index) if entry is not None else 0},
        )

        if entry is None:
            store.set(cls._get_count_cache_key(var_entry.uid, filters), 0, cache_type=var_entry.cache)
            return None

        data = None

        if entry.data is not None:
            filtered_data, count = apply_filters(entry.data, coerce_to_filter_query(filters), pagination)
            data = filtered_data
            # Store count for given filters
            store.set(cls._get_count_cache_key(var_entry.uid, filters), count, cache_type=var_entry.cache)
        else:
            store.set(cls._get_count_cache_key(var_entry.uid, filters), 0, cache_type=var_entry.cache)

        # TODO: once path is supported, stream&filter from disk
        if entry.path:
            raise NotImplementedError('DataVariable.get_value() does not support disk caching yet')

        eng_logger.info(
            f'Data Variable {_uid_short} returning filtered data',
            {'uid': var_entry.uid, 'size': len(data.index) if data is not None else 0},
        )

        return data

    @classmethod
    def get_total_count(cls, var_entry: DataVariableRegistryEntry, store: Store, filters: Optional[FilterQuery]):
        """
        Get total count of the data variable.

        :param var_entry: variable entry
        :param store: store
        :param filters: filters to get count for
        """
        cache_key = cls._get_count_cache_key(var_entry.uid, filters)
        entry = store.get(cache_key, cache_type=var_entry.cache)

        if entry is None:
            raise ValueError('Requested count for filter setup which has not been performed yet')

        return entry

    def dict(self, *args, **kwargs):
        parent_dict = super().dict(*args, **kwargs)
        if 'data' in parent_dict:
            parent_dict.pop('data')   # make sure data is not included in the serialised dict
        return {**parent_dict, '__typename': 'DataVariable', 'uid': str(parent_dict['uid'])}


class DataStoreEntry(BaseModel):
    """
    Entry in the cache store for a DataVariable.
    Can either be a DataFrame or a path to a file on disk.
    """

    data: Optional[DataFrame] = None
    path: Optional[str] = None

    class Config:
        extra = 'forbid'
        arbitrary_types_allowed = True
