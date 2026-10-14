import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope


SOURCE_CATALOG = "synapse-prd"
SOURCE_SCHEMA = "pbi"
SNAPSHOT_PREFIX = "industry_sales_src_"


def snapshot_name(source_table, suffix=""):
    if not re.fullmatch(r"dbx_[a-z0-9_-]+", source_table) or suffix not in ("", "_dev"):
        raise ValueError("Invalid source snapshot name or suffix")
    return SNAPSHOT_PREFIX + source_table.replace("-", "_") + suffix


def is_source(table):
    return isinstance(table, exp.Table) and table.catalog == SOURCE_CATALOG and table.db == SOURCE_SCHEMA


def replace_source_references(statement, catalog="${var.catalog}", suffix="${var.source_snapshot_suffix}"):
    if SOURCE_CATALOG not in statement:
        return statement
    query = sqlglot.parse_one(statement, read="databricks")
    edits = []
    for table in query.find_all(exp.Table):
        if not is_source(table):
            continue
        name = snapshot_name(table.name)
        start = table.args["catalog"].meta["start"]
        end = table.this.meta["end"] + 1
        edits.append((start, end, f"`{catalog}`.silver.`{name}{suffix}`"))
    for start, end, replacement in sorted(edits, reverse=True):
        statement = statement[:start] + replacement + statement[end:]
    return statement


def collect_source_columns(statements):
    columns = {}
    wildcard = set()
    for statement in statements:
        query = sqlglot.parse_one(statement, read="databricks")
        for table in query.find_all(exp.Table):
            if is_source(table):
                columns.setdefault(table.name, set())
        for scope in traverse_scope(query):
            direct = {alias: source for alias, source in scope.sources.items() if is_source(source)}
            for column in scope.columns:
                if column.table in direct:
                    columns[direct[column.table].name].add(column.name)
                elif not column.table:
                    if len(scope.sources) == 1 and len(direct) == 1:
                        columns[next(iter(direct.values())).name].add(column.name)
                    elif direct:
                        wildcard.update(table.name for table in direct.values())
            for selection in scope.expression.selects:
                if isinstance(selection, exp.Star):
                    wildcard.update(table.name for table in direct.values())
                elif isinstance(selection, exp.Column) and selection.is_star and selection.table in direct:
                    wildcard.add(direct[selection.table].name)
    return [
        {"source_table": name, "snapshot_table": snapshot_name(name), "columns": None if name in wildcard or not fields else sorted(fields)}
        for name, fields in sorted(columns.items())
    ]


def validate_manifest(sources):
    if not sources or len({source["source_table"] for source in sources}) != len(sources):
        raise ValueError("Source manifest must be nonempty with unique sources")
    if len({source["snapshot_table"] for source in sources}) != len(sources):
        raise ValueError("Source names collide after snapshot name normalization")
    for source in sources:
        if source["snapshot_table"] != snapshot_name(source["source_table"]):
            raise ValueError("Snapshot destination does not match its source")
        fields = source["columns"]
        if fields is not None and (not fields or len(set(fields)) != len(fields) or any(not isinstance(field, str) or not field or "`" in field for field in fields)):
            raise ValueError("Invalid snapshot projection")
    return sources


def quote_column(column):
    if not column or "`" in column:
        raise ValueError("Invalid column name")
    return f"`{column}`"


def snapshot_view_query(raw, state, columns):
    if not columns:
        raise ValueError("A snapshot view requires source columns")
    projection = ", ".join(quote_column(column) for column in columns)
    return f"SELECT {projection} FROM {raw} WHERE `__industry_snapshot_id` = (SELECT snapshot_id FROM {state})"


def validate_complete_receipts(sources, receipts):
    expected = {source["source_table"] for source in validate_manifest(sources)}
    actual = [receipt["source"] for receipt in receipts]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("A complete, unique receipt is required for every source before publication")


def pinned_snapshot_query(raw, snapshot_id, columns):
    if not re.fullmatch(r"[0-9a-f]{32}", snapshot_id):
        raise ValueError("Invalid completed snapshot ID")
    projection = ", ".join(quote_column(column) for column in columns)
    if not projection:
        raise ValueError("A pinned snapshot requires source columns")
    return f"SELECT {projection} FROM {raw} WHERE `__industry_snapshot_id` = '{snapshot_id}'"