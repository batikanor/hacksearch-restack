from datetime import timedelta
from typing import Any, Dict, Optional
from .workflow import WorkflowLogger
from temporalio import workflow as temporal_workflow
from temporalio.workflow import ChildWorkflowCancellationType, ParentClosePolicy
from temporalio.common import RetryPolicy
import asyncio

log = WorkflowLogger()

get_external_agent_handle = temporal_workflow.get_external_workflow_handle
agent_info = temporal_workflow.info
continue_as_new = temporal_workflow.continue_as_new
condition = temporal_workflow.wait_condition
import_functions = temporal_workflow.unsafe.imports_passed_through
uuid = temporal_workflow.uuid4

__all__ = [
    "get_external_agent_handle",
    "agent_info",
    "continue_as_new",
    "condition",
    "import_functions",
    "log",
    "uuid",
    "RetryPolicy",
]


class Agent:
    def defn(self, *args, **kwargs):
        return temporal_workflow.defn(*args, **kwargs, sandboxed=False)

    def state(self, fn, name: str = None, description: str = None):
        return temporal_workflow.query(fn, name=name, description=description)

    def event(self, fn, name: str = None, description: str = None):
        return temporal_workflow.update(fn, name=name, description=description)

    def run(self, fn):
        return temporal_workflow.run(fn)

    def condition(self, fn, timeout: timedelta = None):
        return temporal_workflow.wait_condition(fn, timeout=timeout)

    async def step(
        self,
        activity,
        *args,
        task_queue: Optional[str] = "restack",
        schedule_to_close_timeout: Optional[timedelta] = timedelta(minutes=2),
        retry_policy: Optional[RetryPolicy] = None,
        **kwargs,
    ):
        engine_id = self.get_engine_id_from_client()
        input_arg = kwargs.pop("input", None)
        if input_arg is not None:
            args = (*args, input_arg)
        return await temporal_workflow.execute_activity(
            activity,
            *args,
            task_queue=f"{engine_id}-{task_queue}",
            schedule_to_close_timeout=schedule_to_close_timeout,
            retry_policy=retry_policy,
            **kwargs,
        )

    async def child_start(
        self,
        workflow: Optional[Any] = None,
        workflow_id: Optional[str] = None,
        agent: Optional[Any] = None,
        agent_id: Optional[str] = None,
        input: Optional[Dict[str, Any]] = None,
        task_queue: Optional[str] = "restack",
        cancellation_type: ChildWorkflowCancellationType = ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
        parent_close_policy: ParentClosePolicy = ParentClosePolicy.TERMINATE,
        execution_timeout: Optional[timedelta] = None,
    ):
        
        if not workflow and not agent:
            raise ValueError("Either workflow or agent must be provided.")
        
        if workflow and agent:
            raise ValueError("Either workflow or agent must be provided, but not both.")

        engine_id = self.get_engine_id_from_client()

        return await temporal_workflow.start_child_workflow(
            workflow=workflow.run or agent.run,
            args=[input] if input else [],
            id=self.add_engine_id_prefix(engine_id, workflow_id or agent_id),
            task_queue=f"{engine_id}-{task_queue}",
            memo={"engineId": engine_id},
            search_attributes={"engineId": [engine_id]},
            cancellation_type=cancellation_type,
            parent_close_policy=parent_close_policy,
            execution_timeout=execution_timeout,
        )

    async def child_execute(
        self,
        workflow: Optional[Any] = None,
        workflow_id: Optional[str] = None,
        agent: Optional[Any] = None,
        agent_id: Optional[str] = None,
        input: Optional[Dict[str, Any]] = None,
        task_queue: Optional[str] = "restack",
        cancellation_type: ChildWorkflowCancellationType = ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
        parent_close_policy: ParentClosePolicy = ParentClosePolicy.TERMINATE,
        execution_timeout: Optional[timedelta] = None,
    ):
        
        if not workflow and not agent:
            raise ValueError("Either workflow or agent must be provided.")
        
        if workflow and agent:
            raise ValueError("Either workflow or agent must be provided, but not both.")

        engine_id = self.get_engine_id_from_client()

        return await temporal_workflow.execute_child_workflow(
            workflow=workflow.run or agent.run,
            args=[input] if input else [],
            id=self.add_engine_id_prefix(engine_id, workflow_id or agent_id),
            task_queue=f"{engine_id}-{task_queue}",
            memo={"engineId": engine_id},
            search_attributes={"engineId": [engine_id]},
            cancellation_type=cancellation_type,
            parent_close_policy=parent_close_policy,
            execution_timeout=execution_timeout,
        )

    async def sleep(self, seconds: int):
        return await asyncio.sleep(seconds)

    def get_engine_id_from_client(self):
        engineId = temporal_workflow.memo_value("engineId", "local")
        # log_with_context("INFO", "engineId", engineId=engineId)
        return engineId

    def add_engine_id_prefix(self, engine_id, agent_id):
        if agent_id.startswith(f"{engine_id}-"):
            return agent_id
        return f"{engine_id}-{agent_id}"


agent = Agent()
