import pymongo
import warnings
from typing import Union, List, Any, Type
from bson import ObjectId
from abc import ABC, abstractmethod
from pbumongo.mongo_document import AbstractMongoDocument
from pbu import Logger


class PagingInformation:
    """
    Data structure to store paging information. The first page is page 0
    """

    def __init__(self, page=0, page_size=25):
        """
        Creates a new object with the provided parameters.
        """
        self.page = page
        self.page_size = page_size


_QRY_RES = Union[AbstractMongoDocument, dict]


class AbstractMongoStore(ABC):
    """
    Abstract base class for MongoDB stores. A store is represented by a collection in MongoDB and contains one type of
    documents, which can be represented by a MongoDocument sub-class.
    """

    @abstractmethod
    def __init__(self, mongo_url: str = "mongodb://localhost:27017", mongo_db: str = None, collection_name: str = None,
                 deserialised_class: Type[AbstractMongoDocument] = None, data_model_version=1, db_name=None):
        """
        Creates a new instance of this store providing credentials and behaviour parameters.
        :param mongo_url: the url to the mongo database (including credentials)
        :param mongo_db: the database name on the mongo database server
        :param collection_name: the collection name within the database selected
        :param deserialised_class: a sub-class of AbstractMongoDocument, which can be used to de-serialise documents in
        MongoDB into objects that can be handled easier.
        :param db_name: DEPRECATED: compatibility constructor argument for old code using the named parameter
        :param data_model_version: the data model version of this store.
        """
        if None in [mongo_db, collection_name]:
            raise ValueError("Parameters db_name and collection_name are mandatory and have to be provided.")
        if db_name is not None:
            warnings.warn("Parameter db_name is deprecated and will be removed in future versions. Please use "
                          "mongo_db instead.")
            mongo_db = db_name
        # e.g. mongodb://localhost:27017
        self.mongo_url = mongo_url

        # connect
        client = pymongo.MongoClient(self.mongo_url)
        self.db = client[mongo_db]
        self.collection = self.db[collection_name]

        self.logger = Logger(self.__class__.__name__)
        self.object_class = deserialised_class
        self.data_model_version = data_model_version

    def create(self, document: Union[dict, AbstractMongoDocument], return_doc = False) -> str:
        """
        Creates a new document in the current store/collection.
        :param document: the document to provide either as dictionary or MongoDocument sub-class instance.
        :param return_doc: a boolean to indicate whether the full inserted object is returned or just its id
        :return: the id of the newly created document
        """
        if getattr(document, "to_json", None) is not None:
            document = document.to_json()

        if isinstance(document, dict):
            if "dataModelVersion" not in document and self.data_model_version is not None:
                document["dataModelVersion"] = self.data_model_version
            if "_id" in document:
                del document["_id"]
            insert_id = str(self.collection.insert_one(document).inserted_id)
            return insert_id if return_doc is False else self.get(insert_id)
        raise ValueError("Provided document needs to be a dict or provide a to_json() method which returns a dict")

    def query(self, query: dict, sorting: Union[dict, str] = None, paging: PagingInformation = None) -> List[_QRY_RES]:
        """
        Runs a query against the collection, expecting a list of matching documents to be returned. Documents will be
        parsed into MongoDocuments, if a object class is provided to the store on initialisation.
        :param query: the query to run provided as a dictionary
        :param sorting: a string of the sort attribute (ascending) or a dictionary providing sorting keys and their sort
        direction. The sort direction can be provided either as numeric (-1, 1) or string starting with asc/desc
        case-insensitive.
        :param paging: a paging information object defining the page size and current page
        :return: a list of parsed documents matching the query
        """
        # run query
        current_cursor = self.collection.find(query)

        # check for sorting parameter
        if sorting is not None:
            if isinstance(sorting, str):
                current_cursor = current_cursor.sort(sorting)
            elif isinstance(sorting, dict):
                # sorting by multiple keys

                def _determine_sort_direction(sort_dir: Union[str, int]):
                    """
                    Helper function to determine pymongo sort direction
                    :param sort_dir: the sort direction as provided by the user
                    :return: the sort direction as requested by pymongo
                    """
                    if isinstance(sort_dir, int):
                        return sort_dir
                    else:
                        if sort_dir.lower().startswith("asc"):
                            return 1
                        else:
                            return -1

                if len(sorting.keys()) == 1:
                    # single sort key
                    for k, v in sorting.items():
                        current_cursor = current_cursor.sort(key_or_list=k,
                                                             direction=_determine_sort_direction(v))
                else:
                    # multiple sort keys
                    sort_items = []
                    for k, v in sorting.items():
                        sort_items.push((k, _determine_sort_direction(v)))
                    current_cursor = current_cursor.sort(sort_items)

            else:
                raise ValueError("Sorting needs to be a string or a dictionary")

        # check for paging parameter
        if paging is not None:
            current_cursor = current_cursor.skip(paging.page * paging.page_size).limit(paging.page_size)

        # check for de-serialisation
        if self.object_class is not None:
            return list(map(lambda doc: self.object_class.from_json(doc), current_cursor))

        # don't use serialisation
        return current_cursor

    def query_one(self, query: dict) -> _QRY_RES:
        """
        Runs a query against the collection, expecting a single document to be returned. The result will be parsed into
        a MongoDocument, if the object class is provided on store initialisation.
        :param query: the query to run
        :return: the document that was returned by the database
        """
        result = self.collection.find_one(query)
        if result is None:
            return None

        if self.object_class is None:
            return result
        # parse the result into an object
        return self.object_class.from_json(result)

    def update_one(self, query: dict, update: dict):
        """
        Updates a single document, providing a query and an update set for the one document matching the query.
        :param query: the query to find which document to update
        :param update: the update of the document (provided as $set and $unset)
        :return: the result of the update operation
        """
        if "_id" in query and isinstance(query["_id"], str):
            query["_id"] = AbstractMongoStore.object_id(query["_id"])
        if "$set" in update and "_id" in update["$set"]:
            del update["$set"]["_id"]
        return self.collection.update_one(query, update)

    def update(self, query: dict, update: dict):
        """
        Updates a set of documents matching the provided query, applying the provided update to each matching document.
        :param query: the query expressed as dictionary to select the documents to update
        :param update: the update expressed as dictionary containing $set and/or $unset.
        :return: the result of the update operation
        """
        if "$set" in update and "_id" in update["$set"]:
            del update["$set"]["_id"]
        return self.collection.update_many(query, update)

    def update_full(self, document: _QRY_RES):
        if not isinstance(document, dict):
            if getattr(document, "to_json", None) is None:
                raise ValueError("Provided document needs to be a dict or have a to_json method.")
            document = document.to_json()
            if "dataModelVersion" not in document and self.data_model_version is not None:
                document["dataModelVersion"] = self.data_model_version
        return self.update_one(AbstractMongoStore.id_query(document["_id"]),
                               AbstractMongoStore.set_update_full(document))

    def get(self, doc_id: str) -> _QRY_RES:
        """
        Retrieves the document with the provided document ID
        :param doc_id: the document id to get
        :return:
        """
        return self.query_one(AbstractMongoStore.id_query(doc_id))

    def get_all(self) -> List[_QRY_RES]:
        """
        Returns a list of all items in the current collection.
        :return: a list of documents, if an object class is provided the documents in that list are already parsed into
        the object class.
        """
        return self.query({})

    def delete(self, doc_id: str):
        """
        Deletes a specific document identified by its ID.
        :param doc_id: the id of the document to delete
        :return: the result of the remove operation
        """
        return self.collection.delete_one(AbstractMongoStore.id_query(str(doc_id)))

    def delete_many(self, query: dict):
        return self.collection.delete_many(query)

    @staticmethod
    def object_id(string_id: str):
        """
        Creates a MongoDB ObjectId instance from a given string ID
        :param string_id: the id represented as string
        :return: the same id represented as ObjectId
        """
        return ObjectId(string_id)

    @staticmethod
    def id_query(string_id: str):
        """
        Returns a simple dictionary containing a query for the given id of a document
        :param string_id: the id of a document expressed as string
        :return: a dictionary containing a valid/proper id query for MongoDB.
        """
        return {"_id": AbstractMongoStore.object_id(string_id)}

    @staticmethod
    def set_update_full(set_update: dict) -> dict:
        """
        Creates an update statement that can be evaluated by MongoDB, including all keys of a dictionary passed in.
        :param set_update: a dictionary of all attributes/keys to be updated.
        :return: a dictionary containing a proper/valid update statement for MongoDB.
        """
        if "_id" in set_update:
            del set_update["_id"]
        return {
            "$set": set_update
        }

    @staticmethod
    def unset_update(keys: Union[str, List[str]]):
        """
        Creates a delete query to remove certain keys from a document or list of documents.
        :param keys: a list of keys to delete (or a single key)
        :return: a dictionary containing a proper/valid update statement for MongoDB.
        """
        unset_update = {
            "$unset": {}
        }
        if isinstance(keys, str):
            unset_update["$unset"][keys] = 1
        elif isinstance(keys, list):
            for key in keys:
                unset_update["$unset"][key] = 1
        return unset_update

    @staticmethod
    def set_update(keys: Union[str, List[str]], values: Union[Any, List[Any]]):
        """
        Creates an update query to update a list of keys with a set of values.
        :param keys: a list of string keys or a single string key to update.
        :param values: a list of values or a single value to update. The values will be matched to keys by index.
        :return: a dictionary containing proper/valid update statement for MongoDB.
        """
        set_update = {
            "$set": {}
        }

        if isinstance(keys, str):
            set_update["$set"][keys] = values
        elif isinstance(keys, list):
            for index, key in enumerate(keys):
                set_update["$set"][key] = values[index]

        return set_update

