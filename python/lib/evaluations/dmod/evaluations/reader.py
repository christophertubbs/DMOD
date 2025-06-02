"""
Defines a function used to select specific data from a dictionary based on a configured path
"""
import typing

import polars
import jsonpath_ng as jsonpath


from . import specification


def select_values(document: dict, selector: specification.ValueSelector) -> typing.Optional[polars.DataFrame]:
    """
    Retrieve data from a dictionary based on a configuration path and load it into a dataframe

    Args:
        document: The dictionary to navigate and collect data from
        selector: The value selector that details what all to retrieve

    Returns:
        A dataframe containing the selected values
    """
    table: typing.Optional[polars.DataFrame] = None
    origin_expression: jsonpath.This = jsonpath.parse(".".join(selector.origin))

    for element in origin_expression.find(document):
        full_path = str(element.full_path)

        main_path = full_path + "." + ".".join(selector.path)
        value_expression: jsonpath.This = jsonpath.parse(main_path)

        value_results = value_expression.find(document)

        if not value_results:
            continue

        columns = {}

        if len(value_results) == 1:
            if selector.where == "key":
                columns[selector.name] = selector.to_datatype(value_results[0].path)
            else:
                columns[selector.name] = selector.to_datatype(value_results[0].value)
        else:
            if selector.where == "key":
                columns[selector.name] = [
                    selector.to_datatype(result.path)
                    for result in value_results
                ]
            else:
                columns[selector.name] = [
                    selector.to_datatype(result.value)
                    for result in value_results
                ]

        for index in selector.associated_fields:
            if selector.where.lower() == "key":
                column_data = []
                missing_entries = 0

                for result in value_results:
                    index_path = f"{str(result.full_path)}.{'.'.join(index.path)}"
                    index_expression = jsonpath.parse(index_path)
                    index_results = index_expression.find(document)

                    if not index_results:
                        missing_entries += 1
                        column_data.append(None)
                    else:
                        column_data.append(index.to_datatype(index_results[0].value))

                if len(column_data) == 0 or len(column_data) == missing_entries:
                    raise KeyError(
                            f"There are no values for the index named '{index.name}' at "
                            f"'{full_path + '.*.' + '.'.join(index.path)}'"
                    )

                if len(column_data) == 1:
                    columns[index.name] = column_data[0]
                else:
                    columns[index.name] = column_data
            else:
                index_path = full_path + "." + ".".join(index.path)

                index_expression: jsonpath.This = jsonpath.parse(index_path)
                index_results = index_expression.find(document)

                if not index_results:
                    raise KeyError(f"There are no values for the index named '{index.name}' at '{index_path}'")

                if len(index_results) == 1:
                    # We're dealing with a scalar
                    columns[index.name] = index.to_datatype(index_results[0].value)
                else:
                    # we're dealing with a vector
                    columns[index.name] = [
                        index.to_datatype(result.value)
                        for result in index_results
                    ]

        if table is None:
            table = polars.DataFrame(data=columns)
        else:
            table = table.vstack(polars.DataFrame(data=columns))

    return table
