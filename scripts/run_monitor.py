import asyncio

from hh_relay.config import MonitorSettings
from hh_relay.monitor import run_monitor


def main() -> None:
    asyncio.run(run_monitor(MonitorSettings.from_env()))


if __name__ == "__main__":
    main()
