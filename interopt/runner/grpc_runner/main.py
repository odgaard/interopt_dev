import ast
#import grpc
import grpc.aio

import logging

# Import param enum type
from interopt.parameter import ParamType, Param


import interopt.runner.grpc_runner.config_service_pb2 as cs
import interopt.runner.grpc_runner.config_service_pb2_grpc as cs_grpc

import interopt.runner.grpc_runner.interopt_service_pb2 as ios
import interopt.runner.grpc_runner.interopt_service_pb2_grpc as ios_grpc

def value_to_param(value, param_type: ParamType):
    if param_type == ParamType.ORDINAL:
        return cs.Parameter(ordinal_param=cs.OrdinalParam(value=int(value)))

    if param_type == ParamType.REAL:
        return cs.Parameter(real_param=cs.RealParam(value=float(value)))

    if param_type in (ParamType.INTEGER, ParamType.INTEGER_EXP):
        return cs.Parameter(integer_param=cs.IntegerParam(value=int(value)))

    if param_type == ParamType.CATEGORICAL:
        return cs.Parameter(categorical_param=cs.CategoricalParam(value=int(value)))

    if param_type == ParamType.STRING:
        return cs.Parameter(string_param=cs.StringParam(value=str(value)))

    if param_type == ParamType.PERMUTATION:
        tuple_value = ast.literal_eval(value)
        return cs.Parameter(permutation_param=cs.PermutationParam(values=list(tuple_value)))
    raise ValueError(f"Unknown parameter type: {param_type}")


async def setup_study(study_name: str, problem_name: str,
                      dataset: str, enable_tabular: bool, enable_model: bool,
                      enable_download: bool, enabled_objectives: list[str],
                      server_addresses: list[str], server_port: int,
                      interopt_address: str, interopt_port: int):
    request = ios.SetupStudyRequest(
        study_name=study_name,
        problem_name=problem_name,
        dataset=dataset,
        enable_tabular=enable_tabular,
        enable_model=enable_model,
        enable_download=enable_download,
        enable_objectives=enabled_objectives,
        server_connections=[
            ios.ServerConnection(server_address=server_addresses[i], server_port=server_port) 
            for i in range(len(server_addresses))]
    )

    grpc_url = f"{interopt_address}:{interopt_port}"

    async with grpc.aio.insecure_channel(grpc_url) as channel:
        stub = ios_grpc.InteroptServiceStub(channel)
        logging.info(f"Sending request: {request}")
        response = await stub.SetupStudy(request)
        logging.info(f"Received response: {response}")
        return response


async def run_config(query_dict: dict, parameters: list[Param], grpc_url: str, study_name: str):
    parameter_names = [param.name for param in parameters]
    parameter_types = [param.param_type_enum for param in parameters]
    query_dict_list = []
    for name, value in query_dict.items():
        if name not in parameter_names:
            raise ValueError(f"Unknown parameter: {name}")
        query_dict_list.append([name, value, parameter_types[parameter_names.index(name)]])
    query_dict_grpc = {
        name: value_to_param(value, param_type)
        for name, value, param_type in query_dict_list
    }
    config = cs.Configuration(parameters=query_dict_grpc)
    result = {}

    async with grpc.aio.insecure_channel(grpc_url) as channel:
        stub = cs_grpc.ConfigurationServiceStub(channel)
        request = cs.ConfigurationRequest(
            configurations=config,
            output_data_file="",
            study_name=study_name
        )
        logging.info(f"Sending request: {request}")
        try:
            response = await stub.RunConfigurationsClientServer(request)
            logging.info(f"Received response: {response}")
            for metric in response.metrics:
                result[metric.name] = metric.values
            #print(f"Received result: {result}")
        except grpc.aio.AioRpcError as e:
            logging.info(e.with_traceback(None))
            # Extracting the status code
            status_code = e.code()
            logging.info(f"Status code: {status_code}")

            # Extracting the details
            details = e.details()
            logging.info(f"Details: {details}")

    return result
