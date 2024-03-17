from enum import Enum
from typing import Any, Union, Type, Callable
import re

class Configuration:
    def __init__(self, parameters: dict):
        self.parameters = parameters

    def to_dict(self):
        return self.parameters

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)

class ParamType(Enum):
    ORDINAL = 1
    CATEGORICAL = 2
    BOOLEAN = 3
    INTEGER = 4
    REAL = 5
    PERMUTATION = 6
    STRING = 7
    INTEGER_EXP = 8
    NUMERIC = 9

class Param:
    param_type_enum: ParamType = None  # This should be overridden in each subclass

    def __init__(self, name: str, default: Any, **kwargs):
        self.name = name
        self.default = default
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)

    # Function to convert ParamType to its string representation and vice versa
    @staticmethod
    def param_type_to_string(param_type: ParamType) -> str:
        return param_type.name.lower()

class Categorical(Param):
    param_type_enum = ParamType.CATEGORICAL
    def __init__ (self, name: str, categories: list, default: Any, **kwargs):
        super().__init__(name, default, **kwargs)
        self.categories = categories

class Permutation(Param):
    param_type_enum = ParamType.PERMUTATION

    def __init__(self, name: str, length: int, default: tuple, **kwargs):
        super().__init__(name, default, **kwargs)
        self.length = length

class Boolean(Param):
    param_type_enum = ParamType.BOOLEAN

class Numeric(Param):
    param_type_enum = ParamType.NUMERIC

    def __init__(self, name: str, bounds: tuple, default: int,
                 transform: Callable[[Any], Any] = lambda x: x, **kwargs):
        super().__init__(name, default, bounds=bounds, transform=transform, **kwargs)
        self.lower, self.upper = bounds[:2]
        self.step = bounds[2] if len(bounds) > 2 else 1

class Integer(Numeric):
    param_type_enum = ParamType.INTEGER

class IntExponential(Integer):
    param_type_enum = ParamType.INTEGER_EXP

    def __init__(self, name: str, bounds: tuple, default: int, base: int, **kwargs):
        super().__init__(name, bounds, default, transform=lambda x: base ** x, **kwargs)
        self.base = base

class Ordinal(Numeric):
    param_type_enum = ParamType.ORDINAL

class String(Param):
    param_type_enum = ParamType.STRING

class Real(Numeric):
    param_type_enum = ParamType.REAL

class Constraint:
    def __init__(self, constraint: Union[Callable[[Any], Any], str]):
        self.constraint = constraint

    @staticmethod
    def _as_dict_string(input_str: str, variable_names: list[str]) -> str:
        for var_name in sorted(variable_names, key=len, reverse=True):
            pattern = r'\b' + re.escape(var_name) + r'\b'
            replacement = f"x['{var_name}']"
            input_str = re.sub(pattern, replacement, input_str)
        return input_str

    @staticmethod
    def as_dict_lambda(input_str: str, variable_names: list[str]) -> Callable[[Any], Any]:
        return Constraint._string_as_lambda(Constraint._as_dict_string(input_str, variable_names))

    @staticmethod
    def _string_as_lambda(input_str: str) -> Callable[[Any], Any]:
        return eval(f"lambda x: ({input_str})")

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)


def string_to_param_type(param_type_str: str) -> ParamType:
    return ParamType[param_type_str.upper()]

def param_type_to_class(param_type: ParamType) -> Type[Param]:
    # Inspect all subclasses of Param to find the matching param_type_enum
    for cls in Param.__subclasses__():
        # Recursively check subclasses
        cls_queue = [cls]
        while cls_queue:
            current_cls = cls_queue.pop()
            if hasattr(current_cls, 'param_type_enum') \
                and current_cls.param_type_enum == param_type:
                return current_cls
            return cls_queue.extend(current_cls.__subclasses__())
    raise ValueError(f"No class found for ParamType {param_type}")

def class_to_param_type(param_class: Type[Param]) -> ParamType:
    # Directly return the param_type_enum class attribute
    if hasattr(param_class, 'param_type_enum'):
        return param_class.param_type_enum
    raise ValueError(f"ParamType not defined for class {param_class.__name__}")
