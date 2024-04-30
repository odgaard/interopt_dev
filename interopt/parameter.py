from enum import Enum
from typing import Any, Union, Type, Callable
import re
from pydantic import BaseModel, Field, validator

class Configuration(BaseModel):
    parameters: dict

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

class Param(BaseModel):
    name: str
    default: Any
    param_type_enum: ParamType = Field(None, exclude=True)

    @validator('param_type_enum', pre=True, always=True)
    def set_param_type_enum(cls, v):
        return cls.__fields__['param_type_enum'].default

class Categorical(Param):
    param_type_enum = ParamType.CATEGORICAL
    categories: list

class Permutation(Param):
    param_type_enum = ParamType.PERMUTATION
    length: int

class Boolean(Param):
    param_type_enum = ParamType.BOOLEAN

class Numeric(Param):
    param_type_enum = ParamType.NUMERIC
    bounds: tuple
    transform: Callable[[Any], Any] = lambda x: x

    @validator('bounds')
    def set_bounds(cls, v):
        if len(v) < 2:
            raise ValueError('Bounds must have at least 2 elements')
        return v

class Integer(Numeric):
    param_type_enum = ParamType.INTEGER

class IntExponential(Integer):
    param_type_enum = ParamType.INTEGER_EXP
    base: int

class Ordinal(Numeric):
    param_type_enum = ParamType.ORDINAL

class String(Param):
    param_type_enum = ParamType.STRING

class Real(Numeric):
    param_type_enum = ParamType.REAL

class Constraint(BaseModel):
    constraint: Union[Callable[[Any], Any], str]
    #dependent_params: list[str]

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

    def direct_eval(self, x: dict) -> bool:
        return eval(self.constraint, {}, x)

    def __call__(self, x: dict) -> bool:
        return self.direct_eval(x)


def string_to_param_type(param_type_str: str) -> ParamType:
    return ParamType[param_type_str.upper()]

def param_type_to_class(param_type: ParamType) -> Type[Param]:
    for cls in Param.__subclasses__():
        if cls.__fields__['param_type_enum'].default == param_type:
            return cls
    raise ValueError(f"No class found for ParamType {param_type}")

def class_to_param_type(param_class: Type[Param]) -> ParamType:
    return param_class.__fields__['param_type_enum'].default