import copy
import hashlib
import json
import re
from datetime import date

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from ursa_config import quote_column


def parse_query(statement):
    queries = sqlglot.parse(statement, read="databricks")
    if len(queries) != 1 or not isinstance(queries[0], exp.Query):
        raise ValueError("Exactly one read-only dataset query is required")
    query = queries[0]
    if any(query.find_all(exp.Placeholder)):
        raise ValueError("Parameterized datasets require an explicit materialization boundary")
    return query


def source_identity(table):
    if table.catalog != "synapse-prd" or table.db != "pbi" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table.name):
        raise ValueError(f"Undeclared upstream relation: {table.sql(dialect='databricks')}")
    return ".".join((table.catalog, table.db, table.name))


def source_component(identity):
    parts = identity.split(".")
    if len(parts) != 3 or parts[:2] != ["synapse-prd", "pbi"] or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parts[2]):
        raise ValueError("Invalid upstream source identity")
    return "source_" + parts[1] + "_" + parts[2].lower()


def input_view(identity):
    return "URSA_KPI_input_" + source_component(identity)


def collect_source_columns(statements, source_schemas=None):
    fields = {}
    source_schemas = source_schemas or {}
    for statement in statements:
        query = parse_query(statement)
        for scope in traverse_scope(query):
            selected = {alias: source for alias, (_, source) in scope.selected_sources.items()}
            direct = {alias: source for alias, source in selected.items() if isinstance(source, exp.Table)}
            identities = {alias: source_identity(source) for alias, source in direct.items()}
            for identity in identities.values():
                fields.setdefault(identity, set())
            for selection in scope.expression.selects:
                if isinstance(selection, exp.Star) and direct:
                    raise ValueError("A raw source wildcard is forbidden; declare its required columns")
                if isinstance(selection, exp.Column) and selection.is_star and selection.table in direct:
                    raise ValueError("A raw source wildcard is forbidden; declare its required columns")
            for column in scope.columns:
                if column.table in direct:
                    fields[identities[column.table]].add(column.name)
                elif not column.table and direct:
                    if len(selected) == 1:
                        fields[next(iter(identities.values()))].add(column.name)
                        continue
                    if len(selected) == len(direct) and all(identity in source_schemas for identity in identities.values()):
                        owners = [identity for identity in identities.values() if column.name.casefold() in {name.casefold() for name in source_schemas[identity]}]
                        if len(owners) == 1:
                            fields[owners[0]].add(column.name)
                            continue
                    raise ValueError(f"Ambiguous unqualified upstream column: {column.name}")
    sources = []
    for identity, columns in sorted(fields.items()):
        if not columns:
            raise ValueError(f"No explicit source projection: {identity}")
        if identity in source_schemas:
            available = {name.casefold() for name in source_schemas[identity]}
            if any(column.casefold() not in available for column in columns):
                raise ValueError(f"A required native source column is missing: {identity}")
        projection = sorted(columns, key=str.casefold)
        for column in projection:
            quote_column(column)
        sources.append({"identity": identity, "component": source_component(identity), "columns": projection})
    if len({source["component"] for source in sources}) != len(sources):
        raise ValueError("Source identities collide after normalization")
    return sources


def localize_sources(statement):
    query = parse_query(statement)
    edits = []
    for table in query.find_all(exp.Table):
        if not table.catalog:
            continue
        identity = source_identity(table)
        edits.append((table.args["catalog"].meta["start"], table.this.meta["end"] + 1, quote_column(input_view(identity))))
    for beginning, ending, replacement in sorted(edits, reverse=True):
        statement = statement[:beginning] + replacement + statement[ending:]
    return statement


def freeze_business_date(statement, business_date):
    if not isinstance(business_date, date):
        raise ValueError("A native business date is required")
    query = parse_query(statement)
    return query.transform(
        lambda node: exp.Cast(this=exp.Literal.string(business_date.isoformat()), to=exp.DataType.build("DATE"))
        if isinstance(node, exp.CurrentDate) else node
    ).sql(dialect="databricks")


def consumer_query(statement, component):
    query = parse_query(statement)
    consumer = f"SELECT * FROM `${{var.catalog}}`.gold.`URSA_KPI_{component}${{var.result_suffix}}`"
    ordering = query.args.get("order")
    if ordering:
        ordering = ordering.copy()
        aliases = {selection.this.sql(dialect="databricks"): selection.alias for selection in query.selects if isinstance(selection, exp.Alias)}
        for expression in list(ordering.walk()):
            identity = expression.sql(dialect="databricks")
            if identity in aliases:
                expression.replace(exp.column(aliases[identity], quoted=True))
        for column in ordering.find_all(exp.Column):
            for qualifier in ("table", "db", "catalog"):
                column.set(qualifier, None)
        consumer += "\n" + ordering.sql(dialect="databricks")
    return consumer + "\n"


def preview_consumer_query(statement):
    query = parse_query(statement)
    tables = list(query.find_all(exp.Table))
    if len(tables) != 1 or tables[0].catalog != "${var.catalog}" or tables[0].db != "gold" or not tables[0].name.startswith("URSA_KPI_result_"):
        raise ValueError("A consumer preview must read exactly one bundle-owned gold result")
    tables[0].replace(exp.Table(this=exp.Identifier(this="URSA_KPI_preview_result", quoted=True)))
    return query.sql(dialect="databricks")


def compile_dashboard(source, source_schemas=None):
    datasets = source.get("datasets", [])
    names = [dataset["name"] for dataset in datasets]
    if not names or len(names) != len(set(names)):
        raise ValueError("A nonempty unique dataset inventory is required")
    compiled = copy.deepcopy(source)
    plans = []
    statements = []
    for dataset, consumer in zip(datasets, compiled["datasets"]):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", dataset["name"]):
            raise ValueError("Invalid source dataset identity")
        if dataset.get("parameters"):
            raise ValueError("Dataset parameters cannot be silently frozen")
        statement = dataset.get("query") or "".join(dataset.get("queryLines", []))
        parse_query(statement)
        statements.append(statement)
        component = "result_" + dataset["name"]
        consumer_sql = consumer_query(statement, component)
        consumer.pop("query", None)
        consumer["queryLines"] = consumer_sql.splitlines(keepends=True)
        plans.append({
            "dataset": dataset["name"],
            "component": component,
            "source_sql": statement,
            "local_sql": localize_sources(statement),
            "consumer_sql": consumer_sql,
        })
    sources = collect_source_columns(statements, source_schemas)
    canonical = json.dumps(source, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    plan = {
        "format_version": 1,
        "source_sha256": hashlib.sha256(canonical).hexdigest(),
        "source_inventory": {"datasets": len(datasets), "pages": len(source["pages"]), "widgets": sum(len(page["layout"]) for page in source["pages"])},
        "sources": sources,
        "datasets": plans,
    }
    return compiled, plan