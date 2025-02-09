import logging
import datetime
from typing import Any
import colorama
from colorama import Fore, Style
from temporalio.runtime import (
    Runtime,
    LoggingConfig,
    TelemetryConfig,
    LogForwardingConfig,
    TelemetryFilter,
)

colorama.init()

BLACK_LIST_META = [
    "sdk_component",
    "is_local",
    "attempt",
    "namespace",
    "task_token",
    "activity_id",
    "restack",
    "client_log",
]


def extract_useful_meta(meta: dict) -> dict:
    if not meta:
        return {}

    useful_meta = {}

    # Include all keys that aren't in BLACK_LIST_META
    for key, value in meta.items():
        if key not in BLACK_LIST_META:
            useful_meta[key] = value

    # Special case: rename activityType to function
    if "activity_type" in meta:
        useful_meta["function"] = meta["activity_type"]
        del useful_meta["activity_type"]

    return useful_meta


def rename_complete_activity_or_workflow_message(message: str) -> str:
    lower_case_message = message.lower()
    if "activity" in lower_case_message:
        return lower_case_message.replace("activity", "function")

    return message


class ColoredFormatter(logging.Formatter):
    """Custom formatter adding colors and improved formatting to log messages"""

    COLORS = {
        "DEBUG": Fore.RESET,
        "INFO": Fore.RESET,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
        "SUCCESS": Fore.GREEN + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        level_color = self.COLORS.get(record.levelname, "")
        reset_color = Style.RESET_ALL

        timestamp = (
            datetime.datetime.fromtimestamp(record.created).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z"
        )

        # Get the base message
        message = record.getMessage()
        # Split the message and the dictionary if present
        base_message = message
        context_dict = None

        if "({" in message and "})" in message:
            parts = message.split("({", 1)
            base_message = parts[0].strip()
            try:
                context_dict = eval("({" + parts[1])
            except (SyntaxError, ValueError):
                pass

        if not hasattr(record, "extra_fields") and context_dict is None:
            return ""

        if (
            record.levelname == "DEBUG"
            or record.levelname == "WARNING"
            and not getattr(record, "extra_fields", {}).get("restack")
            and not getattr(record, "extra_fields", {}).get("client_log")
        ):
            base_message = rename_complete_activity_or_workflow_message(base_message)

        # Start with timestamp and base message
        formatted = f"[restack] {Fore.MAGENTA}{timestamp}{reset_color} [{level_color}{record.levelname}{reset_color}] {base_message}"

        # Add context dictionary items if present

        context_dict_with_meta = extract_useful_meta(context_dict)

        if context_dict_with_meta:
            formatted += "\n"
            for key, value in context_dict_with_meta.items():
                formatted += f"  {key}: {Fore.GREEN}{value}{reset_color}\n"

        # Add any additional extra fields
        if hasattr(record, "extra_fields"):
            if not context_dict_with_meta:  # Only add newline if we haven't already
                formatted += "\n"
            for key, value in record.extra_fields.items():
                if key not in ["restack", "client_log"]:
                    formatted += f"  {key}: {Fore.GREEN}{value}{reset_color}"

        return formatted


def setup_logger(name: str = "restack", level: str = "DEBUG") -> logging.Logger:
    """Setup and configure the logger with colored output"""
    # Setup single restack logger that will receive all logs
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter())
    console_handler.setLevel(logging.DEBUG)

    logger.handlers.clear()
    logger.addHandler(console_handler)

    temporal_logger = logging.getLogger("temporal")
    temporal_logger.setLevel(logging.DEBUG)
    temporal_logger.addHandler(console_handler)
    temporal_logger.propagate = False

    # Configure Temporal runtime with our logger
    try:
        runtime = Runtime(
            telemetry=TelemetryConfig(
                logging=LoggingConfig(
                    filter=TelemetryFilter(core_level="INFO", other_level="INFO"),
                    forwarding=LogForwardingConfig(
                        logger=logger,
                        append_target_to_name=False,
                        prepend_target_on_message=False,
                        overwrite_log_record_time=True,
                        append_log_fields_to_message=True,
                    ),
                ),
                metrics=None,
            )
        )
        # Set this runtime as the default
        Runtime.set_default(runtime, error_if_already_set=False)
    except Exception as e:
        logger.error(f"Failed to create Runtime: {str(e)}")

    return logger


logger = setup_logger()


def log_with_context(level: str, message: str, **kwargs: Any) -> None:
    """Helper function to log messages with additional context"""
    if kwargs:
        extra = {"extra_fields": {**kwargs, "restack": True}}
    else:
        extra = {"extra_fields": {"restack": True}}
    getattr(logger, level.lower())(message, extra=extra)


__all__ = ["logger", "log_with_context"]
