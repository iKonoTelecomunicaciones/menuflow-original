from __future__ import annotations

from typing import Dict, List

from ..events import MenuflowNodeEvents
from ..events.event_generator import send_node_event
from ..repository import Switch as SwitchModel
from ..room import Room
from ..utils import Nodes
from .base import Base, safe_data_convertion


class Switch(Base):
    # Keeps track of the number of validation attempts made in a switch node by room.
    VALIDATION_ATTEMPTS_BY_ROOM: Dict[str, int] = {}

    def __init__(self, switch_node_data: SwitchModel, room: Room, default_variables: Dict) -> None:
        Base.__init__(self, room=room, default_variables=default_variables)
        self.log = self.log.getChild(switch_node_data.get("id"))
        self.content: Dict = switch_node_data

    @property
    def validation(self) -> str:
        return (
            self.render_data(data=self.content.get("validation"))
            if self.content.get("validation")
            else None
        )

    @property
    def validation_attempts(self) -> int | None:
        if not self.content.get("validation_fail"):
            return

        return self.content.get("validation_fail").get("attempts")

    @property
    def validation_fail_message(self) -> str:
        if not self.content.get("validation_fail"):
            return

        return self.content.get("validation_fail").get("message")

    @property
    def cases(self) -> List[Dict]:
        return self.content.get("cases")

    async def load_cases(self) -> Dict[str, str]:
        """It loads the cases into a dictionary.

        Parameters
        ----------
        room : Room
            Room = None

        Returns
        -------
            A dictionary of cases.

        """

        cases_dict = {}

        for case in self.cases:
            cases_dict[safe_data_convertion(case.get("id"))] = {
                "o_connection": case.get("o_connection"),
                "variables": case.get("variables"),
            }
        return cases_dict

    async def _run(self) -> str:
        """It takes a dictionary of variables, runs the rule,
        and returns the connection that matches the case

        Returns
        -------
            The str object

        """
        result = None

        try:
            self.log.info(f"Get validation of input [{self.id}] for room [{self.room.room_id}]")
            result = self.validation
        except Exception as e:
            self.log.warning(f"An exception has occurred in the pipeline [{self.id} ]:: {e}")
            result = "except"

        if result is None:
            self.log.debug(f"Validation value not found, validating case by case in [{self.id}]")
            return await self.validate_cases()

        return await self.get_case_by_id(result)

    async def run(self, update_state: bool = True, generate_event: bool = True) -> str:
        """This function runs the switch node.

        Parameters
        ----------
        update_state : bool
            If true, the state of the room will be updated.
        generate_event : bool
            If true, the event will be generated.
        """
        o_connection = await self._run()

        if update_state:
            await self.room.update_menu(o_connection)

        if generate_event:
            await send_node_event(
                config=self.room.config,
                send_event=self.content.get("send_event"),
                event_type=MenuflowNodeEvents.NodeEntry,
                room_id=self.room.room_id,
                sender=self.room.matrix_client.mxid,
                node_type=Nodes.switch,
                node_id=self.id,
                o_connection=o_connection,
                variables=self.room.all_variables | self.default_variables,
            )

        return o_connection

    async def get_case_by_id(self, id: str | int) -> str:
        id = safe_data_convertion(id)

        try:
            cases = await self.load_cases()
            case_result: Dict = cases[id]

            # Load variables defined in the case into the room
            await self.load_variables(case_result.get("variables", {}))

            case_o_connection = self.render_data(case_result.get("o_connection"))

            self.log.debug(
                f"The case [{case_o_connection}] has been obtained in the input node [{self.id}]"
            )

            if self.validation_attempts and self.room.room_id in self.VALIDATION_ATTEMPTS_BY_ROOM:
                del self.VALIDATION_ATTEMPTS_BY_ROOM[self.room.room_id]

        except KeyError:
            default_case, case_o_connection = await self.manage_case_exceptions()
            self.log.debug(f"Case [{id}] not found; the [{default_case} case] will be sought")

        if case_o_connection is None or case_o_connection in ["finish", ""]:
            case_o_connection = await self.get_o_connection()

        return case_o_connection

    async def validate_cases(self) -> str:
        """Used to validate case by case and return the o_connection value
        for the first valid case.

        Returns
        -------
            the value of the variable `case_o_connection`.

        """
        case_o_connection = None

        for case in self.cases:
            if not case.get("case") and case.get("id"):
                self.log.warning(
                    f"You should use the 'validation' field to use case by ID in [{self.id}]"
                )
                continue

            case_validation = self.render_data(case.get("case", False))
            if not case_validation:
                continue

            if case_validation and not isinstance(case_validation, bool):
                self.log.warning(
                    f"Case validation [{case_validation}] in [{self.id}] should be boolean"
                )
                continue

            # Load variables defined in the case into the room
            await self.load_variables(case.get("variables", {}))

            # Get the o_connection of the case
            case_o_connection = self.render_data(case.get("o_connection"))
            self.log.debug(
                f"The case [{case_o_connection}] has been obtained in the input node [{self.id}]"
            )

            # Delete the validation attempts of the room
            if self.validation_attempts and self.room.room_id in self.VALIDATION_ATTEMPTS_BY_ROOM:
                del self.VALIDATION_ATTEMPTS_BY_ROOM[self.room.room_id]

        if not case_o_connection:
            default_case, case_o_connection = await self.manage_case_exceptions()
            self.log.debug(
                f"Case validations in [{self.id}] do not match with [{case_o_connection}]; "
                f"the [{default_case}] case will be sought"
            )

        if case_o_connection is None or case_o_connection in ["finish", ""]:
            case_o_connection = await self.get_o_connection()

        return case_o_connection

    async def load_variables(self, variables: Dict) -> None:
        """This function loads variables defined in switch cases into the room.

        Parameters
        ----------
        case : Dict
            `case` is the selected switch case.

        """
        variables_recorded = []
        if not variables:
            return

        for variable in variables:
            if variable in variables_recorded:
                continue

            await self.room.set_variable(
                variable_id=variable,
                value=self.render_data(variables[variable]),
            )
            variables_recorded.append(variable)

    async def manage_case_exceptions(self) -> tuple[str, str]:
        """
        This function handles exceptions when getting cases in the switch node,
        if the selected case can not be found it provides a default case.

        Returns
        -------
            A tuple containing two strings:
            the first string is the name of the case being used
            (either "attempt_exceeded" or "default"),
            and the second string is the value of the "o_connection" key in the
            default case dictionary (or "start" if the key is not present).

        """
        cases = await self.load_cases()

        room_validation_attempts = self.VALIDATION_ATTEMPTS_BY_ROOM.get(self.room.room_id, 1)
        if self.validation_attempts and room_validation_attempts >= self.validation_attempts:
            if self.room.room_id in self.VALIDATION_ATTEMPTS_BY_ROOM:
                del self.VALIDATION_ATTEMPTS_BY_ROOM[self.room.room_id]
            case_to_be_used = "attempt_exceeded"
        else:
            case_to_be_used = "default"

        if self.validation_attempts and case_to_be_used == "default":
            self.log.critical(
                f"Validation Attempts {room_validation_attempts} "
                f"of {self.validation_attempts} for room {self.room.room_id}"
            )
            self.VALIDATION_ATTEMPTS_BY_ROOM[self.room.room_id] = room_validation_attempts + 1

        # Getting the default case
        default_case = cases.get(case_to_be_used, {})

        # Load variables defined in the case into the room
        await self.load_variables(default_case)

        # Getting the o_connection of the default case
        default_o_connection = self.render_data(default_case.get("o_connection"))

        return case_to_be_used, default_o_connection
