import os
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from .event import AgentEvent
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleCalendarSpec,
    ScheduleIntervalSpec,
    ScheduleRange,
    WithStartWorkflowOperation,
)
from temporalio.common import (
    SearchAttributePair,
    SearchAttributeKey,
    TypedSearchAttributes,
    WorkflowIDConflictPolicy,
)
from temporalio.worker import Worker
from dataclasses import dataclass

from .playground.workflow import playgroundRun
from .observability import log_with_context
from .security import DataConverter
from .pydantic import pydantic_data_converter
from .endpoints import explore_class_details

__all__ = ["ScheduleCalendarSpec", "ScheduleIntervalSpec", "ScheduleRange"]


@dataclass
class CloudConnectionOptions:
    engine_id: str
    api_key: str
    address: Optional[str] = "localhost:7233"
    api_address: Optional[str] = None
    temporal_namespace: Optional[str] = "default"
    data_converter: Optional[DataConverter] = None


@dataclass
class ServiceOptions:
    rate_limit: Optional[int] = 100000
    max_concurrent_workflow_runs: Optional[int] = 3000
    max_concurrent_function_runs: Optional[int] = 1000
    endpoints: Optional[bool] = True


class Restack:
    api_key: Optional[str] = None
    client: Optional[Client] = None
    options: Optional[CloudConnectionOptions] = None
    functions: Optional[List[Any]] = None

    def __init__(self, options: Optional[CloudConnectionOptions] = None):
        super().__init__()
        self.client = None
        self.options = options

    def get_connection_options(self) -> Dict[str, Any]:
        target_host = (
            self.options.address
            if self.options and self.options.address is not None
            else "localhost:7233"
        )
        api_address = (
            f"https://{self.options.api_address}"
            if self.options and self.options.api_address is not None
            else "http://localhost:6233"
        )
        engine_id = (
            self.options.engine_id
            if self.options and self.options.engine_id is not None
            else "local"
        )
        options = {
            "target_host": target_host,
            "metadata": {
                "restack-engineId": engine_id,
                "restack-apiAddress": api_address,
            },
        }
        if self.options and self.options.api_key is not None:
            options["tls"] = True
            options["api_key"] = self.options.api_key
        return options

    async def connect(
        self, connection_options: Optional[CloudConnectionOptions] = None
    ):
        if self.client:
            log_with_context("INFO", "Reusing existing client connection")
            return
        try:
            self.client = await self.create_client(connection_options)
            log_with_context("INFO", "Connected to Restack Engine")
        except Exception as e:
            log_with_context(
                "ERROR", "Failed to connect to Restack Engine", error=str(e)
            )
            raise e

    async def create_client(
        self, connection_options: Optional[CloudConnectionOptions] = None
    ) -> Client:
        connect_options = connection_options or self.get_connection_options()

        target_host = connect_options["target_host"]
        namespace = (
            self.options.temporal_namespace
            if self.options and self.options.temporal_namespace is not None
            else "default"
        )
        api_key = (
            self.options.api_key
            if self.options and self.options.api_key is not None
            else None
        )
        tls = True if self.options and self.options.api_key is not None else False
        metadata = connect_options["metadata"]
        data_converter = (
            self.options.data_converter
            if self.options and self.options.data_converter is not None
            else pydantic_data_converter
        )
        try:
            client = await Client.connect(
                target_host,
                namespace=namespace,
                api_key=api_key,
                tls=tls,
                rpc_metadata=metadata,
                data_converter=data_converter,
            )
        except Exception as e:
            documentation_url = "https://docs.restack.io/help/troubleshooting#restack-is-not-running"
            log_with_context(
                "ERROR",
                (
                    "Failed to connect, make sure Restack is running: " + documentation_url
                ),
                error=str(e),
            )
            raise e
        return client

    async def create_service(
        self,
        workflows: Optional[List[Any]] = None,
        agents: Optional[List[Any]] = None,
        functions: Optional[List[Any]] = None,
        task_queue: Optional[str] = None,
        options: Optional[ServiceOptions] = None,
    ) -> Worker:
        try:
            log_with_context("INFO", "Starting service...")
            client = await self.create_client()
            engine_id = self.get_connection_options()["metadata"]["restack-engineId"]
            api_address = self.get_connection_options()["metadata"][
                "restack-apiAddress"
            ]
            identity = f"{engine_id}-{task_queue or 'restack'}-{os.getpid()}"
            task_queue = f"{engine_id}-{task_queue or 'restack'}"

            all_workflows = (workflows or []) + (agents or [])
            service = Worker(
                identity=identity,
                client=client,
                task_queue=task_queue,
                workflows=all_workflows,
                activities=functions or [],
                max_task_queue_activities_per_second=options.rate_limit,
                max_concurrent_activities=options.max_concurrent_function_runs,
                max_concurrent_workflow_tasks=options.max_concurrent_workflow_runs,
            )
            log_with_context("INFO", "Service created successfully")

            if options.endpoints:
                log_with_context("INFO", "Creating endpoints...")
                async with aiohttp.ClientSession() as session:
                    workflow_details = []
                    for workflow in workflows or []:
                        details = explore_class_details(workflow)
                        details["taskQueue"] = task_queue
                        workflow_details.append(details)

                    agent_details = []
                    for agent in agents or []:
                        details = explore_class_details(agent)
                        details["taskQueue"] = task_queue
                        agent_details.append(details)

                    endpoints_payload = {
                        "identity": identity,
                        "workflows": workflow_details,
                        "agents": agent_details,
                    }
                    # log_with_context("DEBUG", "Registering endpoints", workflows=workflows, functions=functions, endpoints_payload=endpoints_payload)

                    try:
                        async with session.post(
                            f"{api_address}/api/engine/endpoints",
                            json=endpoints_payload,
                        ) as response:
                            response_text = await response.text()
                            log_with_context("INFO", f"{response_text}")
                    except Exception as e:
                        log_with_context(
                            "WARNING", "Failed to register endpoints", error=str(e)
                        )
            return service
        except Exception as e:
            if (
                e.__cause__
                and "http.client.incompleteread.__mro_entries__".lower()
                in str(e.__cause__).lower()
            ):
                log_with_context(
                    "ERROR",
                    "Failed to start service: Functions in workflow or agents steps need to be imported with import_functions(). See docs at https://docs.restack.io/libraries/python/workflows",
                )
            else:
                log_with_context("ERROR", "Failed to start service", error=str(e))
            raise e

    async def run_service(self, service: Worker):
        try:
            engine_id = self.get_connection_options()["metadata"]["restack-engineId"]

            if service.task_queue.endswith("restack"):
                log_with_context("INFO", "Creating playground service...")

                playground_service = Worker(
                    identity=f"{engine_id}-playground-{os.getpid()}",
                    client=service.client,
                    task_queue=f"{engine_id}-playground",
                    workflows=[playgroundRun],
                )

                log_with_context(
                    "INFO", "Services ready to receive workflows and events"
                )
                await asyncio.gather(service.run(), playground_service.run())
            else:
                log_with_context(
                    "INFO", "Service ready to receive workflows and events"
                )
                await service.run()
        except Exception as e:
            log_with_context("ERROR", "Failed to run service", error=str(e))
            raise e

    async def start_service(
        self,
        workflows: Optional[List[Any]] = None,
        agents: Optional[List[Any]] = None,
        functions: Optional[List[Any]] = None,
        task_queue: Optional[str] = None,
        options: Optional[ServiceOptions] = None,
    ):
        """
        Start a service with the specified configurations.

        Parameters:
        - workflows (Optional[List[Any]]): A list of workflows to be used.
        - agents (Optional[List[Any]]): A list of agents to be used.
        - functions (Optional[List[Any]]): A list of functions to be used.
        - task_queue (Optional[str]): The task queue name.
        - options (Optional[ServiceOptions]): Service options for rate limiting and concurrency.
        """
        service = await self.create_service(
            task_queue=task_queue,
            workflows=workflows,
            agents=agents,
            functions=functions or [],
            options=options or ServiceOptions(),
        )
        await self.run_service(service)

    async def schedule_workflow(
        self,
        workflow_name: str,
        workflow_id: str,
        input: Optional[Dict[str, Any]] = None,
        schedule: Optional[ScheduleSpec] = None,
        task_queue: Optional[str] = "restack",
        event: Optional[AgentEvent] = None,
        is_agent: Optional[bool] = False,
    ) -> str:
        await self.connect()
        if self.client:
            try:
                connection_options = self.get_connection_options()
                engine_id = connection_options["metadata"]["restack-engineId"]

                search_attribute_pairs = [
                    SearchAttributePair(
                        key=SearchAttributeKey.for_text("engineId"), value=engine_id
                    )
                ]
                search_attributes = TypedSearchAttributes(
                    search_attributes=search_attribute_pairs
                )

                if not schedule:
                    if event:
                        start_op = WithStartWorkflowOperation(
                            workflow_name,
                            id=f"{engine_id}-{workflow_id}",
                            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                            args=[input] if input else [],
                            task_queue=f"{engine_id}-{task_queue}",
                            memo={"engineId": engine_id, "agent": is_agent},
                            search_attributes=search_attributes,
                        )
                        try:
                            await self.client.execute_update_with_start_workflow(
                                update=event.name,
                                args=[event.input],
                                start_workflow_operation=start_op,
                            )
                            handle = await start_op.workflow_handle()
                            log_with_context(
                                "INFO", "Workflow started with event", handle=handle
                            )
                            return handle.first_execution_run_id
                        except Exception as e:
                            log_with_context(
                                "ERROR",
                                "Failed to start workflow with event",
                                error=str(e),
                            )
                            raise e
                    else:
                        handle = await self.client.start_workflow(
                            workflow_name,
                            args=[input] if input else [],
                            id=f"{engine_id}-{workflow_id}",
                            memo={"engineId": engine_id},
                            search_attributes=search_attributes,
                            task_queue=f"{engine_id}-{task_queue}",
                        )
                    return handle.first_execution_run_id
                else:
                    schedule_action = ScheduleActionStartWorkflow(
                        workflow=workflow_name,
                        args=[input] if input else [],
                        id=f"{engine_id}-{workflow_id}",
                        task_queue=f"{engine_id}-{task_queue}",
                        memo={"engineId": engine_id},
                        typed_search_attributes=search_attributes,
                    )
                    schedule_obj = Schedule(
                        action=schedule_action,
                        spec=schedule,
                    )
                    scheduled = await self.client.create_schedule(
                        id=f"{engine_id}-{workflow_id}",
                        schedule=schedule_obj,
                        memo={"engineId": engine_id},
                        search_attributes=search_attributes,
                    )
                    return scheduled.id

            except Exception as e:
                log_with_context(
                    "ERROR", "Failed to start or schedule workflow", error=str(e)
                )
                raise e
        else:
            raise Exception("Workflow result not retrieved due to failed connection.")

    async def get_workflow_handle(self, workflow_id: str, run_id: str):
        await self.connect()
        if self.client:
            try:
                connection_options = self.get_connection_options()
                engine_id = connection_options["metadata"]["restack-engineId"]
                return self.client.get_workflow_handle(
                    f"{engine_id}-{workflow_id}", run_id=run_id
                )
            except Exception as e:
                log_with_context("ERROR", "Failed to get workflow result", error=str(e))
                raise e
        else:
            raise Exception("Workflow result not retrieved due to failed connection.")

    async def get_workflow_result(self, workflow_id: str, run_id: str) -> Any:
        handle = await self.get_workflow_handle(workflow_id, run_id)
        try:
            return await handle.result()
        except Exception as e:
            log_with_context("ERROR", "Failed to get workflow result", error=str(e))
            raise e

    async def schedule_agent(
        self,
        agent_name: str,
        agent_id: str,
        input: Optional[Dict[str, Any]] = None,
        schedule: Optional[ScheduleSpec] = None,
        task_queue: Optional[str] = "restack",
        event: Optional[AgentEvent] = None,
    ) -> str:
        return await self.schedule_workflow(
            agent_name, agent_id, input, schedule, task_queue, event, is_agent=True
        )

    async def get_agent_handle(self, agent_id: str, run_id: str):
        return await self.get_workflow_handle(agent_id, run_id)

    async def get_agent_result(self, agent_id: str, run_id: str) -> Any:
        return await self.get_workflow_result(agent_id, run_id)

    async def get_agent_state(
        self, agent_id: str, run_id: str, state_name: str
    ) -> Any:
        handle = await self.get_workflow_handle(agent_id, run_id)
        try:
            return await handle.query(state_name)
        except Exception as e:
            log_with_context("ERROR", "Failed to get agent state", error=str(e))
            raise e

    async def send_agent_event(
        self,
        event_name: str,
        agent_id: str,
        run_id: Optional[str] = None,
        event_input: Optional[Dict[str, Any]] = None,
    ):
        handle = await self.get_workflow_handle(agent_id, run_id)
        try:
            return await handle.execute_update(event_name, event_input)
        except Exception as e:
            log_with_context("ERROR", "Failed to send agent event", error=str(e))
            raise e
