import grpc
import asyncio
import logging
from fastapi import FastAPI
import threading
import uvicorn
import logging.handlers

import interopt.runner.grpc_runner.config_service_pb2 as cs
import interopt.runner.grpc_runner.interopt_service_pb2 as ios
import interopt.runner.grpc_runner.interopt_service_pb2_grpc as ios_grpc

from interopt.study import Study, QueueHandler
from interopt.definition import ProblemDefinition

class InteroptServiceServicer(ios_grpc.InteroptServiceServicer):
    def __init__ (self, studies: dict[Study], problem_registry: dict[str, ProblemDefinition]):
        self.studies = studies
        self.problem_registry = problem_registry

    async def RunConfiguration(self, request, context):
        logging.info(f"Received request: {request}")
        query = await self.convert_request(request)
        # Sort the query to ensure consistent ordering
        study_name = request.study_name
        study = self.studies[study_name]

        logging.info(f"Received request for study: {study_name} with query: {query}")

        query = {name: query[name] for name in study.get_parameter_names()}
        logging.info(f"Converted request: {query}")

        result = await study.query_async(query, study_name=study_name)

        logging.info(f"Results: {result}")
        result = await self.convert_response(result, study)
        logging.info(f"Converted response: {result}")
        return result

    async def SetupStudy(self, request, context):
        queue_handler_for_servers = {}
        study_name = request.study_name
        if study_name in self.studies:
            logging.warning(f"Study with name {study_name} already exists")
            return ios.SetupStudyResponse(success=False)
        queue_handler = None
        first_server = request.server_connections[0]
        first_server_id = f"{first_server.server_address}:{first_server.server_port}"
        queue_handler = queue_handler_for_servers.get(first_server_id, None)
        for server_connection in request.server_connections:
            server_id = f"{server_connection.server_address}:{server_connection.server_port}"
            logging.info(f"Server connection: {server_id}")
            if server_id in queue_handler_for_servers:
                if queue_handler != queue_handler_for_servers.get(server_id, None):
                    logging.error("Overlapping queue handlers for the same server set")
                    return ios.SetupStudyResponse(success=False)

        if queue_handler is None:
            logging.info(f"Creating new queue handler for server: {request.server_connections}")
            server_ids = [f"{server_connection.server_address}:{server_connection.server_port}"
                          for server_connection in request.server_connections]
            queue_handler = QueueHandler(server_ids)
            for server_id in server_ids:
                queue_handler_for_servers[server_id] = queue_handler
        
        logging.info(f"Using queue handler: {queue_handler}")
        logging.info(f"Creating new study: {study_name}")
        study = Study(benchmark_name=request.problem_name, queue_handler=queue_handler,
                      enabled_objectives=[bool(obj) for obj in request.enable_objectives],
                      definition=self.problem_registry[request.problem_name],
                      study_name=study_name, enable_tabular=request.enable_tabular,
                      dataset=request.dataset, enable_model=request.enable_model,
                      server_addresses=[str(server_connection.server_address) for server_connection in request.server_connections])
        self.studies[study_name] = study
        logging.info(f"Added new study: {study_name}")
        return ios.SetupStudyResponse(success=True)

    async def Shutdown(self, request, context):
        if request.shutdown:
            logging.warning("Shutdown requested")
            # Add async shutdown logic here if necessary
            return cs.ShutdownResponse(success=True)
        return cs.ShutdownResponse(success=False)


    async def convert_request(self, request):
        query = {}
        for key, param in request.configurations.parameters.items():
            # Each parameter could be of a different type, so check and extract accordingly
            if param.HasField('integer_param'):
                query[key] = param.integer_param.value
            elif param.HasField('real_param'):
                query[key] = param.real_param.value
            elif param.HasField('string_param'):
                query[key] = param.string_param.value
            elif param.HasField('categorical_param'):
                query[key] = param.categorical_param.value
            elif param.HasField('ordinal_param'):
                query[key] = param.ordinal_param.value
            elif param.HasField('permutation_param'):
                vals = param.permutation_param.values
                query[key] = str(tuple(vals))
            # Add additional elif blocks for other parameter types as needed
        return query

    async def convert_response(self, result, study: Study):
        metrics = []
        for obj in study.enabled_objectives:
            metrics.append(ios.Metric(name=obj, values=[result[obj]]))
        return cs.ConfigurationResponse(
            metrics=metrics,
            timestamps=cs.Timestamp(timestamp=int()),
            feasible=cs.Feasible(value=True)
        )

"""
class Server():
    def __init__(self, studies: list[Study], problem_registry: dict[str, ProblemDefinition], port: int = 50050):
        self.studies = studies
        self.problem_registry = problem_registry
        self.port = port

    async def serve(self) -> None:
        server = grpc.aio.server()
        ios_grpc.add_InteroptServiceServicer_to_server(
            InteroptServiceServicer(self.studies, self.problem_registry), server)
        listen_addr = f'[::]:{self.port}'
        server.add_insecure_port(listen_addr)
        print(f'Serving on {listen_addr}')
        await server.start()
        await server.wait_for_termination()

    def start(self):
        asyncio.run(self.serve())
"""


class Server():
    def __init__(self, studies: dict[str, Study],
                 problem_registry: dict[str, ProblemDefinition],
                 grpc_port: int = 50050, api_port: int = 8000):
        self.studies = studies
        self.problem_registry = problem_registry
        self.grpc_port = grpc_port
        self.api_port = api_port
        self.service = InteroptServiceServicer(studies, problem_registry)
        self.app = FastAPI()
        self.setup_routes()

    def setup_routes(self):
        @self.app.get("/studies/")
        async def read_studies():
            return {
                name: {
                    "benchmark_name": study.benchmark_name,
                    "study_name": name,
                    "dataset": study.dataset,
                    "enable_tabular": study.enable_tabular,
                    "enable_model": study.enable_model,
                    "server_addresses": study.server_addresses,
                    "enabled_objectives": study.enabled_objectives,
                }
                for name, study in self.service.studies.items()
            }

        @self.app.get("/problems/")
        async def get_problems():
            # This will return all problems in the registry
            return self.problem_registry

        @self.app.get("/problems/{problem_name}", response_model=ProblemDefinition)
        async def get_problem(problem_name: str):
            # This will return a specific problem by name
            problem = self.problem_registry.get(problem_name)
            if problem:
                return problem
            return {"error": "Problem not found"}

    async def serve_grpc(self):
        server = grpc.aio.server()
        ios_grpc.add_InteroptServiceServicer_to_server(self.service, server)
        listen_addr = f'[::]:{self.grpc_port}'
        server.add_insecure_port(listen_addr)
        logging.info(f'Serving gRPC on {listen_addr}')
        await server.start()
        await server.wait_for_termination()

    def serve_api(self):
        uvicorn.run(self.app, host="0.0.0.0", port=self.api_port)

    def start(self):
        # Run the gRPC server in a separate thread to not block
        threading.Thread(target=asyncio.run, args=(self.serve_grpc(),)).start()
        logging.info(f'Serving API on http://0.0.0.0:{self.api_port}')
        self.serve_api()



# Example usage
if __name__ == "__main__":
    studies = {}  # Populate your studies dictionary
    problem_registry = {}  # Populate your problem registry
    logging.info("Starting server")
    server = Server(studies, problem_registry)
    server.start()
