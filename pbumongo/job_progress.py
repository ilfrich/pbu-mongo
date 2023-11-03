from time import time
from abc import ABC
from typing import List, Type
from pbu import JobStatus, JsonDocument, list_to_json
from pbumongo.mongo_document import AbstractMongoDocument
from pbumongo.mongo_store import AbstractMongoStore


class ProgressError(JsonDocument):
    def __init__(self):
        super().__init__()
        self.message: str = None
        self.data: dict = None
        self.timestamp: int = 0

    def get_attribute_mapping(self) -> dict:
        return {
            "message": "message",
            "data": "data",
            "timestamp": "timestamp",
        }

    @staticmethod
    def create(message: str, data: dict):
        error = ProgressError()
        error.message = message
        error.data = data
        error.timestamp = round(time())
        return error


class ProgressObject(AbstractMongoDocument, ABC):
    def __init__(self):
        super().__init__()
        # job attributes
        self.status: str = JobStatus.CREATED
        self.start_ts: int = 0
        self.end_ts: int = 0
        self.progress: int = 0
        self.total: int = 0
        self.error = None
        self.errors: List[ProgressError] = []

    def get_attribute_mapping(self) -> dict:
        return {
            "status": "status",
            "start_ts": "startTs",
            "end_ts": "endTs",
            "progress": "progress",
            "total": "total",
            "error": "error",
            "errors": "errors",
        }

    def get_custom_mapping(self) -> dict:
        return {
            "errors": ProgressError,
        }

    def reset_progress(self):
        self.progress = 0
        self.start_ts = 0
        self.end_ts = 0

    def reset_errors(self):
        self.error = None
        self.errors = []


class ProgressObjectStore(AbstractMongoStore, ABC):

    def __init__(self, mongo_url: str = "mongodb://localhost:27017", mongo_db: str = None, collection_name: str = None,
                 deserialised_class: Type[AbstractMongoDocument] = None, data_model_version=1, db_name=None):
        super().__init__(mongo_url, mongo_db, collection_name, deserialised_class, data_model_version, db_name)

    def update_totals(self, report: ProgressObject):
        return self.update_one(AbstractMongoStore.id_query(report.id),
                               AbstractMongoStore.set_update("total", report.total))

    def update_progress(self, report: ProgressObject):
        return self.update_one(AbstractMongoStore.id_query(report.id),
                               AbstractMongoStore.set_update("progress", report.progress))

    def update_errors(self, report: ProgressObject):
        return self.update_one(AbstractMongoStore.id_query(report.id),
                               AbstractMongoStore.set_update(["error", "errors"],
                                                             [report.error, list_to_json(report.errors)]))

    def update_status(self, object_id: str, new_status: str, error_msg: str = None):
        update_keys = ["status"]
        update_values = [new_status]
        if new_status in [JobStatus.COMPLETED, JobStatus.ERROR, JobStatus.SUCCESS]:
            # reached an end state
            update_keys.append("endTs")
            update_values.append(round(time()))
        if new_status == JobStatus.RUNNING:
            # need to double-check if this is resuming
            report: ProgressObject = self.get(object_id)
            if report is None:
                raise ValueError("Trying to update status of not existing object")
            if report.status == JobStatus.CREATED:
                # only set start time, if the current job status is new / CREATED
                update_keys.append("startTs")
                update_values.append(round(time()))

        if error_msg is not None or new_status in [JobStatus.CREATED, JobStatus.RESUMED]:
            update_keys.append("error")
            update_values.append(error_msg)

        return self.update_one(AbstractMongoStore.id_query(object_id),
                               AbstractMongoStore.set_update(update_keys, update_values))


class ProgressUpdater:
    def __init__(self, store: ProgressObjectStore, obj: ProgressObject):
        self.store: ProgressObjectStore = store
        self.obj: ProgressObject = obj

    def update_progress(self, count: int = 1):
        self.obj.progress += count
        self.store.update_progress(self.obj)

    def update_total(self, total: int = 0):
        self.obj.total = total
        self.store.update_totals(self.obj)

    def get_status(self) -> str:
        # reload from db
        self.obj: ProgressObject = self.store.get(self.obj.id)
        return self.obj.status

    def add_error(self, message: str, data: dict):
        self.obj: ProgressObject = self.store.get(self.obj.id)
        # check if error already exists
        existing_error = list(filter(lambda x: str(x.data) == str(data), self.obj.errors))
        if len(existing_error) > 0:
            # just update the message (as error can change)
            existing_error[0].message = message
        else:
            # add new error object
            error = ProgressError.create(message, data)
            self.obj.errors.append(error)
        self.store.update_errors(self.obj)

    def remove_error(self, data: dict):
        self.obj: ProgressObject = self.store.get(self.obj.id)
        # check if an error exists
        filtered_errors = list(filter(lambda x: str(x.data) != str(data), self.obj.errors))
        if len(filtered_errors) < len(self.obj.errors):
            self.obj.errors = filtered_errors
            self.store.update_errors(self.obj)
