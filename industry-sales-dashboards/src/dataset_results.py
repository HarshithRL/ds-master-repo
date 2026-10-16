import re

import sqlglot
from sqlglot import exp
from sqlglot.tokens import TokenType

from allocation_stages import query_parts
from industry_config import OWNED_TABLE_PREFIX
from source_snapshots import collect_source_columns, is_source


SHARED_CONVERSION_DATASETS = {"ds_quotations", "ds_quotations_detail", "ds_expiring_quotes"}


def has_parameters(expression):
    return any(expression.find_all(exp.Placeholder))


def parameter_contract(expression):
    parameters = set()
    for parameter in expression.find_all(exp.Placeholder):
        if isinstance(parameter.parent, exp.Dot) and parameter.parent.this is parameter:
            parameters.add(parameter.parent.sql(dialect="databricks"))
        else:
            parameters.add(parameter.sql(dialect="databricks"))
    return sorted(parameters)


def result_name(dashboard, dataset, component="result"):
    parts = (dashboard, dataset, component)
    if any(not re.fullmatch(r"[a-z][a-z0-9_]*", part) for part in parts):
        raise ValueError("Invalid dataset result identity")
    return OWNED_TABLE_PREFIX + "industry_sales_" + "_".join(parts)


def dataset_plan(dashboard, dataset, source):
    query = sqlglot.parse_one(source, read="databricks")
    if not has_parameters(query):
        return {"dashboard": dashboard, "dataset": dataset, "mode": "final", "table": result_name(dashboard, dataset), "source_sql": source, "parameters": []}
    with_clause = query.args.get("with")
    ctes = with_clause.expressions if with_clause else []
    return {
        "dashboard": dashboard,
        "dataset": dataset,
        "mode": "filtered",
        "source_sql": source,
        "parameters": parameter_contract(query),
        "parameter_ctes": [cte.alias_or_name for cte in ctes if has_parameters(cte.this)],
    }


def parameter_defaults(statement):
    for parameter in ("segment_filter", "country_filter", "priority_filter", "days_bucket_filter"):
        statement = statement.replace(":" + parameter, "CAST(NULL AS ARRAY<STRING>)")
    for parameter in ("cancel_date.min", "cancel_date.max"):
        statement = statement.replace(":" + parameter, "CAST(NULL AS DATE)")
    parsed_statement = "SELECT 1 FROM input " + statement if statement.lstrip().upper().startswith("WHERE") else statement
    if parsed_statement.strip() and has_parameters(sqlglot.parse_one(parsed_statement, read="databricks")):
        raise ValueError("Unknown dynamic parameter; explicit contract required")
    return statement


def table_edits(statement, replacements):
    parsed = sqlglot.parse_one(statement, read="databricks")
    edits = []
    for table in parsed.find_all(exp.Table):
        identity = ".".join(part for part in (table.catalog, table.db, table.name) if part)
        if identity not in replacements:
            continue
        first = table.args.get("catalog") or table.args.get("db") or table.this
        edits.append((first.meta["start"], table.this.meta["end"] + 1, replacements[identity]))
    for start, end, replacement in sorted(edits, reverse=True):
        statement = statement[:start] + replacement + statement[end:]
    return statement


def local_result(table):
    return f"`${{var.catalog}}`.gold.`{table}${{var.result_suffix}}`"


def result_consumer(source, table):
    query = sqlglot.parse_one(source, read="databricks")
    statement = "SELECT * FROM " + local_result(table)
    ordering = query.args.get("order")
    if ordering:
        ordering = ordering.copy()
        aliases = {selection.this.sql(dialect="databricks"): selection.alias for selection in query.selects if isinstance(selection, exp.Alias)}
        for expression in list(ordering.walk()):
            identity = expression.sql(dialect="databricks")
            if identity in aliases:
                expression.replace(exp.Column(this=exp.Identifier(this=aliases[identity], quoted=True)))
        for column in ordering.find_all(exp.Column):
            for qualifier in ("table", "db", "catalog"):
                column.set(qualifier, None)
        statement += "\n" + ordering.sql(dialect="databricks")
    return statement


def input_rows(statement, row_table):
    parsed = sqlglot.parse_one(statement, read="databricks")
    if not isinstance(parsed, exp.Select) or any(parsed.find_all(exp.Star)):
        raise ValueError("Filtered row boundary requires an explicit SELECT without wildcards")
    tokens = sqlglot.tokenize(statement, read="databricks")
    depth = 0
    clauses = {}
    for token in tokens:
        if token.token_type == TokenType.R_PAREN:
            depth -= 1
        if depth == 0 and token.token_type in (TokenType.FROM, TokenType.WHERE, TokenType.GROUP_BY, TokenType.HAVING, TokenType.QUALIFY, TokenType.ORDER_BY, TokenType.LIMIT):
            clauses.setdefault(token.token_type, token.start)
        if token.token_type == TokenType.L_PAREN:
            depth += 1
    start = clauses.get(TokenType.FROM)
    if start is None:
        raise ValueError("Filtered computation has no FROM clause")
    end = min([position for position in clauses.values() if position > start] or [len(statement)])
    fields = {}
    edits = []
    named_outputs = {id(selection): selection.name for selection in parsed.selects if isinstance(selection, exp.Column)}
    for column in parsed.find_all(exp.Column):
        if not column.table:
            continue
        identity = column.sql(dialect="databricks")
        field = fields.setdefault(identity, "__input_" + str(len(fields)))
        column_start = (column.args.get("catalog") or column.args.get("db") or column.args["table"]).meta["start"]
        column_end = column.this.meta["end"] + 1
        if not (start <= column_start < end):
            output_alias = " AS `" + named_outputs[id(column)] + "`" if id(column) in named_outputs else ""
            edits.append((column_start, column_end, f"`{field}`" + output_alias))
    if not fields:
        raise ValueError("No filterable source fields discovered")
    select = ", ".join(f"{identity} AS `{field}`" for identity, field in fields.items())
    where_start = clauses.get(TokenType.WHERE)
    where_end = min([position for position in clauses.values() if where_start is not None and position > where_start] or [len(statement)])
    where = "" if where_start is None else statement[where_start:where_end]
    producer = "SELECT " + select + "\n" + statement[start:end] + "\n" + parameter_defaults(where)
    edits.append((start, end, "FROM " + local_result(row_table) + "\n"))
    consumer = statement
    for beginning, ending, replacement in sorted(edits, reverse=True):
        consumer = consumer[:beginning] + replacement + consumer[ending:]
    return producer, consumer


def compile_dataset(dashboard, dataset, source, source_schemas):
    plan = dataset_plan(dashboard, dataset, source)
    if plan["mode"] == "final":
        plan["producers"] = [{"component": "result", "table": plan["table"], "sql": source}]
        plan["consumer_sql"] = result_consumer(source, plan["table"])
        return plan
    stages, final = query_parts(source)
    names = {name for name, statement in stages}
    dynamic = set()
    steps = []
    consumers = []
    exposed = set()
    for name, statement in stages:
        parsed = sqlglot.parse_one(statement, read="databricks")
        references = {table.name for table in parsed.find_all(exp.Table) if not table.catalog and table.name in names}
        if has_parameters(parsed):
            if references & dynamic:
                raise ValueError("A nested parameterized computation requires an explicit materialization boundary")
            row_table = result_name(dashboard, dataset, name + "_rows")
            producer, consumer = input_rows(statement, row_table)
            steps.append({"component": name + "_rows", "table": row_table, "sql": producer})
            dynamic.add(name)
            consumers.append((name, consumer))
        elif references & dynamic:
            dynamic.add(name)
            consumers.append((name, statement))
        else:
            steps.append({"component": name, "table": None, "sql": statement})
    final_query = sqlglot.parse_one(final, read="databricks")
    final_references = {table.name for table in final_query.find_all(exp.Table) if not table.catalog and table.name in names}
    if not stages or (has_parameters(final_query) and not (final_references & dynamic)):
        row_table = result_name(dashboard, dataset, "filtered_rows")
        producer, final = input_rows(final, row_table)
        steps.append({"component": "filtered_rows", "table": row_table, "sql": producer})
    consumer_fragments = [statement for name, statement in consumers] + [final]
    for statement in consumer_fragments:
        parsed = sqlglot.parse_one(statement, read="databricks")
        exposed.update(table.name for table in parsed.find_all(exp.Table) if not table.catalog and table.name in names and table.name not in dynamic)
    replacements = {
        "supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping": "`${var.catalog}`.gold.`${var.mapping_table_name}`",
    }
    for step in steps:
        if step["component"] in exposed:
            shared = dashboard == "quotations" and dataset in SHARED_CONVERSION_DATASETS and step["component"] == "converted"
            step["table"] = result_name(dashboard, "shared" if shared else dataset, step["component"])
            if shared:
                step["shared"] = True
            replacements[step["component"]] = local_result(step["table"])
    for statement in consumer_fragments:
        for table in sqlglot.parse_one(statement, read="databricks").find_all(exp.Table):
            if not is_source(table):
                continue
            identity = ".".join((table.catalog, table.db, table.name))
            if identity in replacements:
                continue
            lookup_name = "lookup_" + table.name.replace("-", "_")
            fields = next(item["columns"] for item in collect_source_columns([source], source_schemas) if item["source_table"] == table.name)
            if fields is None:
                raise ValueError("An interactive lookup cannot require an unbounded wildcard source")
            result = result_name(dashboard, dataset, lookup_name)
            steps.append({"component": lookup_name, "table": result, "sql": "SELECT " + ", ".join(f"`{field}`" for field in fields) + f" FROM `{table.catalog}`.`{table.db}`.`{table.name}`"})
            replacements[identity] = local_result(result)
    consumer = ""
    if consumers:
        consumer = "WITH " + ",\n".join(name + " AS (\n" + table_edits(statement, replacements) + "\n)" for name, statement in consumers) + "\n"
    consumer += table_edits(final, replacements)
    if any(is_source(table) for table in sqlglot.parse_one(consumer, read="databricks").find_all(exp.Table)):
        raise ValueError("Interactive consumer still requires upstream access")
    original_parameters = parameter_contract(sqlglot.parse_one(source, read="databricks"))
    consumer_parameters = parameter_contract(sqlglot.parse_one(consumer, read="databricks"))
    if original_parameters != consumer_parameters:
        raise ValueError("Materialization changed the native parameter contract")
    plan["producers"] = steps
    plan["consumer_sql"] = consumer
    return plan


def result_storage_name(table):
    if not re.fullmatch(re.escape(OWNED_TABLE_PREFIX) + r"industry_sales_[a-z0-9_]+", table):
        raise ValueError("Invalid result table identity")
    return table.replace(OWNED_TABLE_PREFIX + "industry_sales_", OWNED_TABLE_PREFIX + "industry_sales_calc_", 1)


def unique_result_producers(plans):
    producers = {}
    for plan in plans:
        for producer in plan["producers"]:
            table = producer["table"]
            if not table:
                continue
            parsed = sqlglot.parse_one(producer["sql"], read="databricks")
            if producer.get("shared"):
                if table != result_name("quotations", "shared", "converted") or any(not source.catalog for source in parsed.find_all(exp.Table)):
                    raise ValueError("Shared result must be an independent conversion computation")
            if table in producers:
                previous = producers[table]
                if not producer.get("shared") or not previous.get("shared") or parsed.sql(dialect="databricks") != sqlglot.parse_one(previous["sql"], read="databricks").sql(dialect="databricks"):
                    raise ValueError("Conflicting or unapproved shared result computation")
            else:
                producers[table] = producer
    return producers


def validate_result_receipts(plans, receipts):
    identities = [(plan["dashboard"], plan["dataset"]) for plan in plans]
    if len(identities) != 18 or len(set(identities)) != 18:
        raise ValueError("All eighteen unique active dataset plans are required")
    unique_result_producers(plans)
    expected = [(plan["dashboard"], plan["dataset"], producer["table"]) for plan in plans for producer in plan["producers"] if producer["table"]]
    actual = [(receipt["dashboard"], receipt["dataset"], receipt["table"]) for receipt in receipts]
    if len(expected) != len(set(expected)) or len(actual) != len(expected) or set(actual) != set(expected):
        raise ValueError("Every unique dataset result must verify before publication")