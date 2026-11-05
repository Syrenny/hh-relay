import os


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        msg = f"{name} is not configured"
        raise RuntimeError(msg)
    return value
