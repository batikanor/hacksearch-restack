import os
import asyncio
import random

from .observability import log_with_context

from .playground.workflow import PlaygroundInput, playgroundRun
from .restack import CloudConnectionOptions, Restack, ServiceOptions


async def main():
    try:
        # Fetch environment variables
        engine_id = os.environ.get("RESTACK_ENGINE_ID")
        address = os.environ.get("RESTACK_ENGINE_ADDRESS")
        api_key = os.environ.get("RESTACK_ENGINE_API_KEY")

        # Create connection options only if all environment variables are set

        connection_options = CloudConnectionOptions(
            engine_id=engine_id,
            address=address,
            api_key=api_key,
        )

        restack = Restack(connection_options)

        log_with_context("INFO", "restackClient", restack=restack)
        await restack.schedule_workflow(
            workflow_name="playgroundRun",
            workflow_id=f"{random.randint(0, 1000000)}-local-test-1",
            input=PlaygroundInput(functionName="testRun", taskQueue="restack"),
            # event=WorkflowEvent(name="test_event", input={"content": "test"})
        )

        log_with_context("INFO", "Scheduling workflow")

        await restack.start_service(
            workflows=[playgroundRun], options=ServiceOptions(endpoints=True)
        )

        log_with_context("INFO", "Services running successfully.")
    except Exception as e:
        log_with_context("ERROR", "Failed to run services", error=str(e))


def run_test():
    asyncio.run(main())


if __name__ == "__main__":
    run_test()
