import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from markdown import markdown
from mautrix.types import Format, MessageEvent, MessageType, TextMessageEventContent

from ..db.route import RouteState
from ..events import MenuflowNodeEvents
from ..events.event_generator import send_node_event
from ..repository import Form, FormMessage, FormMessageContent
from ..room import Room
from ..utils import Nodes, Util
from .input import Input


class FormInput(Input):
    fail_attempts_by_room = {}

    def __init__(self, form_node_data: Form, room: Room, default_variables: Dict) -> None:
        Input.__init__(self, form_node_data, room, default_variables)
        self.content = form_node_data

    @property
    def template_name(self) -> Dict[str, Any]:
        return self.render_data(self.content.get("template_name", ""))

    @property
    def language(self) -> str:
        return self.render_data(self.content.get("language", "en"))

    @property
    def body_variables(self) -> List[str]:
        return self.render_data(self.content.get("body_variables", []))

    @property
    def header_variables(self) -> Dict[str, Any]:
        return self.render_data(self.content.get("header_variables", []))

    @property
    def button_variables(self) -> Dict[str, Any]:
        return self.render_data(self.content.get("button_variables", []))

    @property
    def form_message_content(self) -> FormMessage:
        form_message = FormMessage(
            msgtype="m.form",
            form_message=FormMessageContent(
                template_name=self.template_name,
                language=self.language,
                body_variables=self.body_variables,
                header_variables=self.header_variables,
                button_variables=self.button_variables,
            ),
        )
        form_message.trim_reply_fallback()
        return form_message

    async def __update_menu(self, case_id: str) -> str:
        if self.room.room_id in self.fail_attempts_by_room:
            del self.fail_attempts_by_room[self.room.room_id]

        o_connection = await self.get_case_by_id(case_id)
        await self.room.update_menu(o_connection)
        return o_connection

    async def check_fail_attempts(self):
        if not self.validation_attempts:
            return

        current_fail_attempts = self.fail_attempts_by_room.get(self.room.room_id, 0)
        if current_fail_attempts >= self.validation_attempts:
            await self.__update_menu("attempt_exceeded")
            return

        if self.validation_fail_message:
            msg_content = TextMessageEventContent(
                msgtype=MessageType.TEXT,
                body=self.validation_fail_message,
                format=Format.HTML,
                formatted_body=markdown(text=self.validation_fail_message, extensions=["nl2br"]),
            )
            await self.send_message(self.room.room_id, msg_content)

        self.fail_attempts_by_room[self.room.room_id] = current_fail_attempts + 1

    async def run(self, evt: Optional[MessageEvent]):
        """Send WhhatApp flow and capture the response of it and save it as variables.
        if the MessageEvent is not m.form_response, wait for the user to send the response.

        Parameters
        ----------
        client : MatrixClient
            The MatrixClient object.
        evt : Optional[MessageEvent]
            The event that triggered the node.

        """

        if self.room.route.state == RouteState.INPUT:
            if not evt or not self.variable or evt.content.msgtype != "m.form_response":
                self.log.warning(
                    "A problem occurred getting user response, message type is not m.form_response"
                )
                await self.check_fail_attempts()
                return

            if self.inactivity_options:
                await Util.cancel_task(task_name=self.room.room_id)

            self.room.set_variable(self.variable, evt.content.get("form_data"))
            o_connection = await self.__update_menu("submitted")

            await send_node_event(
                config=self.room.config,
                send_event=self.content.get("send_event"),
                event_type=MenuflowNodeEvents.NodeInputData,
                room_id=self.room.room_id,
                sender=self.room.matrix_client.mxid,
                node_id=self.id,
                o_connection=o_connection,
                variables=self.room.all_variables | self.default_variables,
            )
        else:
            # This is the case where the room is not in the input state
            # and the node is an input node.
            # In this case, the message is shown and the menu is updated to the node's id
            # and the room state is set to input.
            self.log.debug(f"Room {self.room.room_id} enters input node {self.id}")
            await self.room.matrix_client.send_message_event(
                room_id=self.room.room_id,
                event_type="m.room.message",
                content=self.form_message_content,
            )
            await self.room.update_menu(node_id=self.id, state=RouteState.INPUT)
            if self.inactivity_options:
                await self.inactivity_task()

            await send_node_event(
                config=self.room.config,
                send_event=self.content.get("send_event"),
                event_type=MenuflowNodeEvents.NodeEntry,
                room_id=self.room.room_id,
                sender=self.room.matrix_client.mxid,
                node_type=Nodes.media,
                node_id=self.id,
                o_connection=None,
                variables=self.room.all_variables | self.default_variables,
            )

    async def inactivity_task(self):
        """It spawns a task to harass the client to enter information to input option

        Parameters
        ----------
        client : MatrixClient
            The MatrixClient object

        """

        self.log.debug(f"Inactivity loop starts in room: {self.room.room_id}")
        asyncio.create_task(self.timeout_active_chats(), name=self.room.room_id)

    async def timeout_active_chats(self):
        """It sends messages in time intervals to communicate customer
        that not entered information to input option.

        Parameters
        ----------
        client : MatrixClient
            The Matrix client object.

        """

        # wait the given time to start the task
        await asyncio.sleep(self.chat_timeout)

        count = 0
        while True:
            self.log.debug(f"Inactivity loop: {datetime.now()} -> {self.room.room_id}")
            if self.attempts == count:
                self.log.debug(f"INACTIVITY TRIES COMPLETED -> {self.room.room_id}")
                o_connection = await self.__update_menu("timeout")

                await send_node_event(
                    config=self.room.config,
                    send_event=self.content.get("send_event"),
                    event_type=MenuflowNodeEvents.NodeInputTimeout,
                    room_id=self.room.room_id,
                    sender=self.room.matrix_client.mxid,
                    node_id=self.id,
                    o_connection=o_connection,
                    variables=self.room.all_variables | self.default_variables,
                )

                await self.room.matrix_client.algorithm(room=self.room)
                break

            await self.room.matrix_client.send_text(
                room_id=self.room.room_id, text=self.warning_message
            )
            await asyncio.sleep(self.time_between_attempts)
            count += 1
