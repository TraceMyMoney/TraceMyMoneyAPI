from typing import Collection, Dict, Any

from bson.objectid import ObjectId
from mongoengine import Document


class BaseMethods:
    model: Document = None

    @classmethod
    def get_record_with_(cls, **kwargs: Dict) -> Collection:
        return cls.model.objects(**kwargs).first()

    @classmethod
    def get_record_with_id(cls, _id: str) -> Collection:
        return cls.model.objects(id=ObjectId(_id)).first()

    @classmethod
    def get_all_record_with_(cls, **kwargs: Any) -> Collection:
        return cls.model.objects(**kwargs)
