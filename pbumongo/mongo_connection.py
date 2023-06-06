from typing import Type
from pbumongo.mongo_store import AbstractMongoStore


class MongoConnection:
    def __init__(self, mongo_url: str = "mongodb://localhost:27017", mongo_db: str = None):
        if mongo_db is None:
            raise ValueError("Parameter 'mongo_db' cannot be None")
        if mongo_url is None:
            raise ValueError("Parameter 'mongo_url' cannot be None")
        self.mongo_url = mongo_url
        self.mongo_db = mongo_db

    def create_store(self, store_class: Type[AbstractMongoStore], collection_name: str) -> AbstractMongoStore:
        return store_class(mongo_url=self.mongo_url, mongo_db=self.mongo_db, collection_name=collection_name)
