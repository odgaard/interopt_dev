import grpc
import asyncio
import logging

import interopt.runner.grpc_runner.config_service_pb2 as cs
import interopt.runner.grpc_runner.config_service_pb2_grpc as cs_grpc

from interopt.study import Study

# Configure logging
#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class ConfigurationServiceServicer(cs_grpc.ConfigurationServiceServicer):
    def __init__ (self, study: Study):
        self.study = study

    async def RunConfigurationsClientServer(self, request, context):
        logging.info(f"Received request: {request}")
        query = await self.convert_request(request)
        # Sort the query to ensure consistent ordering
        parameter_names = self.study.get_parameter_names()
        query = {name: query[name] for name in parameter_names}
        logging.info(f"Converted request: {query}")

        result = await self.study.query_async(query)

        logging.info(f"Results: {result}")
        result = await self.convert_response(result)
        logging.info(f"Converted response: {result}")
        return result

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

    async def convert_response(self, result):
        metrics = []
        for obj in self.study.enabled_objectives:
            metrics.append(cs.Metric(name=obj, values=[result[obj]]))
        return cs.ConfigurationResponse(
            metrics=metrics,
            timestamps=cs.Timestamp(timestamp=int()),
            feasible=cs.Feasible(value=True)
        )

class Server():
    def __init__(self, study: Study, port: int = 50050):
        self.study = study
        self.port = port

    async def serve(self) -> None:
        server = grpc.aio.server()
        cs_grpc.add_ConfigurationServiceServicer_to_server(
            ConfigurationServiceServicer(self.study), server)
        listen_addr = f'[::]:{self.port}'
        server.add_insecure_port(listen_addr)
        print(f'Serving on {listen_addr}')
        await server.start()
        await server.wait_for_termination()

    def start(self):
        asyncio.run(self.serve())
