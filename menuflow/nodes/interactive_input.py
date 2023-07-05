from mautrix.types import MessageEvent

from ..db.room import RoomState
from .input import Input
from ..repository import InteractiveInput as InteractiveInputModel
from ..repository import InteractiveMessage
from ..room import Room
from typing import Dict, Any, Optional
from ..utils import Util


class InteractiveInput(Input):
    def __init__(
        self, interactive_input_data: InteractiveInputModel, room: Room, default_variables: Dict
    ) -> None:
        Input.__init__(
            self,
            input_node_data=interactive_input_data,
            room=room,
            default_variables=default_variables,
        )
        self.content = interactive_input_data

    @property
    def interactive_message(self) -> Dict[str, Any]:
        return self.render_data(self.content.get("interactive_message", {}))

    @property
    def interactive_message_type(self) -> str:
        if self.interactive_message.get("type") == "list":
            return "m.interactive.list_reply"
        else:
            return "m.interactive.quick_reply"

    @property
    def interactive_message_content(self) -> InteractiveMessage:
        interactive_message = InteractiveMessage.from_dict(
            msgtype=self.interactive_message_type,
            interactive_message=self.interactive_message,
        )
        interactive_message.trim_reply_fallback()
        return interactive_message

    async def run(self, evt: Optional[MessageEvent]):
        """If the room is in input mode, then set the variable.
        Otherwise, show the message and enter input mode

        Parameters
        ----------
        client : MatrixClient
            The MatrixClient object.
        evt : Optional[MessageEvent]
            The event that triggered the node.

        """

        if self.room.state == RoomState.INPUT:
            if not evt or not self.variable:
                self.log.warning("A problem occurred to trying save the variable")
                return

            await self.input_text(content=evt.content)

            if self.inactivity_options:
                await Util.cancel_task(task_name=self.room.room_id)
        else:
            # This is the case where the room is not in the input state
            # and the node is an input node.
            # In this case, the message is shown and the menu is updated to the node's id
            # and the room state is set to input.
            self.log.debug(f"Room {self.room.room_id} enters input node {self.id}")
            await self.room.matrix_client.send_message_event(
                room_id=self.room.room_id,
                event_type="m.room.message",
                content=self.interactive_message_content,
            )
            await self.room.update_menu(node_id=self.id, state=RoomState.INPUT)
            if self.inactivity_options:
                await self.inactivity_task()
