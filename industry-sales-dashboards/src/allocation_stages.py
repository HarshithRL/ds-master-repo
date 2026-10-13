from datetime import date

import sqlglot
from sqlglot import exp
from sqlglot.tokens import TokenType


def freeze_date(expression, as_of_date):
    for current_date in list(expression.find_all(exp.CurrentDate)):
        current_date.replace(exp.Cast(this=exp.Literal.string(as_of_date.isoformat()), to=exp.DataType.build("DATE")))
    return expression


def build_stages(source, as_of_date):
    if not isinstance(as_of_date, date):
        raise ValueError("An explicit business date is required")
    query = sqlglot.parse_one(source, read="databricks")
    with_clause = query.args.get("with")
    if with_clause is None or with_clause.args.get("recursive"):
        raise ValueError("Expected a nonrecursive allocation CTE query")
    stages = []
    names = set()
    tokens = sqlglot.tokenize(source, read="databricks")
    token_positions = {token.start: index for index, token in enumerate(tokens)}
    closing_index = None
    for cte in with_clause.expressions:
        name = cte.alias_or_name
        if not name or name in names:
            raise ValueError("CTE names must be nonempty and unique")
        names.add(name)
        alias_start = cte.args["alias"].this.meta["start"]
        opening_index = token_positions[alias_start] + 1
        while tokens[opening_index].token_type != TokenType.L_PAREN:
            opening_index += 1
        depth = 1
        closing_index = opening_index + 1
        while depth:
            token = tokens[closing_index]
            if token.token_type == TokenType.L_PAREN:
                depth += 1
            elif token.token_type == TokenType.R_PAREN:
                depth -= 1
            closing_index += 1
        closing_index -= 1
        body = source[tokens[opening_index].end + 1:tokens[closing_index].start]
        stages.append((name, freeze_sql_date(body, as_of_date)))
    final = freeze_sql_date(source[tokens[closing_index].end + 1:].strip().rstrip(";"), as_of_date)
    return stages, final


def freeze_sql_date(statement, as_of_date):
    tokens = sqlglot.tokenize(statement, read="databricks")
    replacements = []
    for index, token in enumerate(tokens):
        if token.text.upper() != "CURRENT_DATE" or token.token_type in (TokenType.IDENTIFIER, TokenType.STRING):
            continue
        end = token.end + 1
        if index + 2 < len(tokens) and tokens[index + 1].token_type == TokenType.L_PAREN and tokens[index + 2].token_type == TokenType.R_PAREN:
            end = tokens[index + 2].end + 1
        replacements.append((token.start, end))
    for start, end in reversed(replacements):
        statement = statement[:start] + f"CAST('{as_of_date.isoformat()}' AS DATE)" + statement[end:]
    return statement


def output_table_name(mapping_table_name):
    prefix = "industry_sales_cs_team_sales_org_mapping"
    if mapping_table_name not in (prefix, prefix + "_dev"):
        raise ValueError("Unexpected mapping table name")
    return "industry_sales_open_orders_allocation" + ("_dev" if mapping_table_name.endswith("_dev") else "")