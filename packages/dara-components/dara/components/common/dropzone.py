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

from typing import Callable, Optional, Union
from uuid import uuid4

from pandas import DataFrame

from dara.core.base_definitions import Action
from dara.core.definitions import StyledComponentInstance
from dara.core.interactivity import DataVariable

DropzoneResolver = Union[
    Callable[[bytes, str], DataFrame],
    Callable[[bytes, str], None],
]


class UploadDropzone(StyledComponentInstance):
    """
    A component that exposes a dropzone for uploading files. Takes a DataVariable instance
    that will store the dataset uploaded and an on_drop action that is triggered when
    a file is successfully uploaded after being dropped or pasted.
    """

    js_module = '@darajs/components'

    accept: Optional[str] = None
    target: Optional[DataVariable] = None
    resolver: Optional[DropzoneResolver]
    on_drop: Optional[Action] = None

    class Config:
        extra = 'allow'

    def __init__(
        self,
        target: Optional[DataVariable] = None,
        resolver: Optional[DropzoneResolver] = None,
        on_drop: Optional[Action] = None,
        accept: Optional[str] = None,
        **kwargs
    ):
        """
        A component that exposes a dropzone for uploading files. Takes a DataVariable instance
        that will store the dataset uploaded and an on_drop action that is triggered when
        a file is successfully uploaded after being dropped or pasted.

        :param accept: optional comma-separated list of MIME-types or filename extensions accepted by the frontend; see https://developer.mozilla.org/en-US/docs/Web/HTML/Element/input/file#unique_file_type_specifiers for detail.
            When not specified, defaults to accepting csv/xlsx; more specifically: `.csv, text/csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel, application/csv, text/x-csv, application/x-csv, text/comma-separated-values, text/x-comma-separated-values`
        :param target: data variable storing the data
        :param resolver: optional resolver accepting `bytes` and filename as a string
            - if a target is specified, can be used to customise how the `bytes` received are turned into a `DataFrame`
            - if a target is not specified, can be treated as a side effect function to run on the `bytes` received (to i.e. store on disk)
        :param on_drop: optional action triggered when a file is successfully uploaded
        """
        from dara.core.internal.registries import upload_resolver_registry

        # Register the resolver function if provided
        uid = None
        if resolver is not None:
            uid = str(uuid4())
            upload_resolver_registry.register(uid, resolver)

        super().__init__(target=target, on_drop=on_drop, accept=accept, **kwargs)

        self.resolver_id = uid
