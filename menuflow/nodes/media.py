from __future__ import annotations

import mimetypes
from io import BytesIO
from typing import Dict

from mautrix.errors import MUnknown
from mautrix.types import (
    AudioInfo,
    FileInfo,
    ImageInfo,
    MediaInfo,
    MediaMessageEventContent,
    MessageType,
    VideoInfo,
)
from mautrix.util.magic import mimetype

from ..db.route import RouteState
from ..events import MenuflowNodeEvents
from ..events.event_generator import send_node_event
from ..repository import Media as MediaModel
from ..room import Room
from .message import Message
from .types import Nodes

try:
    from PIL import Image
except ImportError:
    Image = None


class Media(Message):
    media_cache: Dict[str, MediaMessageEventContent] = {}

    def __init__(self, media_node_data: MediaModel, room: Room, default_variables: Dict) -> None:
        Message.__init__(self, media_node_data, room=room, default_variables=default_variables)
        self.log = self.log.getChild(media_node_data.get("id"))
        self.content: Dict = media_node_data

    @property
    def url(self) -> str:
        return self.render_data(self.content.get("url", ""))

    @property
    def info(self) -> MediaInfo:
        if MessageType.AUDIO == self.message_type:
            media_info = AudioInfo(**self.render_data(self.content.get("info", {})))
        elif MessageType.VIDEO == self.message_type:
            media_info = VideoInfo(**self.render_data(self.content.get("info", {})))
        elif MessageType.IMAGE == self.message_type:
            media_info = ImageInfo(**self.render_data(self.content.get("info", {})))
        elif MessageType.FILE == self.message_type:
            media_info = FileInfo(**self.render_data(self.content.get("info", {})))
        else:
            self.log.warning(
                f"It has not been possible to identify the message type of the node {self.id}"
            )
            return

        return media_info

    async def load_media(self) -> MediaMessageEventContent:
        """It downloads the media from the URL, uploads it to the Matrix server,
        and returns a MediaMessageEventContent object with the URL of the uploaded media

        Returns
        -------
            MediaMessageEventContent

        """
        resp = await self.session.get(self.url)
        data = await resp.read()
        media_info = self.info

        if media_info is None:
            return

        if not media_info.mimetype:
            media_info.mimetype = mimetype(data)

        if (
            media_info.mimetype.startswith("image/")
            and not media_info.width
            and not media_info.height
        ):
            with BytesIO(data) as inp, Image.open(inp) as img:
                media_info.width, media_info.height = img.size

        media_info.size = len(data)

        extension = {
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "video/mp4": ".mp4",
            "audio/mp4": ".m4a",
            "audio/ogg": ".ogg",
            "application/pdf": ".pdf",
        }.get(media_info.mimetype)

        extension = extension or mimetypes.guess_extension(media_info.mimetype) or ""

        file_name = f"{self.message_type.value[2:]}{extension}" if self.message_type else None

        try:
            mxc = await self.room.matrix_client.upload_media(
                data=data, mime_type=media_info.mimetype, filename=file_name
            )
        except MUnknown as e:
            self.log.exception(f"error {e}")
            return
        except Exception as e:
            self.log.exception(f"Message not receive :: error {e}")
            return

        return MediaMessageEventContent(
            msgtype=self.message_type, body=self.text, url=mxc, info=media_info
        )

    async def run(self):
        """It sends a message to the room with the media attached"""
        self.log.debug(f"Room {self.room.room_id} enters media node {self.id}")

        o_connection = self.get_o_connection()
        try:
            media_message = self.media_cache[self.url]
        except KeyError:
            media_message = await self.load_media()
            if media_message is None:
                await self.room.update_menu(
                    node_id=o_connection,
                    state=RouteState.END if not o_connection else None,
                )
            self.media_cache[self.url] = media_message

        await self.send_message(room_id=self.room.room_id, content=media_message)

        await self.room.update_menu(
            node_id=o_connection,
            state=RouteState.END if not o_connection else None,
        )

        await send_node_event(
            config=self.room.config,
            send_event=self.content.get("send_event"),
            event_type=MenuflowNodeEvents.NodeEntry,
            room_id=self.room.room_id,
            sender=self.room.matrix_client.mxid,
            node_type=Nodes.media,
            node_id=self.id,
            o_connection=o_connection,
            variables=self.room.all_variables | self.default_variables,
        )
