import asyncio
from collections import defaultdict


class Bus:
    def __init__(self):
        self.subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, user_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.subscribers[user_id].add(queue)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue) -> None:
        self.subscribers[user_id].discard(queue)

    def publish(self, user_id: str, event: str) -> None:
        for queue in list(self.subscribers[user_id]):
            if not queue.full():
                queue.put_nowait(event)
