from __future__ import annotations

from typing import Dict, List

from attr import dataclass, ib
from mautrix.types import BaseMessageEventContent, SerializableAttrs

from ..flow_object import FlowObject
from .switch import Case


@dataclass
class FormMessageContent(SerializableAttrs):
    template_name: str = ib(default=None)
    body_variables: Dict[str, str] = ib(default=None)
    header_variables: Dict[str, str] = ib(default=None)
    button_variables: Dict[str, str] = ib(default=None)
    language: str = ib(default=None)


@dataclass
class FormMessage(SerializableAttrs, BaseMessageEventContent):
    msgtype: str = ib(default=None, metadata={"json": "msgtype"})
    body: str = ib(default="", metadata={"json": "body"})
    form_message: FormMessageContent = ib(
        factory=FormMessageContent, metadata={"json": "form_message"}
    )


@dataclass
class InactivityOptions(SerializableAttrs):
    chat_timeout: int = ib(default=None)
    warning_message: str = ib(default=None)
    time_between_attempts: int = ib(default=None)
    attempts: int = ib(default=None)


@dataclass
class Form(FlowObject):
    """
    ## Form

    Form node is a special type of input node that allows send a WhatsApp flow and
    capture the response of it and save it as variables.

    content:

    ```
    - id: f1
      type: form
      template_name: 'template_name'
      language: en
      body_variables:
        - opt
      header_variables:
        - opt
      button_variables:
        - opt
      variable: opt
      validation_fail:
        message: "Message"
        attempts: 3
      inactivity_options:
        chat_timeout: 20 #seconds
        warning_message: "Message"
        time_between_attempts: 10 #seconds
        attempts: 3
      cases:
        - id: submitted
          o_connection: submitted
        - id: timeout
          o_connection: timeout
        - id: attempt_exceeded
          o_connection: max_attempts
    ```
    """

    template_name: str = ib(factory=str)
    language: str = ib(factory=str)
    body_variables: Dict[str, str] = ib(default=None)
    header_variables: Dict[str, str] = ib(default=None)
    button_variables: Dict[str, str] = ib(default=None)
    variable: str = ib(default=None)
    inactivity_options: InactivityOptions = ib(default=None)
    cases: List[Case] = ib(factory=list)
