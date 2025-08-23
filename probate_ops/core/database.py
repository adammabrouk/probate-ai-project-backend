from .settings import settings
from peewee import PostgresqlDatabase

postgres_db = PostgresqlDatabase(
    host="34.55.11.203",
    database="postgres",
    user="postgres",
    password=settings.POSTGRES_PASSWORD,
)