from abc import ABC, abstractmethod
from pbu import JsonDocument


class AbstractMongoDocument(JsonDocument, ABC):
    """
    Abstract parent class for classes representing the objects in a specific MongoDB collection.
    """

    def __init__(self, doc_id=None, data_model_version=None):
        """
        Parent constructor initialising the id and version attributes of this instance.
        :param doc_id: the id under which the object is stored in the database
        :param data_model_version: the current data model version in the system
        """
        super().__init__()
        self.id = doc_id
        if self.id is not None and not isinstance(self.id, str):
            # convert ObjectId to str
            self.id = str(self.id)
        self.data_model_version = data_model_version

    def extract_system_fields(self, json: dict):
        """
        Extracts the id and version from a JSON object or dictionary and maps them to the current instances attributes.
        :param json: the json object or dictionary from which to extract information.
        """
        super().extract_system_fields(json)
        if "_id" in json:
            self.id = str(json["_id"])
        if "dataModelVersion" in json:
            self.data_model_version = json["dataModelVersion"]

    def to_json(self) -> dict:
        """
        Returns a serializable representation of this document as dictionary or JSON object.
        :return: a dictionary or JSON object providing the data contained within this document
        """
        result = super().to_json()
        if self.id is not None:
            result["_id"] = str(self.id)
        if getattr(self, "data_model_version", None) is not None:
            result["dataModelVersion"] = self.data_model_version

        return result
