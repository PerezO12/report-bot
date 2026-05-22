from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserState:
    flow_id: str
    current_step_id: str
    answers: dict[str, Any] = field(default_factory=dict)
    media_file_ids: dict[str, dict | None] = field(default_factory=dict)


class StateStore:
    def __init__(self) -> None:
        self._store: dict[int, UserState] = {}

    def init_session(self, user_id: int, flow_id: str, first_step_id: str) -> None:
        self._store[user_id] = UserState(
            flow_id=flow_id,
            current_step_id=first_step_id,
        )

    def get_state(self, user_id: int) -> UserState | None:
        return self._store.get(user_id)

    def set_answer(self, user_id: int, step_id: str, value: Any) -> None:
        state = self._store.get(user_id)
        if state:
            state.answers[step_id] = value
            state.current_step_id = step_id

    def set_photo(self, user_id: int, step_id: str, file_id: str | None) -> None:
        """Backward compat — maps to set_media with type 'photo'."""
        if file_id:
            self.set_media(user_id, step_id, file_id, "photo")
        else:
            self.set_media(user_id, step_id, None, "photo")

    def set_media(
        self, user_id: int, step_id: str, file_id: str | None, media_type: str
    ) -> None:
        """Store media file_id with type (photo, video, document)."""
        state = self._store.get(user_id)
        if state:
            state.media_file_ids[step_id] = (
                {"file_id": file_id, "media_type": media_type} if file_id else None
            )
            state.current_step_id = step_id

    def clear_session(self, user_id: int) -> None:
        self._store.pop(user_id, None)
