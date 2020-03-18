import abc
import collections


def convert_from(field=None, name=None):
    def wrapper(func):
        func._convert_from = field
        func._convert_to = name
        return func

    return wrapper


class _MetaConverterMeta(abc.ABCMeta):
    def __init__(cls, name, bases, ns):
        super().__init__(name, bases, ns)
        cls._converters = {}
        _default = object()
        for key, value in ns.items():
            if getattr(value, "_convert_from", _default) is not _default:
                name = value._convert_to or key
                cls._converters[name] = value


class MetaConverter(collections.abc.Mapping, metaclass=_MetaConverterMeta):
    """Convert a metadata dictionary to PDM's format"""

    def __init__(self, source, filename=None):
        self._data = {}
        self.filename = filename
        self._convert(dict(source))

    def __getitem__(self, k):
        return self._data[k]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def _convert(self, source):
        for key, func in self._converters.items():
            if func._convert_from and func._convert_from not in source:
                continue
            if func._convert_from is None:
                value = source
            else:
                value = source[func._convert_from]
            self._data[key] = func(self, value)

        # Delete all used fields
        for key, func in self._converters.items():
            if func._convert_from is None:
                continue
            try:
                del source[func._convert_from]
            except KeyError:
                pass
        # Add remaining items to the data
        self._data.update(source)
