import os
import ast
import requests
import asyncio

from typing import Optional
from enum import Enum, auto

import pandas as pd
import numpy as np

from interopt.runner.grpc_runner import run_config
from interopt.runner.model import load_models
from interopt.definition import ProblemDefinition

class TabularDataset:
    def __init__(self, benchmark_name, dataset, parameter_names, objectives, enable_download):
        self.objectives = objectives
        self.tab = None
        self.parameter_names = parameter_names
        self.tab_path = f'datasets/{benchmark_name}_{dataset}.csv'
        if os.path.exists(self.tab_path):
            self.tab = pd.read_csv(self.tab_path).dropna()
        elif enable_download:
            success = self.ensure_dataset_downloaded(benchmark_name, dataset)
            if success:
                self.tab = pd.read_csv(self.tab_path).dropna()
                print(self.tab)
        if self.tab is None:
            multi_index = pd.MultiIndex.from_tuples([], names=self.parameter_names)
            self.tab = pd.DataFrame(columns=parameter_names + objectives, index=multi_index)
        else:
            self.tab.set_index(parameter_names, inplace=True)
            self.tab.sort_index(inplace=True)
        #self.load_and_prepare_dataset(parameter_names)
        self.query_tab = self.tab.copy()

    #def load_and_prepare_dataset(self, parameter_names):
        #self.tab['energy_consumptions'] = self.tab['energy_consumptions'].apply(
        #    ast.literal_eval)
        #self.tab['energy'] = self.tab['energy_consumptions'].apply(
        #    lambda x: sum(x)/len(x) if len(x) > 0 else 0)
        # Set the index for the query_tab, modify as needed for each benchmark


    def ensure_dataset_downloaded(self, benchmark_name, dataset):
        filename = f"{benchmark_name}_{dataset}.csv"
        url = f"https://raw.githubusercontent.com/odgaard/bacobench_data/main/{filename}"  # URL of the file on Github
        #url = f'http://bacobench.s3.amazonaws.com/{filename}'  # URL of the file in S3
        if not os.path.exists('datasets'):
            os.mkdir('datasets')
        file_path = f'datasets/{filename}'
        success = True
        if not os.path.exists(file_path):
            success = TabularDataset.download_file(url, file_path)
        return success

    @staticmethod
    def download_file(url, local_file_path):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Will raise an exception for 4XX/5XX errors
            with open(local_file_path, 'wb') as f:
                f.write(response.content)
            print(f"Downloaded {local_file_path}")
            return True
        except requests.exceptions.HTTPError as e:
            print(f"Failed to download {url}: {e}")
            return False

    def query(self, query_dict) -> Optional[pd.Series]:
        query_tuple = tuple(query_dict[col] for col in self.query_tab.index.names)
        if query_tuple in self.query_tab.index:
            print("Using tabular data")
            query_result: pd.Series = self.query_tab.loc[query_tuple][self.objectives]
            return query_result
        #print("Query not found in tabular data")
        return None

    def write(self, result):
        # Check if the CSV file exists
        file_exists = os.path.isfile(self.tab_path)

        # If file exists, append without header; otherwise, write with header
        write_result = result.reset_index()
        if file_exists:
            write_result.to_csv(self.tab_path, mode='a', sep=",",
                          index=False, header=False)
        else:
            write_result.to_csv(self.tab_path, mode='w', sep=",",
                          index=False, header=True)

    def add(self, result):
        self.write(result)
        self.query_tab = pd.concat([self.query_tab, result])




class SoftwareQuery:
    def __init__(self, benchmark_name, dataset, parameter_names, enabled_objectives,
                 enable_tabular, enable_model, enable_download):
        self.tabular_dataset = TabularDataset(
            benchmark_name, dataset, parameter_names, enabled_objectives, enable_download)
        if enable_model:
            self.models = load_models(
                self.tabular_dataset.query_tab, benchmark_name, dataset,
                enabled_objectives, parameter_names)
        self.query_tab = self.tabular_dataset.query_tab
        self.enable_tabular = enable_tabular
        self.enable_model = enable_model
        #print(f"Enable tabular: {enable_tabular}")
        #print(f"Enable model: {enable_model}")

    def get_objectives(self):
        return self.tabular_dataset.objectives

    async def query_software(self, query_dict: dict) -> Optional[pd.DataFrame]:
        # Use the tabular data, query is available in the table
        query_result = pd.DataFrame()
        #print(f"Query: {query_dict}, {self.enable_tabular}, {self.enable_model}")
        if self.enable_tabular:
            query_result = self.tabular_dataset.query(query_dict)
            #print(f"Query result: {query_result}")
        if query_result is None and self.enable_model:
            # Use surrogate model, query is not available in the table
            query_result: pd.Series = self.query_model(query_dict)
            #print(f"Query result: {query_result}")

        if query_result is not None:
            #return query_result.to_frame().T
            return query_result

        return None

    def query_model(self, query_dict) -> pd.Series:
        model_query_dict = self.convert_permutation_to_tuple(query_dict, 'permutation')

        print("Using surrogate model")
        results = [self.models[objective].predict(pd.DataFrame([model_query_dict]))[0]
                   for objective in self.get_objectives()]

        # Convert from log scale back to normal
        results = [np.exp(result) for result in results]

        return pd.DataFrame([results], columns=self.get_objectives(),
                          index=[tuple(query_dict.values())]).iloc[0]

    def convert_permutation_to_tuple(self, query_dict: dict, param: str) -> list[int]:
        new_dict = query_dict.copy()
        tuple_str = ast.literal_eval(new_dict[param])
        for i, value in enumerate(tuple_str):
            new_dict[f'tuple_{param}_{i}'] = value
        del new_dict[param]
        return new_dict


class OperationMode(Enum):
    CLIENT = auto()
    INTEROP_SERVER = auto()

class QueueHandler:
    def __init__(self, grpc_urls: list[str]):
        self.grpc_urls = grpc_urls
        self.queue = asyncio.Queue()
        self.server_availability = {url: True for url in self.grpc_urls}
        self.available_server_event = asyncio.Event()
        self.available_server_event.set()
        self.lock = asyncio.Lock()

    async def get_available_server_url(self):
        while True:
            async with self.lock:
                for url, is_available in self.server_availability.items():
                    if is_available:
                        self.server_availability[url] = False  # Mark the server as busy
                        if not any(self.server_availability.values()): # Check if all servers are now busy
                            self.available_server_event.clear()  # Clear the event to wait again
                        return url # If no available servers found, wait for one to become available
            await self.available_server_event.wait()

    async def mark_server_as_available(self, url):
        async with self.lock:
            self.server_availability[url] = True
            self.available_server_event.set()  # Signal that at least one server is available

class GRPCQuery:
    def __init__(self, grpc_urls, parameters,
                 enabled_objectives, definition: ProblemDefinition):
        self.parameters = parameters
        self.enabled_objectives = enabled_objectives
        self.definition = definition
        self.queue_handler = QueueHandler(grpc_urls)

    async def send_queries_to_servers(self, query: dict) -> dict:
        return await self.send_query(query)

    async def send_query(self, query: dict) -> dict:
        url = await self.queue_handler.get_available_server_url()
        try:
            #print(f"Sending query to {url}")
            result = await run_config(query, self.parameters, url)
            return result
        finally:
            await self.queue_handler.mark_server_as_available(url)

    async def query_hardware(self, query: dict) -> pd.DataFrame:
        # Implement or override as needed
        result = await self.send_queries_to_servers(query)
        result = await self.process_grpc_results(result, query)
        return result

    async def process_grpc_results(self, result: dict, query: dict) -> pd.DataFrame:
        # Create a MultiIndex with names
        index_tuples = [tuple(query.values())]  # This will be a list of tuples

        if len(result) == 0:
            # Creating a MultiIndex without rows initially
            multi_index = pd.MultiIndex.from_tuples([], names=list(query.keys()))

            # Creating an empty DataFrame with a MultiIndex and specific columns
            return pd.DataFrame(columns=self.enabled_objectives, index=multi_index)

        values = [result[e][0] for e in self.enabled_objectives]
        multi_index = pd.MultiIndex.from_tuples(index_tuples, names=list(query.keys()))
        return pd.DataFrame([values], columns=self.enabled_objectives, index=multi_index)

class Study():
    tab = None
    query_tab = None
    models = None

    def __init__(self, benchmark_name: str, definition: ProblemDefinition,
                 enable_tabular: bool, dataset, enabled_objectives: list[str],
                 server_addresses: list[str] = ["localhost"], port=50051, url="",
                 enable_model: bool = True, enable_download: bool = True):
        self.benchmark_name = benchmark_name
        #self.grpc_urls = [f"{server_address}:{port}" if url == "" else url]
        self.grpc_urls = [f"{server_address}:{port}" for server_address in server_addresses]
        self.enabled_objectives = enabled_objectives
        self.enable_tabular = enable_tabular
        self.enable_model = enable_model
        self.dataset = dataset
        self.definition = definition
        self.parameters = definition.search_space.params
        self.port = port

        if self.enable_tabular or self.enable_model:
            self.software_query = SoftwareQuery(
                benchmark_name, dataset, self.get_parameter_names(),
                enabled_objectives=self.enabled_objectives,
                enable_tabular=self.enable_tabular, enable_model=self.enable_model,
                enable_download=enable_download)
        else:
            self.software_query = None
        self.grpc_query = GRPCQuery(self.grpc_urls, self.parameters,
                                    self.enabled_objectives, self.definition)

    def set_tabular(self, enable_tabular: bool):
        self.enable_tabular = enable_tabular

    def get_enabled_objectives(self):
        return self.enabled_objectives

    def query(self, query: dict) -> dict:
        res = asyncio.run(self.query_async(query))
        ret = {}
        for k in self.enabled_objectives:
            ret[k] = res[k]
        return ret

    async def query_async(self, query: dict) -> list[dict]:
        return await self.query_choice(query)

    async def query_choice(self, query: dict) -> dict:
        result = None
        if self.enable_tabular:
            result = await self.software_query.query_software(query.copy())
            if isinstance(result, pd.Series):
                result = result.to_frame().T
        if result is None:
            result = await self.grpc_query.query_hardware(query.copy())

            self.software_query.tabular_dataset.add(result)

        return result.iloc[0].to_dict()


    def get_parameter_names(self):
        return [param.name for param in self.parameters]

    def get_parameter_types(self):
        return [param.param_type_enum for param in self.parameters]

    def get_default_config(self):
        return {param.name: param.default for param in self.parameters}
