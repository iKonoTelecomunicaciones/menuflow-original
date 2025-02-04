from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union

from mautrix.util.logging import TraceLogger

from .config import Config
from .flow_utils import FlowUtils
from .middlewares import ASRMiddleware, HTTPMiddleware, IRMMiddleware, LLMMiddleware, TTMMiddleware
from .nodes import (
    CheckTime,
    Delay,
    Email,
    FormInput,
    GPTAssistant,
    HTTPRequest,
    Input,
    InteractiveInput,
    InviteUser,
    Leave,
    Location,
    Media,
    Message,
    SetVars,
    Subroutine,
    Switch,
)
from .repository import Flow as FlowModel
from .room import Room
from .utils import Middlewares, Util

Node = Union[
    CheckTime,
    Email,
    HTTPRequest,
    Input,
    InteractiveInput,
    InviteUser,
    Leave,
    Location,
    Media,
    Message,
    SetVars,
    Subroutine,
    Switch,
    Delay,
    GPTAssistant,
    FormInput,
]


class Flow:
    flow_utils: FlowUtils
    log: TraceLogger = logging.getLogger("menuflow.flow")

    def __init__(self) -> None:
        self.data: Flow = None
        self.nodes: List[Dict] = []
        self.nodes_by_id: Dict[str, Dict] = {}

    @property
    def flow_variables(self) -> Dict:
        return {"flow": self.data.flow_variables or {}}

    @classmethod
    def init_cls(cls, flow_utils: FlowUtils) -> None:
        cls.flow_utils = flow_utils

    async def load_flow(
        self,
        flow_mxid: Optional[str] = None,
        content: Optional[Dict] = None,
        config: Optional[Config] = None,
    ) -> Flow:
        self.data = await FlowModel.load_flow(flow_mxid=flow_mxid, content=content, config=config)
        self.nodes = self.data.nodes or []
        self.nodes_by_id: Dict[str, Dict] = {}

        util = Util(config)
        await util.cancel_tasks()

    def _add_node_to_cache(self, node_data: Dict):
        self.nodes_by_id[node_data.get("id")] = node_data

    def get_node_by_id(self, node_id: str) -> Dict | None:
        """This function returns a node from a cache or a list of nodes based on its ID.

        Parameters
        ----------
        node_id : str
            The ID of the node that we want to retrieve from the graph.

        Returns
        -------
            This function returns a dictionary object representing a node in a graph, or `None`
            if the node with the given ID is not found.

        """

        try:
            return self.nodes_by_id[node_id]
        except KeyError:
            pass

        for node in self.nodes:
            if node_id == node.get("id", ""):
                self._add_node_to_cache(node)
                return node

    def middleware(
        self, middleware_id: str, room: Room
    ) -> HTTPMiddleware | IRMMiddleware | ASRMiddleware | None:
        middleware_model = self.flow_utils.get_middleware_by_id(middleware_id=middleware_id)
        try:
            middleware_type = Middlewares(middleware_model.type)
        except ValueError:
            self.log.warning(f"Middleware type {middleware_model.type} not found")
            return

        if not middleware_model:
            return

        if middleware_type in (Middlewares.JWT, Middlewares.BASIC, Middlewares.BASE):
            middleware_initialized = HTTPMiddleware(
                http_middleware_data=middleware_model,
                room=room,
                default_variables=self.flow_variables,
            )
        elif middleware_type == Middlewares.IRM:
            middleware_initialized = IRMMiddleware(
                irm_data=middleware_model, room=room, default_variables=self.flow_variables
            )
        elif middleware_type == Middlewares.LLM:
            middleware_initialized = LLMMiddleware(
                llm_data=middleware_model, room=room, default_variables=self.flow_variables
            )
        elif middleware_type == Middlewares.ASR:
            middleware_initialized = ASRMiddleware(
                asr_middleware_content=middleware_model,
                room=room,
                default_variables=self.flow_variables,
            )
        elif middleware_type == Middlewares.TTM:
            middleware_initialized = TTMMiddleware(
                ttm_data=middleware_model, room=room, default_variables=self.flow_variables
            )

        return middleware_initialized

    def node(self, room: Room) -> Node | None:
        node_data = self.get_node_by_id(node_id=room.route.node_id)

        if not node_data:
            return

        if node_data.get("type") == "message":
            node_initialized = Message(
                message_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "media":
            node_initialized = Media(
                media_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "email":
            node_initialized = Email(
                email_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "location":
            node_initialized = Location(
                location_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "switch":
            node_initialized = Switch(
                switch_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "input":
            node_initialized = Input(
                input_node_data=node_data, room=room, default_variables=self.flow_variables
            )
            if node_data.get("middlewares"):
                middlewares = []
                for middleware in node_data.get("middlewares"):
                    middlewares.append(self.middleware(middleware, room=room))
                node_initialized.middlewares = middlewares
        elif node_data.get("type") == "check_time":
            node_initialized = CheckTime(
                check_time_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "http_request":
            node_initialized = HTTPRequest(
                http_request_node_data=node_data, room=room, default_variables=self.flow_variables
            )

            if node_data.get("middleware"):
                middleware = self.middleware(node_data.get("middleware"), room)
                node_initialized.middleware = middleware
        elif node_data.get("type") == "interactive_input":
            node_initialized = InteractiveInput(
                interactive_input_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "leave":
            node_initialized = Leave(
                leave_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "set_vars":
            node_initialized = SetVars(
                set_vars_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "invite_user":
            node_initialized = InviteUser(
                invite_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "subroutine":
            node_initialized = Subroutine(
                subroutine_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "delay":
            node_initialized = Delay(
                delay_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        elif node_data.get("type") == "gpt_assistant":
            node_initialized = None
            if GPTAssistant.assistant_cache.get((room.room_id, room.route.id)):
                node_initialized = GPTAssistant.assistant_cache.get((room.room_id, room.route.id))
            else:
                node_initialized = GPTAssistant(
                    gpt_assistant_node_data=node_data,
                    room=room,
                    default_variables=self.flow_variables,
                )
                GPTAssistant.assistant_cache[(room.room_id, room.route.id)] = node_initialized

            if node_data.get("middlewares"):
                middlewares = []
                for middleware in node_data.get("middlewares"):
                    middlewares.append(self.middleware(middleware, room=room))
                node_initialized.middlewares = middlewares
        elif node_data.get("type") == "form":
            node_initialized = FormInput(
                form_node_data=node_data, room=room, default_variables=self.flow_variables
            )
        else:
            return

        return node_initialized
