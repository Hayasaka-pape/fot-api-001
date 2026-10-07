import os
import re
from datetime import date as Date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Section = Literal["scoreboard", "stats", "lineup", "fixtures", "standings", "team", "league", "squad"]
MIN_POLL_SECONDS = 30


def configured_timezone():
    return os.getenv("TIMEZONE", "Asia/Tokyo")


def configured_timeout():
    # Let Pydantic parse the string instead of float() here: a bad .env value
    # must receive the same validation response as a bad explicit request.
    return os.getenv("FOTMOB_TIMEOUT", "10")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class Query(StrictModel):
    kind: Literal["match", "date", "team", "league"]
    id: str | None = None
    date: str | None = None
    timezone: str = Field(default_factory=configured_timezone)
    timeout: float = Field(default_factory=configured_timeout, ge=1, le=60)
    mode: Literal["demo", "live"] = "live"
    sections: list[Section] | None = Field(default=None, max_length=8)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("IANA タイムゾーンを指定してください（例: Asia/Tokyo）")
        return value

    @field_validator("id")
    @classmethod
    def valid_id(cls, value):
        if value is not None and not re.fullmatch(r"[0-9]{1,12}", value):
            raise ValueError("ID は 1〜12 桁の数字で指定してください")
        return value

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("日付は YYYY-MM-DD 形式で指定してください")
            Date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def required_target(self):
        if self.kind == "date" and not self.date:
            raise ValueError("日付別の検索には date が必要です")
        if self.kind != "date" and not self.id:
            raise ValueError("チーム・リーグ・試合の検索には id が必要です")
        return self


class MatchOptionsInput(StrictModel):
    date: str
    timezone: str = Field(default_factory=configured_timezone)
    timeout: float = Field(default_factory=configured_timeout, ge=1, le=60)
    mode: Literal["demo", "live"] = "live"

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        return Query.valid_date(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return Query.valid_timezone(value)

    def to_query(self):
        return Query(kind="date", date=self.date, timezone=self.timezone,
                     timeout=self.timeout, mode=self.mode, sections=["fixtures"])


def css_color(value):
    # General CSS expressions/URLs could load remote content in an exported OBS
    # file; accept a small portable set of literal colors instead.
    if not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})|(?:rgb|rgba)\([0-9.,%\s]+\)|transparent|black|white", value):
        raise ValueError("色は HEX、rgb、rgba 形式で指定してください")
    return value


class Canvas(StrictModel):
    width: int = Field(default=1920, ge=320, le=7680)
    height: int = Field(default=1080, ge=180, le=4320)
    background: str = "transparent"
    _color = field_validator("background")(css_color)


class Theme(StrictModel):
    accent: str = "#9df63a"
    background: str = "#0c1522"
    text: str = "#ffffff"
    opacity: float = Field(default=0.92, ge=0, le=1)
    _colors = field_validator("accent", "background", "text")(css_color)


class Widget(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    section: Section
    x: float = Field(ge=0, le=7680)
    y: float = Field(ge=0, le=4320)
    width: float = Field(ge=80, le=7680)
    height: float = Field(ge=40, le=4320)
    fontSize: int = Field(default=24, ge=10, le=96)


def default_widgets():
    return [
        Widget(id="scoreboard", section="scoreboard", x=48, y=48, width=960, height=170, fontSize=32),
        Widget(id="stats", section="stats", x=48, y=242, width=480, height=480),
        Widget(id="lineup", section="lineup", x=552, y=242, width=680, height=650),
        Widget(id="fixtures", section="fixtures", x=1256, y=48, width=616, height=600),
    ]


class SceneInput(StrictModel):
    id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    query: Query
    sections: list[Section] = Field(default_factory=lambda: ["scoreboard", "stats", "lineup"], max_length=8)
    canvas: Canvas = Field(default_factory=Canvas)
    theme: Theme = Field(default_factory=Theme)
    widgets: list[Widget] = Field(default_factory=default_widgets, max_length=24)
    # Keep 15-second saved scenes readable; renderers clamp actual polling to 30
    # rather than rejecting a previously valid scene when it is edited.
    pollInterval: int = Field(default=MIN_POLL_SECONDS, ge=15, le=3600)

    @model_validator(mode="after")
    def valid_layout(self):
        ids = [widget.id for widget in self.widgets]
        if len(ids) != len(set(ids)):
            raise ValueError("ウィジェット ID は重複できません")
        widget_sections = [widget.section for widget in self.widgets]
        # A section is resolved once in the preview. Multiple copies would make
        # its position ambiguous and diverge from the portable export renderer.
        if len(widget_sections) != len(set(widget_sections)) or len(self.sections) != len(set(self.sections)):
            raise ValueError("同じ項目はシーンに 1 つだけ配置できます")
        for widget in self.widgets:
            if widget.x + widget.width > self.canvas.width + 0.5 or widget.y + widget.height > self.canvas.height + 0.5:
                raise ValueError("ウィジェットはキャンバス内に配置してください")
        return self
