"""Coerce optional upstream containers; required structures are checked by callers."""


def as_object(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []
