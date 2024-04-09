import re
import secrets
import os
import time
from datetime import datetime, date
from pathlib import Path
from typing import Annotated, Any
from aiohttp import ClientSession
from pydantic import BaseModel, BeforeValidator
from litestar import Controller, Request, get, post
from litestar.datastructures import State
from litestar.response import Template
from litestar import Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.config.cors import CORSConfig
from litestar.config.csrf import CSRFConfig
from litestar.config.allowed_hosts import AllowedHostsConfig
from litestar.static_files import create_static_files_router
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.contrib.sqlalchemy.base import UUIDAuditBase, UUIDBase
from litestar.contrib.sqlalchemy.plugins import (
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
)
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.stores.file import FileStore

from .core import TimetableClient, fetch, Entry

# from .models import User, Rule, Filter


class Payload(BaseModel):
    start: date | None = None
    end: date | None = None
    types: dict[str, list[str]]  # type: [regex]

    def __init__(self, **data: Any):
        super().__init__(**data)

    def get_start(self) -> date:
        return self.start or datetime.now().date()

    def get_end(self) -> date:
        return self.end or datetime.now().date()


class TimetableResponse(BaseModel):
    entries: dict[date, list[dict[str, Any]]]
    time: float
    fields: list[str] = Entry.dump_fields


class MainController(Controller):

    path = "/"

    template = "index.html"

    @get()
    async def home(self, request: Request, state: State) -> Template:
        return Template(
            self.template,
            context={
                "types": await state.client.get_types(),
                "preload": request.session or {"types": []},
            },
        )

    @post()
    async def fetch_table(
        self,
        request: Request,
        state: State,
        data: Payload,
    ) -> TimetableResponse:
        start = time.perf_counter()
        request.set_session(data)
        entries: dict[date, list[Entry]] = {}
        items = await state.client.fetch(start=data.get_start(), end=data.get_end())
        for item in items:
            bucket = entries.setdefault(item.start.date(), [])
            if item.type in data.types:
                filters = data.types[item.type]
                if not filters:
                    bucket.append(item)
                for filt in filters:
                    if re.search(filt, item.full_desc):
                        bucket.append(item)
                        break
        for bucket in entries.values():
            bucket.sort(key=lambda e: e.start)

        response: dict[date, list[dict[str, Any]]] = {}
        for e, b in sorted(entries.items(), key=lambda t: t[0]):
            response[e] = [i.dump() for i in b]

        return TimetableResponse(entries=response, time=time.perf_counter() - start)

    @get("/about")
    async def about(self) -> Template:
        return Template("about.html")


async def init_http_session(app: Litestar):
    session = ClientSession()
    app.state.http = session
    app.state.client = TimetableClient(session=session)


async def close_http_session(app: Litestar):
    if (session := app.state.http) and not session.closed:
        await session.close()


cors_config = CORSConfig(
    allow_origins=[
        "https://chronicler.zeffo.me",
        "https://chronicler.up.railway.app",
        "127.0.0.1",
        "localhost",
        "192.168.1.254",
    ]
)
allowed_hosts = AllowedHostsConfig(
    allowed_hosts=[
        "chronicler.up.railway.app",
        "chronicler.zeffo.me",
        "localhost",
        "127.0.0.1",
        "192.168.1.254",
    ]
)

session_config = AsyncSessionConfig(expire_on_commit=False)
sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string=os.getenv("DATABASE_URL"),
    session_config=session_config,
)
sqlalchemy_plugin = SQLAlchemyInitPlugin(config=sqlalchemy_config)


async def on_startup() -> None:
    """Initializes the database."""
    return
    async with sqlalchemy_config.get_engine().begin() as conn:
        await conn.run_sync(UUIDBase.metadata.create_all)
        await conn.run_sync(UUIDAuditBase.metadata.create_all)


app = Litestar(
    route_handlers=[
        MainController,
        create_static_files_router(path="/static", directories=["static"]),
    ],
    template_config=TemplateConfig(
        directory=Path("templates"),
        engine=JinjaTemplateEngine,
    ),
    # plugins=[sqlalchemy_plugin],
    on_startup=[init_http_session, on_startup],
    on_shutdown=[close_http_session],
    cors_config=cors_config,
    allowed_hosts=allowed_hosts,
    middleware=[ServerSideSessionConfig().middleware],
    stores={"sessions": FileStore(path=Path("session_data"))},
)
