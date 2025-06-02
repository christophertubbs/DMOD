import pathlib
import os
import re
import inspect
import logging

import polars

import typing_extensions as typing

from dmod.core import common

from .. import specification
from .. import retrieval

from .. import reader
from .. import util

ParamSpec = typing.ParamSpec('ParamSpec')
"""A type hint for variable parameters"""

DataFrameCreator = typing.Callable[
    typing.Concatenate[typing.Union[typing.AnyStr, bytes, pathlib.Path, typing.IO], ParamSpec],
    polars.DataFrame
]
"""A function that may be used to construct a dataframe based on a path or raw input data"""


def get_datasource(datasource_definition: specification.DataSourceSpecification) -> retrieval.Retriever:
    """
    Get a retriever based off of the format variable in the backend field of the datasource definition

    Args:
        datasource_definition: The definition of a datasource from a project configuration

    Returns:
        A retriever based off of the format variable in the backend field of the datasource definition
    """
    return __FORMAT_MAPPING[datasource_definition.backend.format](datasource_definition)


class JSONDataRetriever(retrieval.Retriever):
    """
    Parses input data from a json document
    """
    @classmethod
    def get_purpose(cls) -> str:
        """
        Returns:
            What type of data this retriever is supposed to get
        """
        return "input_data"

    @property
    def definition(self) -> specification.DataSourceSpecification:
        """
        The data source that spurred the creation of this retriever
        """
        return self._definition

    @classmethod
    def get_format(cls) -> str:
        """
        The data format that this retriever consumes
        """
        return "json"

    def retrieve(self, **kwargs) -> polars.DataFrame:
        """
        Load the data described within the data source definition

        Returns:

        """
        if kwargs:
            raise ValueError(f"Unrecognized arguments: {kwargs}")

        documents = {
            str(source): util.data_to_dictionary(self.backend.read(source))
            for source in self.backend.sources
        }

        loaded_data: typing.Optional[polars.DataFrame] = None

        for document_name, document in documents.items():  # type: str, typing.Dict[str, typing.Any]
            frame = None
            for selector in self.definition.value_selectors:
                if selector.where == "constant":
                    continue

                selected_data = reader.select_values(document, selector)

                if frame is None:
                    frame = selected_data
                else:
                    common_columns = [
                        column_name
                        for column_name in frame.columns
                        if column_name in selected_data.columns
                    ]

                    frame = frame.join(selected_data, on=common_columns)

            constants = [
                selector
                for selector in self.definition.value_selectors
                if selector.where == 'constant'
            ]

            for constant in constants:
                value = constant.to_datatype(constant.path[0])
                frame.with_columns(**{constant.name: value})

            if self.definition.locations is not None and self.definition.locations.from_field == "filename":
                name = None

                if self.definition.locations.pattern:
                    full_pattern = os.pathsep.join(self.definition.locations.pattern)
                    search_results = re.search(full_pattern, document_name)
                    if search_results:
                        name = search_results.group()

                if not name:
                    name = os.path.splitext(os.path.basename(document_name))[0]

                frame = frame.with_columns(location=name)

            for mapping in self.definition.field_mapping:
                if mapping.map_type != "column":
                    continue

                if mapping.value in frame:
                    frame = frame.rename({mapping.value: mapping.field})

            if loaded_data is None:
                loaded_data = frame
            else:
                loaded_data = loaded_data.vstack(frame)

        return loaded_data


class FrameDataRetriever(retrieval.Retriever):
    """
    Retrieves tabular data from CSV files
    """
    @classmethod
    def get_purpose(cls) -> str:
        """
        Returns:
            What type of data this retriever is supposed to get
        """
        return "input_data"

    @property
    def definition(self) -> specification.DataSourceSpecification:
        return self._definition

    @classmethod
    def get_format(cls) -> str:
        return "csv"

    @classmethod
    def default_read_parameters(cls) -> typing.Dict[str, typing.Any]:
        return {
            "try_parse_dates": True
        }

    @classmethod
    def read_function(cls) -> DataFrameCreator:
        """
        The function used to interpret the stream read from the source
        """
        return polars.read_csv

    def retrieve(self, **kwargs) -> polars.DataFrame:
        constructor_signature = inspect.signature(self.read_function)
        provided_parameters = {
            key: value
            for key, value in self.backend.definition.properties.items()
            if key in constructor_signature.parameters
        }

        column_options = self.definition.get_column_options()

        for option, value in column_options.items():
            if option not in provided_parameters:
                provided_parameters[option] = value
            elif common.is_sequence_type(value) and common.is_sequence_type(provided_parameters[option]):
                for entry in value:
                    if entry not in provided_parameters[option]:
                        provided_parameters[option].append(entry)
            elif isinstance(value, dict) and isinstance(provided_parameters[option], dict):
                provided_parameters[option].update(value)
            else:
                provided_parameters[option] = value

        for key, default_value in self.default_read_parameters().items():
            provided_parameters.setdefault(key, default_value)

        provided_parameters.update({
            key: value
            for key, value in kwargs.items()
            if key in constructor_signature.parameters
        })

        combined_table = None

        for source in self.backend.sources:
            try:
                document = self.read_function()(self.backend.read_stream(source), **provided_parameters)
            except Exception as e:
                logging.error(f"Failed to read {source}", exc_info=e)
                raise

            column_names: typing.List[str] = []

            variable_selectors = [
                selector
                for selector in self.definition.value_selectors
                if selector.where.lower() != 'constant'
            ]

            for selector in variable_selectors:
                if selector.where.lower() != 'column':
                    raise ValueError(f"Column to be found in a '{selector.where}' is not valid for csv data.")

                if selector.name not in document.columns:
                    raise KeyError(f"There is not a column named '{selector.name}' in '{source}'")

                if selector.name not in column_names:
                    column_names.append(selector.name)

                for index in selector.associated_fields:
                    if index.name not in document.columns:
                        raise KeyError(f"There is not a column named '{index.name}' in '{source}'")

                    if index.name not in column_names:
                        column_names.append(index.name)

            table: polars.DataFrame = document[column_names]

            has_locations = self.definition.locations is not None
            should_identify_locations = has_locations and self.definition.locations.identify
            location_is_in_filename = should_identify_locations and self.definition.locations.from_field == 'filename'

            if location_is_in_filename:
                file_name_without_extension = os.path.splitext(os.path.basename(source))[0]
                pattern = self.definition.locations.pattern

                path_to_check = re.compile(os.path.join(*pattern) if common.is_sequence_type(pattern) else pattern)
                search_results = path_to_check.search(file_name_without_extension)

                name = search_results.group() if search_results else file_name_without_extension

                table = table.with_columns(location=name)

            if self.definition.unit.value:
                table = table.with_columns(unit=self.definition.unit.value)

            fields_to_rename: typing.Dict[str, str] = {}

            for mapping in self.definition.field_mapping:
                if mapping.map_type.lower() != 'column':
                    raise ValueError(
                            f"Values from the {mapping.value} field may not be mapped to '{mapping.field}' "
                            f"via a '{mapping.map_type}' for CSV data."
                    )

                if mapping.value not in table.columns:
                    raise KeyError(
                        f"There is not a column named '{mapping.value}' to rename in the retrieved table; "
                        f"available columns are: [{', '.join(table.columns)}]"
                    )

                fields_to_rename[mapping.value] = mapping.field

            if fields_to_rename:
                table = table.rename(fields_to_rename)

            table = table.with_columns(**{
                constant.name: constant.to_datatype(constant.path[0])
                for constant in self.definition.value_selectors
                if constant.where == 'constant'
            })

            if combined_table is None:
                combined_table = table
            else:
                combined_table = combined_table.vstack(table)

        return combined_table


class ParquetDataRetriever(FrameDataRetriever):
    """
    A retriever for parquet files
    """
    @classmethod
    def get_format(cls) -> str:
        return "parquet"

    @classmethod
    def read_function(cls) -> DataFrameCreator:
        return polars.read_parquet


__FORMAT_MAPPING = {
    "json": JSONDataRetriever,
    "csv": FrameDataRetriever,
    "parquet": ParquetDataRetriever,
}
