from aiohttp import ClientSession
from yarl import URL
from datetime import datetime, timedelta
from io import StringIO
from pydantic import BaseModel, Field, BeforeValidator
import csv

from typing import Annotated, Any, ClassVar


BASE_URL = URL("http://time-table.sicsr.ac.in/report.php")


def dt_conv(raw: str) -> datetime:
    return datetime.strptime(raw, "%H:%M:%S - %A %d %B %Y")


def td_conv(raw: str) -> timedelta:
    """Input format is `1 hours`"""
    val, unit = raw.split()
    return timedelta(**{unit: float(val)})


def fmtdt(dt: datetime):
    return dt.strftime("%H:%M %d/%m")


DateTime = Annotated[datetime, BeforeValidator(dt_conv)]


class Entry(BaseModel):
    brief_desc: str = Field(validation_alias="Brief description")
    area: str = Field(validation_alias="Area")
    room: int = Field(validation_alias="Room")
    start: DateTime = Field(validation_alias="Start time")
    end: DateTime = Field(validation_alias="End time")
    duration: Annotated[timedelta, BeforeValidator(td_conv)] = Field(
        validation_alias="Duration"
    )
    full_desc: str = Field(validation_alias="Full Description")
    type: str = Field(validation_alias="Type")
    creator: str = Field(validation_alias="Created by")
    status: str = Field(validation_alias="Confirmation status")
    last_updated: DateTime = Field(validation_alias="Last updated")

    def url(self) -> str:
        return f'<a href="/search?room={self.room}&start={self.start.hour}&end={self.end.hour}</a>'

    def dump(self) -> dict[str, Any]:
        return {
            "start": fmtdt(self.start),
            "end": fmtdt(self.end),
            "class": self.full_desc,
            "room": self.room,
            "duration": self.duration.seconds // 60,
        }

    dump_fields: ClassVar[list[str]] = [
        "start",
        "end",
        "class",
        "room",
        "duration",
    ]

    def __str__(self):
        return f"{fmtdt(self.start)} - {fmtdt(self.end)}: {self.full_desc} ({self.duration}) - {self.status}"


def build_url(
    start: datetime,
    end: datetime,
    *,
    areamatch: str = "",
    roommatch: str = "",
    typematch: list[str] = [],
    namematch: str = "",
    descrmatch: str = "",
    creatormatch: str = "",
    match_confirmed: int = 2,
    output: int = 0,
    output_format: int = 1,
    sortby: str = "s",
    sumby: str = "d",
    phase: int = 2,
    datatable: int = 1,
):
    def zpad(value: int) -> str:
        return f"{value:02}"

    return BASE_URL % {
        "from_day": zpad(start.day),
        "from_month": zpad(start.month),
        "from_year": start.year,
        "to_day": zpad(end.day),
        "to_month": zpad(end.month),
        "to_year": end.year,
        "areamatch": areamatch,
        "roommatch": roommatch,
        "typematch[]": typematch,
        "namematch": namematch,
        "descrmatch": descrmatch,
        "creatormatch": creatormatch,
        "match_confirmed": match_confirmed,
        "output": output,
        "output_format": output_format,
        "sortby": sortby,
        "sumby": sumby,
        "phase": phase,
        "datatable": datatable,
    }


async def _request(
    start: datetime,
    end: datetime,
    *,
    areamatch: str = "",
    roommatch: str = "",
    typematch: list[str] = [],
    namematch: str = "",
    descrmatch: str = "",
    creatormatch: str = "",
    match_confirmed: int = 2,
    session: ClientSession,
):
    url = build_url(
        start,
        end,
        areamatch=areamatch,
        roommatch=roommatch,
        typematch=typematch,
        namematch=namematch,
        descrmatch=descrmatch,
        creatormatch=creatormatch,
        match_confirmed=match_confirmed,
    )
    resp = await session.get(url)
    data = await resp.text()
    return StringIO(data)


async def fetch_report(
    start: datetime,
    end: datetime,
    *,
    areamatch: str = "",
    roommatch: str = "",
    typematch: list[str] = [],
    namematch: str = "",
    descrmatch: str = "",
    creatormatch: str = "",
    match_confirmed: int = 2,
    session: ClientSession,
):
    reader = csv.DictReader(
        await _request(
            start,
            end,
            areamatch=areamatch,
            roommatch=roommatch,
            typematch=typematch,
            namematch=namematch,
            descrmatch=descrmatch,
            creatormatch=creatormatch,
            match_confirmed=match_confirmed,
            session=session,
        )
    )
    return reader


async def fetch(
    start: datetime,
    end: datetime,
    *,
    areamatch: str = "",
    roommatch: str = "",
    typematch: list[str] = [],
    namematch: str = "",
    descrmatch: str = "",
    creatormatch: str = "",
    match_confirmed: int = 2,
    session: ClientSession,
):
    reader = await fetch_report(
        start,
        end,
        areamatch=areamatch,
        roommatch=roommatch,
        typematch=typematch,
        namematch=namematch,
        descrmatch=descrmatch,
        creatormatch=creatormatch,
        match_confirmed=match_confirmed,
        session=session,
    )
    return map(lambda row: Entry.model_validate(row), reader)


class TimetableClient:
    def __init__(self, session: ClientSession):
        self.session = session
        self.__types: set[str] = set()

    async def get_types(self):
        if not self.__types:
            start = datetime.now()
            end = start + timedelta(weeks=4)
            self.__types = {e.type for e in await self.fetch(start, end)}
        items = list(self.__types)
        items.sort()
        return items

    async def fetch(
        self,
        start: datetime,
        end: datetime,
        *,
        areamatch: str = "",
        roommatch: str = "",
        typematch: list[str] = [],
        namematch: str = "",
        descrmatch: str = "",
        creatormatch: str = "",
        match_confirmed: int = 2,
    ) -> list[Entry]:
        # TODO: add caching here
        return list(
            await fetch(
                start,
                end,
                areamatch=areamatch,
                roommatch=roommatch,
                typematch=typematch,
                namematch=namematch,
                descrmatch=descrmatch,
                creatormatch=creatormatch,
                match_confirmed=match_confirmed,
                session=self.session,
            )
        )
