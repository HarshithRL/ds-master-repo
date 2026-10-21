import copy

import sqlglot
from sqlglot import exp


def dataset_sql(dataset):
    if dataset.get("query") and dataset.get("queryLines"):
        raise ValueError("A dataset cannot contain two competing SQL definitions")
    statement = dataset.get("query") or "".join(dataset.get("queryLines", []))
    queries = sqlglot.parse(statement, read="databricks")
    if len(queries) != 1 or not isinstance(queries[0], exp.Query):
        raise ValueError("Exactly one read-only dataset query is required")
    return queries[0].sql(dialect="databricks", comments=False)


def dataset_index(dashboard):
    datasets = dashboard.get("datasets", [])
    names = [dataset.get("name") for dataset in datasets]
    if not names or any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Dataset names must be nonempty and unique")
    return dict(zip(names, datasets))


def merge_presentation(compiled, presentation, plan):
    expected = dataset_index(compiled)
    actual = dataset_index(presentation)
    producers = {dataset["dataset"]: dataset for dataset in plan["datasets"]}
    if set(actual) != set(expected) or set(producers) != set(expected):
        raise ValueError("Adding, removing or renaming datasets requires a reviewed data-model change")
    if set(presentation) - set(compiled) - {"relationshipGraphs"}:
        raise ValueError("Unsupported new dashboard-level settings require review")
    if presentation.get("relationshipGraphs") != compiled.get("relationshipGraphs"):
        raise ValueError("Relationship graph changes require a reviewed data-model change")
    pages = presentation.get("pages", [])
    page_names = [page.get("name") for page in pages]
    if not pages or any(not isinstance(name, str) or not name for name in page_names) or len(page_names) != len(set(page_names)):
        raise ValueError("Pages must be nonempty with unique names")
    if not any(page.get("layout") for page in pages):
        raise ValueError("Refusing to capture an empty dashboard")
    merged = copy.deepcopy(presentation)
    for dataset in merged["datasets"]:
        name = dataset["name"]
        permitted = [expected[name], {"query": producers[name]["source_sql"]}]
        resolved = "".join(expected[name]["queryLines"]).replace("${var.catalog}", "automation_d").replace("${var.result_suffix}", "_dev")
        permitted.append({"query": resolved})
        if dataset_sql(dataset) not in {dataset_sql(candidate) for candidate in permitted}:
            raise ValueError(f"Dataset SQL changed; synchronize its materialization logic separately: {name}")
        if dataset.get("parameters"):
            raise ValueError("Dataset SQL parameters require a reviewed materialization boundary")
        dataset.pop("query", None)
        dataset["queryLines"] = copy.deepcopy(expected[name]["queryLines"])
    return merged


def validate_expression(expression, allowed, description, associative=False):
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError(f"Missing expression: {description}")
    parsed = sqlglot.parse(expression, read="databricks")
    if len(parsed) != 1 or parsed[0] is None or any(parsed[0].find_all(exp.Table, exp.Query, exp.Placeholder)):
        raise ValueError(f"Only a local result-field expression is supported: {description}")
    if associative and parsed[0].sql(dialect="databricks", comments=False).casefold() == "count_if(`associative_filter_predicate_group`)":
        return
    unknown = {column.name for column in parsed[0].find_all(exp.Column) if column.name.casefold() not in allowed}
    if unknown:
        raise ValueError(f"Unknown materialized result columns in {description}: {sorted(unknown)}")


def validate_result_fields(presentation, result_columns):
    datasets = dataset_index(presentation)
    if set(result_columns) != set(datasets) or any(not columns for columns in result_columns.values()):
        raise ValueError("Native result schemas are required for every dataset")
    allowed = {}
    for name, dataset in datasets.items():
        calculated = dataset.get("columns", [])
        labels = [column.get("displayName") for column in calculated]
        if any(not isinstance(label, str) or not label for label in labels) or len({label.casefold() for label in labels}) != len(labels):
            raise ValueError(f"Calculated result fields must have unique names: {name}")
        allowed[name] = {column.casefold() for column in result_columns[name] + labels}
        for column in calculated:
            validate_expression(column.get("expression"), allowed[name], name + "." + column["displayName"])
    for page in presentation["pages"]:
        for item in page.get("layout", []):
            for named_query in item.get("widget", {}).get("queries", []):
                query = named_query.get("query", {})
                name = query.get("datasetName")
                if name not in datasets:
                    raise ValueError(f"Unknown widget dataset: {name}")
                for field in query.get("fields", []):
                    validate_expression(field.get("expression"), allowed[name], name + "." + str(field.get("name")), associative=True)