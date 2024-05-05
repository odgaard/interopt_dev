from typing import Union
from pydantic import BaseModel
from interopt.parameter import Constraint, Categorical, Permutation, Boolean, Numeric, Integer, IntExponential, Ordinal, String, Real

class Metric(BaseModel):
    name: str
    index: int
    singular: bool

class Objective(BaseModel):
    name: str
    metric: Metric
    minimize: bool

class SearchSpace(BaseModel):
    params: list[Union[Categorical, Permutation, Boolean,
                       Numeric, Integer, IntExponential,
                       Ordinal, String, Real]]
    metrics: list[Metric]
    objectives: list[Objective]
    constraints: list[Constraint]
