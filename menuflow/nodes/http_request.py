from typing import TYPE_CHECKING, Dict

from aiohttp import BasicAuth, ClientTimeout, ContentTypeError
from mautrix.util.config import RecursiveDict
from ruamel.yaml.comments import CommentedMap

from ..db.route import RouteState
from ..events import MenuflowNodeEvents
from ..events.event_generator import send_node_event
from ..repository import HTTPRequest as HTTPRequestModel
from ..room import Room
from .switch import Switch
from .types import Nodes

if TYPE_CHECKING:
    from ..middlewares import HTTPMiddleware


class HTTPRequest(Switch):
    HTTP_ATTEMPTS: Dict = {}

    middleware: "HTTPMiddleware" = None

    def __init__(
        self, http_request_node_data: HTTPRequestModel, room: Room, default_variables: Dict
    ) -> None:
        Switch.__init__(
            self, http_request_node_data, room=room, default_variables=default_variables
        )
        self.log = self.log.getChild(http_request_node_data.get("id"))
        self.content: Dict = http_request_node_data

    @property
    def method(self) -> str:
        return self.content.get("method", "")

    @property
    def url(self) -> str:
        return self.render_data(self.content.get("url", ""))

    @property
    def http_variables(self) -> Dict:
        return self.render_data(self.content.get("variables", {}))

    @property
    def cookies(self) -> Dict:
        return self.render_data(self.content.get("cookies", {}))

    @property
    def headers(self) -> Dict:
        return self.render_data(self.content.get("headers", {}))

    @property
    def basic_auth(self) -> Dict:
        return self.render_data(self.content.get("basic_auth", {}))

    @property
    def query_params(self) -> Dict:
        return self.render_data(self.content.get("query_params", {}))

    @property
    def data(self) -> Dict:
        return self.render_data(self.content.get("data", {}))

    @property
    def json(self) -> Dict:
        return self.render_data(self.content.get("json", {}))

    @property
    def context_params(self) -> Dict[str, str]:
        return self.render_data(
            {
                "bot_mxid": "{{ route.bot_mxid }}",
                "customer_room_id": "{{ route.customer_room_id }}",
            }
        )

    def prepare_request(self) -> Dict:
        request_body = {}

        if self.query_params:
            request_body["params"] = self.query_params

        if self.basic_auth:
            request_body["auth"] = BasicAuth(
                login=self.basic_auth["login"],
                password=self.basic_auth["password"],
            )

        if self.headers:
            request_body["headers"] = self.headers

        if self.data:
            request_body["data"] = self.data

        if self.json:
            request_body["json"] = self.json

        return request_body

    async def make_request(self):
        """It makes a request to the URL specified in the node,
        and then it does some stuff with the response

        Returns
        -------
            The status code and the response text.
        """

        self.log.debug(f"Room {self.room.room_id} enters http_request node {self.id}")

        request_body = self.prepare_request()

        if self.middleware:
            self.middleware.room = self.room
            request_params_ctx = self.context_params
            request_params_ctx.update({"middleware": self.middleware})
        else:
            request_params_ctx = {}

        try:
            timeout = ClientTimeout(total=self.config["menuflow.timeouts.http_request"])
            response = await self.session.request(
                self.method,
                self.url,
                **request_body,
                trace_request_ctx=request_params_ctx,
                timeout=timeout,
            )
        except Exception as e:
            self.log.exception(f"Error in http_request node: {e}")
            o_connection = await self.get_case_by_id(id=500)
            await self.room.update_menu(node_id=o_connection, state=None)
            return 500, e

        self.log.debug(
            f"node: {self.id} method: {self.method} url: {self.url} status: {response.status}"
        )

        if response.status == 401:
            if not self.middleware:
                if self.cases:
                    o_connection = await self.get_case_by_id(id=response.status)

                if o_connection:
                    await self.room.update_menu(
                        node_id=o_connection, state=RouteState.END if not self.cases else None
                    )
            return response.status, None

        variables = {}
        o_connection = None

        if self.cookies:
            for cookie in self.cookies:
                variables[cookie] = response.cookies.output(cookie)

        try:
            response_data = await response.json()
        except ContentTypeError:
            response_data = {}

        if isinstance(response_data, dict):
            # Tulir and its magic since time immemorial
            serialized_data = RecursiveDict(CommentedMap(**response_data))
            if self.http_variables:
                for variable in self.http_variables:
                    try:
                        variables[variable] = self.render_data(
                            serialized_data[self.http_variables[variable]]
                        )
                    except KeyError:
                        pass
        elif isinstance(response_data, str):
            if self.http_variables:
                for variable in self.http_variables:
                    try:
                        variables[variable] = self.render_data(response_data)
                    except KeyError:
                        pass

                    break

        if self.cases:
            o_connection = await self.get_case_by_id(id=response.status)

        if o_connection:
            await self.room.update_menu(
                node_id=o_connection, state=RouteState.END if not self.cases else None
            )

        if variables:
            await self.room.set_variables(variables=variables)

        if o_connection is None:
            o_connection = await self.get_o_connection()

        return response.status, await response.text(), o_connection

    async def run_middleware(self, status: int):
        """This function check athentication attempts to avoid an infinite try_athentication cicle.

        Parameters
        ----------
        status : int
            Http status of the request.

        """

        if status in [200, 201]:
            self.HTTP_ATTEMPTS.update(
                {self.room.room_id: {"last_http_node": None, "attempts_count": 0}}
            )
            return

        if (
            self.HTTP_ATTEMPTS.get(self.room.room_id)
            and self.HTTP_ATTEMPTS[self.room.room_id]["last_http_node"] == self.id
            and self.HTTP_ATTEMPTS[self.room.room_id]["attempts_count"] >= self.middleware.attempts
        ):
            self.log.debug("Attempts limit reached, o_connection set as `default`")
            self.HTTP_ATTEMPTS.update(
                {self.room.room_id: {"last_http_node": None, "attempts_count": 0}}
            )
            await self.room.update_menu(await self.get_case_by_id("default"), None)

        if status == 401:
            self.HTTP_ATTEMPTS.update(
                {
                    self.room.room_id: {
                        "last_http_node": self.id,
                        "attempts_count": self.HTTP_ATTEMPTS.get(self.room.room_id, {}).get(
                            "attempts_count"
                        )
                        + 1
                        if self.HTTP_ATTEMPTS.get(self.room.room_id)
                        else 1,
                    }
                }
            )
            self.log.debug(
                "HTTP auth attempt "
                f"{self.HTTP_ATTEMPTS[self.room.room_id]['attempts_count']}, trying again ..."
            )

    async def run(self):
        """It makes a request to the URL specified in the node's configuration,
        and then runs the middleware
        """
        try:
            status, response, o_connection = await self.make_request()
            self.log.info(f"http_request node {self.id} had a status of {status}")
        except Exception as e:
            self.log.exception(e)

        if self.middleware:
            await self.run_middleware(status=status)

        await send_node_event(
            config=self.room.config,
            send_event=self.content.get("send_event"),
            event_type=MenuflowNodeEvents.NodeEntry,
            room_id=self.room.room_id,
            sender=self.room.matrix_client.mxid,
            node_type=Nodes.http_request,
            node_id=self.id,
            o_connection=o_connection,
            variables=self.room.all_variables | self.default_variables,
        )
