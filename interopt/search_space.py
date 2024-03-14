from typing import Union
from interopt.parameter import Param, Constraint, string_to_param_type, param_type_to_class

class Metric:
    def __init__(self, name: str, index: int, singular: bool):
        self.name = name
        self.index = index
        self.singular = singular

    @staticmethod
    def from_dict(d: dict):
        return Metric(d['name'], d['index'], d['singular'])

class Objective:
    def __init__(self, name: str, metric: Metric, minimize: bool):
        self.name = name
        assert self.name == metric.name
        self.metric = metric
        self.minimize = minimize

    @staticmethod
    def from_dict(d: dict):
        return Objective(d['name'], d['metric'], d['minimize'])

class SearchSpace():
    def __init__(self, params: Union[list[Param], list[dict]],
                 metrics: list[Metric], objectives: list[Objective],
                 constraints: list[Constraint] = []):
        if isinstance(params[0], dict):
            self.params = [self.dict_to_param(p) for p in params]
        elif isinstance(params[0], Param):
            self.params = params
        else:
            raise ValueError("params must be a list of Param or dict")

        self.objectives = objectives
        self.constraints = constraints
        self.metrics = metrics

    @staticmethod
    def dict_to_param(param: dict) -> Param:
        cl = param_type_to_class(string_to_param_type(param['type']))
        return cl.from_dict(param)
