"""Generated pytest suite creation."""

from __future__ import annotations

from pathlib import Path
from pprint import pformat

from server.generators.common import relative_manifest_entry, write_template
from server.parser import FieldIR, FoundryIR, ResourceIR


def generate_tests(ir: FoundryIR, output_root: Path) -> tuple[list[str], int]:
    """Generate pytest coverage for the emitted backend routes."""
    files_written: list[str] = []

    conftest_path = output_root / "tests" / "conftest.py"
    write_template(conftest_path, "backend/tests/conftest.py.j2")
    files_written.append(relative_manifest_entry(output_root, conftest_path))

    test_count = 0
    for resource in ir.resources:
        test_path = output_root / "tests" / f"test_{resource.module_name}.py"
        write_template(
            test_path,
            "backend/tests/test_resource.py.j2",
            resource=_test_context(resource),
        )
        files_written.append(relative_manifest_entry(output_root, test_path))
        test_count += 5

    return sorted(dict.fromkeys(files_written)), test_count


def _test_context(resource: ResourceIR) -> dict[str, object]:
    return {
        "module_name": resource.module_name,
        "class_name": resource.class_name,
        "collection_path": resource.path,
        "detail_path": resource.detail_path.replace(f"{{{resource.path_parameter}}}", "{item_id}"),
        "sample_payload_literal": pformat(_sample_payload(resource.fields), sort_dicts=True),
        "update_payload_literal": pformat(_update_payload(resource.fields), sort_dicts=True),
    }


def _sample_payload(fields: tuple[FieldIR, ...]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields:
        if field.required or field.nullable:
            payload[field.name] = field.sample_value
    return payload


def _update_payload(fields: tuple[FieldIR, ...]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields:
        if field.python_type == "str":
            payload[field.name] = f"updated-{field.name}"
            break
        if field.python_type == "int":
            payload[field.name] = 99
            break
        if field.python_type == "bool":
            payload[field.name] = False
            break
    if not payload and fields:
        payload[fields[0].name] = fields[0].sample_value
    return payload
