"""List and filtered list model."""

# standard libraries
import collections.abc
import copy
import functools
import typing

# third party libraries
# None

# local libraries
from nion.utils import Event
from nion.utils import Observable
from nion.utils import Model
from nion.utils import ListModel as ListModelModule


# TODO: logical types: datetime, timestamp, uuid, etc.


MDescription = typing.Dict  # when napolean works: typing.NewType("MDescription", typing.Dict)
MFields = typing.List  # when napolean works: typing.NewType("MFields", typing.List)


STRING = "string"
BOOLEAN = "boolean"
INT = "int"
FLOAT = "double"


def define_string() -> MDescription:
    return "string"


def define_boolean() -> MDescription:
    return "boolean"


def define_int() -> MDescription:
    return "int"


def define_float() -> MDescription:
    return "double"


def define_field(name: str=None, type: str=None, *, default=None) -> MDescription:
    d = {"name": name, "type": type}
    if default is not None:
        d["default"] = default
    return d


def define_record(name: str, fields: MFields) -> MDescription:
    return {"type": "record", "name": name, "fields": fields}


def define_array(items: MDescription) -> MDescription:
    return {"type": "array", "items": items}


def build_model(schema: MDescription, *, default_value=None, value=None):
    if schema in ("string", "boolean", "int", "float"):
        return FieldPropertyModel(default_value if default_value is not None else value)
    type = schema.get("type")
    if type in ("string", "boolean", "int", "float"):
        return FieldPropertyModel(default_value if default_value is not None else value)
    elif type == "record":
        record_values = copy.copy(default_value or dict())
        record_values.update(value or dict())
        return RecordModel(schema, values=record_values)
    elif type == "array":
        return ArrayModel(schema, value if value is not None else default_value)


def build_value(schema: MDescription, *, value=None):
    if schema in ("string", "boolean", "int", "float"):
        return value
    type = schema.get("type")
    if type in ("string", "boolean", "int", "float"):
        return value
    elif type == "record":
        return RecordModel(schema, values=value)
    elif type == "array":
        return ArrayModel(schema, value)


class FieldPropertyModel(Model.PropertyModel):

    def __init__(self, value):
        super().__init__(value=value)
        self.field_value_changed_event = Event.Event()
        self.array_item_inserted_event = Event.Event()
        self.array_item_removed_event = Event.Event()

    @property
    def field_value(self):
        return self.value

    def notify_property_changed(self, key: str) -> None:
        super().notify_property_changed(key)
        self.field_value_changed_event.fire(key)


class RecordModel(Observable.Observable):

    __initialized = False

    def __init__(self, schema: MDescription, *, values=None):
        super().__init__()
        self.__field_models = dict()
        self.__field_model_property_changed_listeners = dict()
        self.__array_item_inserted_listeners = dict()
        self.__array_item_removed_listeners = dict()
        self.schema = schema
        for field_schema in schema["fields"]:
            field_name = field_schema["name"]
            field_type = field_schema["type"]
            field_default = field_schema.get("default")
            field_model = build_model(field_type, default_value=field_default, value=(values or dict()).get(field_name))
            self.__field_models[field_name] = field_model

            def handle_property_changed(field_name, name):
                if name == "value":
                    self.property_changed_event.fire(field_name)

            def handle_array_item_inserted(field_name, key, value, before_index):
                if key == "items":
                    self.item_inserted_event.fire(field_name, value, before_index)

            def handle_array_item_removed(field_name, key, value, index):
                if key == "items":
                    self.item_removed_event.fire(field_name, value, index)

            self.__field_model_property_changed_listeners[field_name] = field_model.field_value_changed_event.listen(functools.partial(handle_property_changed, field_name))
            self.__array_item_inserted_listeners[field_name] = field_model.array_item_inserted_event.listen(functools.partial(handle_array_item_inserted, field_name))
            self.__array_item_removed_listeners[field_name] = field_model.array_item_removed_event.listen(functools.partial(handle_array_item_removed, field_name))
        self.field_value_changed_event = Event.Event()
        self.array_item_inserted_event = Event.Event()
        self.array_item_removed_event = Event.Event()
        self.__initialized = True

    def close(self):
        for field_name in self.__field_models.keys():
            del self.__field_model_property_changed_listeners[field_name]
            del self.__array_item_inserted_listeners[field_name]
            del self.__array_item_removed_listeners[field_name]

    def __getattr__(self, name):
        if name in self.__field_models:
            return self.__field_models[name].field_value
        if name.endswith("_model") and name[:-6] in self.__field_models:
            return self.__field_models[name[:-6]]
        raise AttributeError()

    def __setattr__(self, name, value):
        if self.__initialized and name in self.__field_models and isinstance(self.__field_models[name], FieldPropertyModel):
            self.__field_models[name].value = value
        else:
            super().__setattr__(name, value)

    @property
    def field_value(self):
        return self


class ItemsSequence(collections.abc.MutableSequence):

    def __init__(self, list_model):
        super().__init__()
        self.__list_model = list_model

    def __len__(self):
        return len(self.__list_model.items)

    def __getitem__(self, key):
        return self.__list_model.items[key]

    def __setitem__(self, key, value):
        raise IndexError()

    def __delitem__(self, key):
        self.__list_model.remove_item(key)

    def __contains__(self, item):
        return self.__list_model.items.contains(item)

    def insert(self, index, value):
        self.__list_model.insert_item(index, value)


class ArrayModel(ListModelModule.ListModel):

    def __init__(self, schema: MDescription, values=None):
        if values is not None:
            items = list()
            item_schema = schema["items"]
            for value in values:
                items.append(build_value(item_schema, value=value))
        else:
            items = None
        super().__init__(items=items)
        self.schema = schema
        self.field_value_changed_event = Event.Event()
        self.array_item_inserted_event = Event.Event()
        self.array_item_removed_event = Event.Event()

    @property
    def field_value(self):
        return ItemsSequence(self)

    def notify_insert_item(self, key, value, before_index):
        super().notify_insert_item(key, value, before_index)
        self.array_item_inserted_event.fire(key, value, before_index)

    def notify_remove_item(self, key, value, index):
        super().notify_remove_item(key, value, index)
        self.array_item_removed_event.fire(key, value, index)