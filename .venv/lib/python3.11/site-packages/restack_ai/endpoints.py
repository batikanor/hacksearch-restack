import inspect
from typing import Any, Dict
from pydantic import BaseModel
from dataclasses import is_dataclass
from msgspec import json


def extract_openapi_schema(cls: Any) -> Dict[str, Any]:
    """
    Extract the OpenAPI-compatible JSON schema of a Pydantic model or dataclass if applicable.
    """

    if issubclass(cls, BaseModel):
        schema = cls.model_json_schema()
        # Determine required fields for Pydantic models
        required = [
            name
            for name, prop in schema.get("properties", {}).items()
            if not any(
                subschema.get("type") == "null" for subschema in prop.get("anyOf", [])
            )
        ]
        formatted_schema = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": required,
            "title": schema.get("title", cls.__name__),
        }
        return formatted_schema
    elif is_dataclass(cls):
        # Generate JSON schema using msgspec
        schema = json.schema(cls)
        properties = schema.get("$defs", {}).get(cls.__name__, {}).get("properties", {})

        # Determine required fields for dataclasses
        required = [
            name
            for name, prop in properties.items()
            if not any(
                subschema.get("type") == "null" for subschema in prop.get("anyOf", [])
            )
        ]

        formatted_schema = {
            "type": "object",
            "properties": properties,
            "required": required,
            "title": cls.__name__,
        }
        return formatted_schema
    return {}


def explore_class_details(cls: Any) -> Dict[str, Any]:
    """
    Extract detailed information about a class or function, focusing on input/output schemas.

    Returns:
        Dict containing:
        - name: The name of the class/function
        - type: 'class' or 'function'
        - input_schema: OpenAPI-compatible JSON schema of the input if applicable
        - output_schema: OpenAPI-compatible JSON schema of the output if applicable
    """
    details = {
        "name": getattr(cls, "__name__", "Unknown"),
        "type": "class" if inspect.isclass(cls) else "function",
        "input_schema": {},
        "output_schema": {},
    }

    if inspect.isclass(cls):
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if name == "run":
                sig = inspect.signature(method)
                for param in sig.parameters.values():
                    if param.annotation != inspect.Parameter.empty and inspect.isclass(
                        param.annotation
                    ):
                        details["input_schema"] = extract_openapi_schema(
                            param.annotation
                        )
                if sig.return_annotation != inspect.Signature.empty and inspect.isclass(
                    sig.return_annotation
                ):
                    details["output_schema"] = extract_openapi_schema(
                        sig.return_annotation
                    )

    return details
