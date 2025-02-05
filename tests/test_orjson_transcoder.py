import timeit
from time import sleep
from typing import Any, Dict, List, Tuple, Union, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import orjson as orjson
from eventsourcing.domain import DomainEvent
from eventsourcing.persistence import (
    DatetimeAsISO,
    JSONTranscoder,
    Transcoder,
    Transcoding,
    UUIDAsHex,
)
from eventsourcing.tests.persistence import (
    CustomType1,
    CustomType1AsDict,
    CustomType2,
    CustomType2AsDict,
    TranscoderTestCase,
)

from _eventsourcing_orjsontranscoder import CDatetimeAsISO, CTupleAsList, CUUIDAsHex
from eventsourcing_orjsontranscoder import OrjsonTranscoder
from tests._orjson_transcodings import (
    CCustomType1AsDict,
    CCustomType2AsDict,
    CMyDictAsDict,
    CMyIntAsInt,
    CMyListAsList,
    CMyStrAsStr,
)


class TupleAsList(Transcoding):
    type = tuple
    name = "tuple_as_list"

    def encode(self, obj: Tuple[Any, ...]) -> List[Any]:
        return list(obj)

    def decode(self, data: List[Any]) -> Tuple[Any, ...]:
        return tuple(data)


class OrjsonTranscoder_Recursive(Transcoder):

    native_types = (str, int, float)

    def __init__(self):
        super().__init__()
        self.register(TupleAsList())
        self._encoders = {
            int: self._encode_pass,
            str: self._encode_pass,
            float: self._encode_pass,
            dict: self._encode_dict,
            list: self._encode_list,
        }

    @staticmethod
    def _encode_pass(obj: Union[int, str, float]) -> Union[int, str, float]:
        return obj

    def _encode_dict(self, obj: dict):
        return {k: self._encode(v) for (k, v) in obj.items()}

    def _encode_list(self, obj: list):
        return [self._encode(v) for v in obj]

    def _encode(self, obj):
        obj_type = type(obj)
        try:
            _encoder = self._encoders[obj_type]
        except KeyError:
            try:
                transcoding = self.types[obj_type]
            except KeyError:
                raise TypeError(
                    f"Object of type {obj_type} is not "
                    "serializable. Please define and register "
                    "a custom transcoding for this type."
                )
            else:
                return self._encode(
                    {
                        "_type_": transcoding.name,
                        "_data_": transcoding.encode(obj),
                    }
                )
        else:
            obj = _encoder(obj)
        return obj

    def encode(self, obj: Any) -> bytes:
        return orjson.dumps(self._encode(obj))

    def _decode(self, obj: Any):
        if type(obj) is dict:
            for key, value in obj.items():
                if not isinstance(value, self.native_types):
                    obj[key] = self._decode(value)
            return self._decode_obj(obj)
        elif type(obj) is list:
            for i, value in enumerate(obj):
                if not isinstance(value, self.native_types):
                    obj[i] = self._decode(value)
            return obj
        return obj

    def _decode_obj(self, d: Dict[str, Any]) -> Any:
        if set(d.keys()) == {
            "_type_",
            "_data_",
        }:
            t = d["_type_"]
            t = cast(str, t)
            try:
                transcoding = self.names[t]
            except KeyError:
                raise TypeError(
                    f"Data serialized with name '{t}' is not "
                    "deserializable. Please register a "
                    "custom transcoding for this type."
                )

            return transcoding.decode(d["_data_"])
        else:
            return d

    def decode(self, data: bytes) -> Any:
        return self._decode(orjson.loads(data))


class TestOrjsonTranscoder(TranscoderTestCase):
    def construct_transcoder(self):
        transcoder = OrjsonTranscoder()
        transcoder.register(CTupleAsList())
        transcoder.register(CDatetimeAsISO())
        transcoder.register(CUUIDAsHex())
        transcoder.register(CCustomType1AsDict())
        transcoder.register(CCustomType2AsDict())
        transcoder.register(CMyDictAsDict())
        transcoder.register(CMyListAsList())
        transcoder.register(CMyIntAsInt())
        transcoder.register(CMyStrAsStr())
        return transcoder

    def test_none_type(self):
        transcoder = self.construct_transcoder()
        obj = None
        data = transcoder.encode(obj)
        copy = transcoder.decode(data)
        self.assertEqual(obj, copy)

    def test_bool(self):
        transcoder = self.construct_transcoder()
        obj = True
        data = transcoder.encode(obj)
        copy = transcoder.decode(data)
        self.assertEqual(obj, copy)

        obj = False
        data = transcoder.encode(obj)
        copy = transcoder.decode(data)
        self.assertEqual(obj, copy)

    def test_float(self):
        transcoder = self.construct_transcoder()
        obj = 3.141592653589793
        data = transcoder.encode(obj)
        copy = transcoder.decode(data)
        self.assertEqual(obj, copy)

        obj = 211.7
        data = transcoder.encode(obj)
        copy = transcoder.decode(data)
        self.assertEqual(obj, copy)

    def test_performance(self):
        transcoder = self.construct_transcoder()
        self._test_performance(transcoder)
        sleep(0.1)
        transcoder = JSONTranscoder()
        transcoder.register(DatetimeAsISO())
        transcoder.register(UUIDAsHex())
        transcoder.register(CustomType1AsDict())
        transcoder.register(CustomType2AsDict())
        self._test_performance(transcoder)
        print("")
        print("")
        print("")
        sleep(0.1)

    def _test_performance(self, transcoder):

        obj = {
            "originator_id": uuid5(NAMESPACE_URL, "some_id"),
            "originator_version": 123,
            "timestamp": DomainEvent.create_timestamp(),
            "a_str": "hello",
            "b_int": 1234567,
            "c_tuple": (1, 2, 3, 4, 5, 6, 7),
            "d_list": [1, 2, 3, 4, 5, 6, 7],
            "e_dict": {"a": 1, "b": 2, "c": 3},
            "f_valueobj": CustomType2(
                CustomType1(UUID("b2723fe2c01a40d2875ea3aac6a09ff5"))
            ),
        }

        # Warm up.
        timeit.timeit(lambda: transcoder.encode(obj), number=100)

        number = 100000
        duration = timeit.timeit(lambda: transcoder.encode(obj), number=number)
        print(
            f"{transcoder.__class__.__name__} encode:"
            f" {1000000 * duration / number:.1f} μs"
        )

        data = transcoder.encode(obj)
        timeit.timeit(lambda: transcoder.decode(data), number=100)

        duration = timeit.timeit(lambda: transcoder.decode(data), number=number)
        print(
            f"{transcoder.__class__.__name__} decode:"
            f" {1000000 * duration / number:.1f} μs"
        )


del TranscoderTestCase
