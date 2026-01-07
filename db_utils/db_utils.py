# ruff: noqa: E402
from sqlalchemy import create_engine
import pandas as pd
from tqdm import tqdm
from sqlalchemy.sql import text
import sqlalchemy
import logging
import locale


import os
import re

project_path = re.sub(
    r"TeNNetViz.*", "TeNNetViz/", os.path.dirname(os.path.abspath(__file__))
)
os.chdir(project_path)
import sys

sys.path.append(project_path)
from db_utils.globals import DB_URL

locale.setlocale(locale.LC_ALL, "")
logger = logging.getLogger("db_utils")
logger.setLevel(logging.INFO)
logging.basicConfig(format="%(asctime)s-%(levelname)s: %(message)s")


def read_table(schema: str, table_name: str) -> pd.DataFrame:
    logger.info(f"Reading table {table_name} from schema {schema}")
    connection = create_engine(f"{DB_URL}{schema}")
    df = pd.read_sql_table(table_name, con=connection)
    connection.dispose()
    logger.info(f"Table read successfully, shape: {df.shape}")
    return df


def read_sql_query(schema: str, query: str) -> pd.DataFrame:
    logger.info(f"Reading table from schema {schema} with query: {query}")
    connection = create_engine(f"{DB_URL}{schema}")
    df = pd.read_sql_query(query, con=connection)
    connection.dispose()
    logger.info(f"Table read successfully, shape: {df.shape}")
    return df


def read_multiple_tables(schema: str, table_names: list) -> dict:
    logger.info(f"Reading tables {table_names} from schema {schema}")
    connection = create_engine(f"{DB_URL}{schema}")
    tables = {}
    for table_name in table_names:
        tables[table_name] = pd.read_sql_table(table_name, con=connection)
        logger.info(
            f"Table {table_name} read successfully, shape: {tables[table_name].shape}"
        )
    connection.dispose()
    return tables


def read_multiple_sql_queries(schema: str, queries: dict) -> dict:
    logger.info(f"Reading tables {queries.keys()} from schema {schema}")
    connection = create_engine(f"{DB_URL}{schema}")
    tables = {}
    for table_name, query in queries.items():
        tables[table_name] = pd.read_sql_query(query, con=connection)
        logger.info(
            f"Table {table_name} read successfully, shape: {tables[table_name].shape}"
        )
    connection.dispose()
    return tables


def create_sql_table(
    schema: str,
    table_name: str,
    df: pd.DataFrame,
    use_default_spec: bool = True,
) -> None:
    logger.info(f"Creating table {table_name} in schema {schema}")
    if use_default_spec:
        outputdict = sqlcol(df)
    else:
        outputdict = None
    connection = create_engine(f"{DB_URL}{schema}")
    df.to_sql(
        table_name,
        con=connection,
        if_exists="replace",
        index=False,
        chunksize=2000,
        method="multi",
        dtype=outputdict,
    )
    connection.dispose()
    logger.info(f"Table {table_name} created successfully")


def format_sql_table(format_function: callable, schema: str):
    format_function(schema)


def insert_rows(
    schema: str,
    table_name: str,
    df: pd.DataFrame,
) -> None:
    logger.info(f"Inserting rows into table {table_name} in schema {schema}")
    connection = create_engine(f"{DB_URL}{schema}")
    df.to_sql(
        table_name,
        con=connection,
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi",
    )
    connection.dispose()
    logger.info("Rows inserted successfully")


def delete_rows(schema: str, table_name: str, condition: str | list[str]) -> None:
    engine = create_engine(f"{DB_URL}{schema}")
    with engine.connect() as con:
        if type(condition) is list:
            logger.info(
                f"Deleting {len(condition)} rows from table {table_name} in schema {schema}"
            )
            cpt = 0
            for cond in tqdm(condition):
                con.execute(text(f"DELETE FROM {table_name} WHERE {cond}"))
                cpt += 1
                if cpt % 100 == 0:
                    con.commit()
        else:
            logger.info(
                f"Deleting row where {condition} from table {table_name} in schema {schema}"
            )
            con.execute(text(f"DELETE FROM {table_name} WHERE {condition}"))
        # commtting the changes
        con.commit()
    engine.dispose()
    logger.info("Rows deleted successfully")


def execute_query(schema: str, query: str | list[str], verbose=False) -> bool:
    if verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.ERROR)
    logger.info(f"Executing query in schema {schema}")
    connection = create_engine(f"{DB_URL}{schema}")
    try:
        with connection.connect() as con:
            if type(query) is list:
                cpt = 0
                # for q in query:
                for q in tqdm(query):
                    con.execute(text(q))
                    cpt += 1
                    if cpt % 100 == 0:
                        con.commit()

            else:
                con.execute(text(query))
            con.commit()
    except Exception as e:
        logger.error(e)
        return False
    connection.dispose()
    logger.info("Query executed successfully")
    return True


def get_update_query(table_name: str, updates: dict, conditions: dict) -> None:
    if len(updates) == 0:
        logger.error("No updates provided")
        return None
    if len(conditions) == 0:
        logger.error("No consditions provided")
        return None
    if len(updates) == 1:
        # print(type(list(updates.values())[0]))
        if type(list(updates.values())[0]) is str:
            update_list = f"{list(updates.keys())[0]} = '{list(updates.values())[0]}'"
        else:
            update_list = f"{list(updates.keys())[0]} = {list(updates.values())[0]}"
    else:
        if type(updates.values()) is str:
            update_list = ", ".join(
                [f"{key} = '{value}'" for key, value in updates.items()]
            )
        else:
            update_list = ", ".join(
                [f"{key} = {value}" for key, value in updates.items()]
            )
    if len(conditions) == 1:
        condition = f"{list(conditions.keys())[0]} = '{list(conditions.values())[0]}'"
    else:
        condition = " AND ".join(
            [f"{key} = '{value}'" for key, value in conditions.items()]
        )

    query = f"UPDATE {table_name} SET {update_list} WHERE {condition}"
    # print(query)
    return query


def get_update_queries(table_name: str, updates: list[dict], conditions: list[dict]):
    return [
        get_update_query(table_name, updates[i], conditions[i])
        for i in range(len(updates))
    ]


def sqlcol(dfparam):
    dtypedict = {}
    for i, j in zip(dfparam.columns, dfparam.dtypes):
        if "object" in str(j):
            dtypedict.update({i: sqlalchemy.types.NVARCHAR(length=255)})

        if "datetime" in str(j):
            dtypedict.update({i: sqlalchemy.types.DateTime()})

        if "float" in str(j):
            dtypedict.update({i: sqlalchemy.types.DECIMAL(precision=7, scale=3)})

        if "int" in str(j):
            dtypedict.update({i: sqlalchemy.types.INT()})

    return dtypedict


def drop_table(schema: str, table_name: str) -> None:
    logger.info(f"Dropping table {table_name} in schema {schema}")
    connection = create_engine(f"{DB_URL}{schema}")
    try:
        with connection.connect() as con:
            query = f"DROP TABLE {table_name}"
            con.execute(text(query))
            con.commit()
    except Exception as e:
        logger.error(e)
        return False
    connection.dispose()
    logger.info(f"Table {table_name} dropped successfully")
