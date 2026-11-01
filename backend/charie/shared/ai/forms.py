"""Fixed JSON forms: Pydantic models become strict schemas Meta takes."""

from typing import Any

from pydantic import BaseModel

from charie.shared.ai.errors import AiError


class FormError(AiError):
    """The form itself breaks Meta's rules."""

    def __init__(self, message: str) -> None:
        super().__init__("bad_form", message)


def form_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A strict JSON schema for the model; refuses what Meta can't take."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    seen: set[str] = set()
    return _strict(schema, model.__name__, model.__name__, defs, seen)


def _strict(node: Any, owner: str, model_name: str, defs: dict[str, Any], seen: set[str]) -> Any:
    """Inline `$ref`s, then make every object strict with described fields."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" not in node:
            raise FormError(
                f"Field `{owner}` is a free-form object; type its fields in a model "
                "so Meta can take it."
            )
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.removeprefix("#/$defs/")
            if name == model_name or name in seen:
                raise FormError(
                    f"The form for `{model_name}` refers to itself. "
                    "Use a flat list where each item names its parent."
                )
            if name not in defs:
                raise FormError(f"The form for `{model_name}` refers to unknown `{name}`.")
            import copy

            node = copy.deepcopy(defs[name])
            seen = seen | {name}
        if "properties" in node and isinstance(node["properties"], dict):
            properties = node["properties"]
            for field, sub in properties.items():
                if isinstance(sub, dict) and "description" not in sub:
                    raise FormError(
                        f"Field `{owner}.{field}` needs a one-line description; the AI sees it."
                    )
                properties[field] = _strict(sub, field, model_name, defs, seen)
            node["additionalProperties"] = False
            node["required"] = sorted(properties)
        else:
            for key, value in node.items():
                node[key] = _strict(value, owner, model_name, defs, seen)
        return node
    if isinstance(node, list):
        return [_strict(value, owner, model_name, defs, seen) for value in node]
    return node
