"""Bounded protobuf wire reader; only schema-verified fields are interpreted."""


def varint(data, position):
    value = 0
    for shift in range(0, 70, 7):
        if position >= len(data):
            raise ValueError("truncated protobuf varint")
        byte = data[position]
        position += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, position
    raise ValueError("oversized protobuf varint")


def fields(data):
    if not isinstance(data, bytes) or len(data) > 32 * 1024 * 1024:
        raise ValueError("unsupported protobuf payload")
    position = 0
    result = {}
    while position < len(data):
        tag, position = varint(data, position)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError("invalid protobuf field")
        if wire == 0:
            value, position = varint(data, position)
        elif wire in (1, 2, 5):
            if wire == 2:
                size, position = varint(data, position)
            else:
                size = 8 if wire == 1 else 4
            if size > len(data) - position:
                raise ValueError("truncated protobuf field")
            value = data[position:position + size]
            position += size
        else:
            raise ValueError("unsupported protobuf wire type")
        result.setdefault(number, []).append(value)
    return result


def first(data, number, default=b""):
    return data.get(number, [default])[-1]


def string(data, number):
    value = first(data, number)
    if not isinstance(value, bytes):
        raise ValueError("expected protobuf string")
    return value.decode("utf-8")
