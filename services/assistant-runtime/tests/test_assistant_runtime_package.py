from fastapi import FastAPI
from veritymesh_assistant_runtime import __version__, create_app


def test_package_import() -> None:
    assert __version__ == "0.0.0"
    assert isinstance(create_app(), FastAPI)
