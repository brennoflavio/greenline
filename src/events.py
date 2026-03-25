from datetime import timedelta
from typing import Dict, Optional

from ut_components.event import Event


class NewMessageEvent(Event):
    def __init__(self):
        super().__init__(id="new-message", execution_interval=timedelta(seconds=2))

    def trigger(self, metadata: Optional[Dict]):
        pass


class MessageStatusUpdateEvent(Event):
    def __init__(self):
        super().__init__(id="message-status-update", execution_interval=timedelta(seconds=5))

    def trigger(self, metadata: Optional[Dict]):
        pass


class ChatListUpdateEvent(Event):
    def __init__(self):
        super().__init__(id="chat-list-update", execution_interval=timedelta(seconds=30))

    def trigger(self, metadata: Optional[Dict]):
        pass
