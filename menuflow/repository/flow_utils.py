from __future__ import annotations

import logging
from typing import Dict, List

import yaml
from attr import dataclass, ib
from mautrix.types import SerializableAttrs
from mautrix.util.logging import TraceLogger

from ..utils import Middlewares
from .middlewares import EmailServer, HTTPMiddleware, IRMMiddleware, ASRMiddleware

log: TraceLogger = logging.getLogger("menuflow.repository.flow_utils")


@dataclass
class FlowUtils(SerializableAttrs):
    middlewares: List[HTTPMiddleware, IRMMiddleware, ASRMiddleware] = ib(default=[])
    email_servers: List[EmailServer] = ib(default=[])

    @classmethod
    def load_flow_utils(cls):
        try:
            path = f"/data/flow_utils.yaml"
            with open(path, "r") as file:
                flow_utils: Dict = yaml.safe_load(file)
            return cls.from_dict(flow_utils)
        except FileNotFoundError:
            log.warning("File flow_utils.yaml not found")

    @classmethod
    def from_dict(cls, data: dict) -> "FlowUtils":
        return cls(
            middlewares=[
                cls.initialize_middleware_dataclass(middleware)
                for middleware in data.get("middlewares", [])
            ],
            email_servers=[
                cls.initialize_email_server_dataclass(email_server)
                for email_server in data.get("email_servers", [])
            ],
        )

    @classmethod
    def initialize_middleware_dataclass(cls, middleware: Dict) -> HTTPMiddleware | IRMMiddleware | ASRMiddleware:
        try:
            middleware_type = Middlewares(middleware.get("type"))
        except ValueError:
            log.warning(f"Middleware type {middleware.get('type')} not found")
            return

        if middleware_type in (Middlewares.jwt, Middlewares.basic, Middlewares.base):
            return HTTPMiddleware(**middleware)
        elif middleware_type == Middlewares.irm:
            return IRMMiddleware.from_dict(middleware)
        elif middleware_type == Middlewares.asr:
            return ASRMiddleware.from_dict(middleware)

    @classmethod
    def initialize_email_server_dataclass(cls, email_server: Dict) -> EmailServer:
        return EmailServer(**email_server)
