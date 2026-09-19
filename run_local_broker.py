import asyncio
import logging
import sys

logging.basicConfig(level=logging.WARNING)

try:
    from amqtt.broker import Broker
except ImportError:
    print("[FAIL] amqtt not installed. Run: pip install amqtt")
    sys.exit(1)


CONFIG = {
    "listeners": {
        "default": {
            "type": "tcp",
            "bind": "0.0.0.0:1883",
            "max_connections": 100,
        },
    },
    "sys_interval": 10,
    "auth": {
        "allow-anonymous": True,
        "plugins": [],
    },
    "topic-check": {
        "enabled": False,
    },
}


async def main():
    broker = Broker(CONFIG)
    await broker.start()
    print("=" * 60)
    print("LOCAL MQTT BROKER RUNNING")
    print("  bind: tcp://0.0.0.0:1883")
    print("  auth: anonymous allowed")
    print("  topic-check: disabled")
    print("=" * 60)
    print("Leave this terminal open. Press Ctrl+C to stop.")
    print("=" * 60)
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbroker stopped")