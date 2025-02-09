from temporalio import activity
from temporalio.exceptions import ApplicationError
from typing import Any
from .observability import logger, log_with_context
import websockets

activity.logger.logger = logger


class ActivityLogger:
    """Wrapper for activity logger that ensures proper context and formatting"""

    def __init__(self):
        self._logger = activity.logger

    def _log(self, level: str, message: str, **kwargs: Any):
        try:
            activity.info()
            getattr(self._logger, level)(
                message, extra={"extra_fields": {**kwargs, "client_log": True}}
            )
        except RuntimeError:
            log_with_context(level.upper(), message, **kwargs)

    def debug(self, message: str, **kwargs: Any):
        self._log("debug", message, **kwargs)

    def info(self, message: str, **kwargs: Any):
        self._log("info", message, **kwargs)

    def warning(self, message: str, **kwargs: Any):
        self._log("warning", message, **kwargs)

    def error(self, message: str, **kwargs: Any):
        self._log("error", message, **kwargs)

    def critical(self, message: str, **kwargs: Any):
        self._log("critical", message, **kwargs)


log = ActivityLogger()

FunctionFailure = ApplicationError
function_info = activity.info
heartbeat = activity.heartbeat
function = activity

__all__ = [
    "FunctionFailure",
    "log",
    "function_info",
    "heartbeat",
]


def current_workflow():
    return activity.Context.current().info


async def stream_to_websocket(api_address: str, data: Any):
    """
    Stream data to Restack Engine WebSocket API endpoint.

    Parameters:
    - api_address: The address of the Restack Engine API.
    - data: The streamed data from OpenAI compatible API or a JSON dict.

    Returns:
    - The final combined response as a string.
    """

    info = {
        "activityId": activity.info().activity_id,
        "workflowId": activity.info().workflow_id,
        "runId": activity.info().workflow_run_id,
        "activityType": activity.info().activity_type,
        "taskQueue": activity.info().task_queue,
    }

    websocket_url = f"wss://{api_address}/stream/ws/workflow/history?workflowId={info['workflowId']}&runId={info['runId']}"

    try:
        async with websockets.connect(websocket_url) as websocket:
            try:
                # Send initial message
                await websocket.send(str(info))
                heartbeat(info)

                collected_messages = []

                log.debug("Sending to WebSocket", data=data)

                # Check if module name is openai (so we don't have to import openai package in our library)
                if data.__class__.__module__.startswith("openai"):
                    for chunk in data:
                        content = (
                            chunk.choices[0].delta.content
                            if chunk.choices[0].delta
                            else None
                        )
                        if content:
                            collected_messages.append(content)
                            chunk_info = {
                                **info,
                                "chunk": chunk.__dict__,
                            }
                            # log.debug("Sending content to WebSocket", chunkInfo=chunk_info)
                            await websocket.send(str(chunk_info))
                            heartbeat(chunk_info)

                    final_response = "".join(collected_messages)
                    return final_response
                elif isinstance(data, dict):
                    event_info = {
                        **info,
                        "data": data,
                    }
                    await websocket.send(str(event_info))
                    heartbeat(info)
                    return data
            finally:
                # Ensure the WebSocket connection is closed
                await websocket.close()
    except Exception as e:
        log.error(f"Error with restack stream to websocket: {e}")
        raise ApplicationError(f"Error with restack stream to websocket: {e}")
