# Python Basic Utilities - Mongo `pbumongo`

Available on [PyPi](https://pypi.org/project/pbumongo/)

**Table of Contents**

1. [Installation](#installation)
2. [Usage](#usage)
3. [Classes](#classes)
    1. [AbstractMongoStore](#abstractmongostore) - abstract class for handling MongoDB collection access
       1. [MongoConnection](#mongoconnection) - a helper class to assist with creating multiple store instances 
    2. [AbstractMongoDocument](#abstractmongodocument) - abstract class for wrapping MongoDB BSON documents
    3. [ProgressUpdater](#progressupdater) - a collection of classes to help with updating job progress 


## Installation

Install via pip:

```bash
pip install pbumongo
```

## Usage

It is good practice associating a sub-class of `AbstractMongoDocument` with a sub-class of `AbstractMongoStore`. This is
done through the `deserialised_class` parameter in the `super()` constructor call of the store class. Any method for
querying documents will use that class to deserialise the BSON document into the provided class, which should extend
`AbstractMongoDocument`.

Example: let's say we want to implement access to a collection containing user documents. We'll define a class `User`
that extends `AbstractMongoDocument` and a class `UserStore` that extends `AbstractMongoStore`.

```python
# main imports
from pbumongo import AbstractMongoDocument, AbstractMongoStore
# supporting imports
import crypt
from typing import List, Optional
from time import time


# this is an example of a minimum viable class
class User(AbstractMongoDocument):
    def __init__(self):
        super().__init__()
        # define attributes with meaningful defaults
        self.username: str = None
        self.password: str = None
        self.permissions: List[str] = []
        self.last_login: int = 0

    def get_attribute_mapping(self) -> dict:
        # the values are what is used inside MongoDB documents
        return {
            "username": "username",
            "password": "password",
            "permissions": "permissions",
            "last_login": "lastLogin"
        }

    @staticmethod
    def from_json(json: dict):
        user = User()
        user.extract_system_fields(json)
        return user


class UserStore(AbstractMongoStore):
    def __init__(self, mongo_url, mongo_db, collection_name):
        super().__init__(mongo_url, mongo_db, collection_name, deserialised_class=User, data_model_version=1)

    def login(self, username, password) -> Optional[User]:
        # encrypt the password!
        pw_encrypted = crypt.crypt(password, crypt.METHOD_MD5)
        user: Optional[User] = self.query_one({"username": username, "password": pw_encrypted})
        if user is not None:
            # update last_login attribute and save it in database as well
            user.last_login = round(time())
            self.update_one(AbstractMongoStore.id_query(user.id),
                            AbstractMongoStore.set_update("lastLogin", user.last_login))
        return user

    def create_user(self, username, password) -> User:
        # check if this user already exists
        existing = self.query_one({"username": username})
        if existing is not None:
            raise ValueError(f"User with username '{username}' already exists.")
        # create new user object
        user = User()
        user.username = username
        user.password = crypt.crypt(password, crypt.METHOD_MD5)
        # store in database and return document
        user_id = self.create(user)
        return self.get(user_id)
```

#### MongoConnection

To use these classes in your application, you can use the MongoConnection helper or create the `UserStore` class
instance directly. The `MongoConnection` helper is useful, when you have a lot of collections and don't want to repeat
the mongo connection URL and DB name for every constructor.

```python
from pbumongo import MongoConnection
from mypackage import UserStore  # see implementation above

con = MongoConnection("mongodb://localhost:27017", "myDbName")
user_store = con.create_store(store_class=UserStore, collection_name="users")

user = user_store.login(username="admin", password="mypassword")
```

## Classes

### `AbstractMongoStore`

This is an abstract class and cannot be instantiated directly. Instead, define a class that extends this class.

**Constructor**

`__init__(mongo_url, mongo_db, collection_name, deserialised_class, data_model_version=1)`

- `mongo_url` - this is the Mongo connection URL containing the host, port and optional username, password
- `mongo_db` - this is the Mongo DB name - the one you provide when using `use <dbname>` on the Mongo shell
- `collection_name` - the name of the collection - e.g. `myCollection` for `db.myCollection.find({})` on the Mongo shell
- `deserialised_class` - used for all the query methods to deserialise the BSON document into a class with attributes
  for easier access
- `data_model_version` - a number that can be used for database migration as an app develops over time

**Methods**

- `get(doc_id: str)` - fetches a single document with a matching `doc_id == document["_id"]`
- `get_all()` - fetches the entire collection content and deserialises every document. Careful, this is not an iterator,
  but returns a `list` of all the documents and can consume quite a bit of compute and memory.
- `create(document)` - creates a new document and returns the `_id` of the newly created BSON document as string. The
  `document` can be either `dict` or an instance of the `deserialised_class` provided in the `super().__init(..)` call.
  - Since version 1.0.1 a new parameter is available `create(document, return_doc=True)` which will return the entire
    document/object instead of just the `_id` of the newly created document. 
- `query_one(query: dict)` - fetches a single document and deserialises it or returns `None` if no document can be found
- `query(query: dict, sorting, paging)` - fetches multiple documents and deserialises them. `sorting` can be an
  attribute name (as provided in the BSON) or a dictionary with the sort order. `paging` is an instance of
  `pbumongo.PagingInformation`.
- `update_one(query: dict, update: dict)` - proxies the `db.collection.updateOne(..)` function from the Mongo shell
- `update(query:, update: dict` - same as `update_one`, but will update multiple documents, if the query matches
- `update_full(document)` - shortcut for updating the entire document with an updated version, the query will be
  constructed from the `id`/`_id` provided by the `document`.
- `delete(doc_id)` - deletes a single document with the provided document ID
- `delete_many(query: dict)` - deletes multiple documents matching the query.

**Static Methods**

- `AbstractMongoStore.id_query(string_id: str)` - creates a query `{ "_id": ObjectId(string_id) }`, which can be used to
  query the database
- `AbstractMongoStore.set_update(keys, values)` - creates a `$set` update statement. If only a single attribute is 
  updated, you can pass them directly as parameters, e.g. updating a key `"checked": True`, can be done by 
  `.set_update("checked", True)`. If you update multiple attributes provide them as list in the matching order.
- `AbstractMongoStore.unset_update(keys)` - creates an `$unset` update statement with the attributes listed as `keys`.
  Similarly to `.set_update`, you can provide a single key without a list for ease of use.
  
### `AbstractMongoDocument`

This is an abstract class and cannot be instantiated directly. Instead, define a class that extends this class.

**Constructor**

`__init__(doc_id=None, data_model_version=None)`

The parameters are entirely optional. Generally it is recommended to use the static method `from_json(json: dict)` to 
create BSON documents you've loaded from the database instead of calling the constructor. For new documents, you would
not provide the `_id` as the store class handles that.

**Methods**

For methods and static methods please see the documentation of `JsonDocument` from `pbu`. `AbstractMongoDocument` 
extends that class.


### `ProgressUpdater`

The `ProgressUpdaer` class is part of a set of classes that assist with keeping track of job progress. The other classes
are:

- `ProgressObject`: a database object with fields for a status (see `pbu` > `JobStatus`), start and end timestamp, 
 total count, processed count, a list of errors and a main error.
- `ProgressObjectStore`: an abstract class that provides store methods to update status, progress and errors of a 
 `ProgressObject`
- `ProgressError`: a JSON document containing an error message as well as a dictionary for data related to the error. 
 These objects will be appeneded to a `ProgressObject`'s `errors` list.
- `ProgressUpdater`: an object to pass into a processor, which holds references to the progress store and progress 
 object and provides methods for updating progress and handling errors.

Both, `ProgressObject` and `ProgressObjectStore` are abstract classes and should be extended with remaining attributes 
of a process / job definition (like a name/label, extra configuration, etc.). `ProgressObject` is an 
`AbstractMongoDocument` and `ProgressUpdateStore` is an `AbstractMongoStore`.
