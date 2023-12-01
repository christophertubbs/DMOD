"""
@TODO: Put a module wide description here
"""
from __future__ import annotations

import typing


class CaseInsensitiveString(str):
    @classmethod
    def of(cls, value: str) -> CaseInsensitiveString:
        return cls(value)

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return super().lower() == other.lower()

        return super().__eq__(other)

    def __ne__(self, other) -> bool:
        if isinstance(other, str):
            return super().lower() != other.lower()

        return super().__ne__(other)

    def __lt__(self, other) -> bool:
        if isinstance(other, str):
            return super().lower() < other.lower()

        return super().__lt__(other)

    def __le__(self, other: str) -> bool:
        if isinstance(other, str):
            return super().lower() <= other.lower()

        return super().__le__(other)

    def __gt__(self, other) -> bool:
        if isinstance(other, str):
            return super().lower() > other.lower()

        return super().__gt__(other)

    def __ge__(self, other) -> bool:
        if isinstance(other, str):
            return super().lower() >= other.lower()

        return super().__ge__(other)

    def capitalize(self) -> str:
        return self.of(super().capitalize())

    def casefold(self) -> str:
        return self.of(super().casefold())

    def center(self, __width: typing.SupportsIndex, __fillchar: str = ...) -> str:
        return self.of(super().center(__width, __fillchar))

    def endswith(
        self, __suffix: str | typing.Tuple[str, ...], __start: typing.SupportsIndex | None = ..., __end: typing.SupportsIndex | None = ...
    ) -> bool:
        return super().lower().endswith(
            __suffix.lower() if isinstance(__suffix, str) else (suffix.lower() for suffix in __suffix),
            __start,
            __end
        )

    def expandtabs(self, tabsize: typing.SupportsIndex = ...) -> str:
        return self.of(super().expandtabs(tabsize))

    def find(self, sub, start=None, end=None) -> int:
        return super().lower().find(sub.lower(), start, end)

    def format(self, *args: object, **kwargs: object) -> str:
        return self.of(super().format(*args, **kwargs))

    def format_map(self, map: typing.Mapping) -> str:
        return self.of(super().format_map(map))

    def index(self, sub, start=None, end=None):
        return super().lower().index(sub.lower(), start, end)

    def join(self, __iterable: typing.Iterable[str]) -> str:
        return self.of(super().join(__iterable))

    def ljust(self, __width: typing.SupportsIndex, __fillchar: str = ...) -> str:
        return self.of(super().ljust(__width, __fillchar))

    def lower(self) -> str:
        return self.of(super().lower())

    def lstrip(self, __chars: str | None = ...) -> str:
        return self.of(super().lstrip(__chars))

    def partition(self, __sep: str) -> tuple[str, str, str]:
        beginning, middle, end = super().partition(__sep)
        return (
            self.of(beginning) if isinstance(beginning, str) else beginning,
            self.of(middle) if isinstance(middle, str) else middle,
            self.of(end) if isinstance(end, str) else end
        )

    def removeprefix(self, __prefix: str) -> str:
        return self.of(super().removeprefix(__prefix))

    def removesuffix(self, __suffix: str) -> str:
        return self.of(super().removesuffix(__suffix))

    def replace(self, __old: str, __new: str, __count: typing.SupportsIndex = ...) -> str:
        return self.of(super().replace(__old, __new, __count))

    def rfind(self, __sub: str, __start: typing.SupportsIndex | None = ..., __end: typing.SupportsIndex | None = ...) -> int:
        return super().lower().rfind(__sub.lower(), __start, __end)

    def rindex(self, __sub: str, __start: typing.SupportsIndex | None = ..., __end: typing.SupportsIndex | None = ...) -> int:
        return super().lower().rfind(__sub.lower(), __start, __end)

    def rjust(self, __width: typing.SupportsIndex, __fillchar: str = ...) -> str:
        return self.of(super().rjust(__width, __fillchar))

    def rpartition(self, __sep: str) -> tuple[str, str, str]:
        beginning, middle, end = super().rpartition(__sep)
        return (
            self.of(beginning) if isinstance(beginning, str) else beginning,
            self.of(middle) if isinstance(middle, str) else middle,
            self.of(end) if isinstance(end, str) else end
        )

    def rsplit(self, sep: str | None = ..., maxsplit: typing.SupportsIndex = ...) -> list[str]:
        return [
            self.of(part)
            for part in super().rsplit(sep, maxsplit)
        ]

    def rstrip(self, __chars: str | None = ...) -> str:
        return self.of(super().rstrip(__chars))

    def split(self, sep: str | None = ..., maxsplit: typing.SupportsIndex = ...) -> list[str]:
        return [
            self.of(part)
            for part in super().split(sep, maxsplit)
        ]

    def splitlines(self, keepends: bool = ...) -> list[str]:
        return [
            self.of(part)
            for part in super().splitlines(keepends)
        ]

    def startswith(
        self, __prefix: str | typing.Tuple[str, ...], __start: typing.SupportsIndex | None = ..., __end: typing.SupportsIndex | None = ...
    ) -> bool:
        if isinstance(__prefix, str):
            return super().lower().startswith(__prefix.lower(), __start, __end)
        else:
            return super().lower().startswith(tuple(prefix.lower() for prefix in __prefix), __start, __end)

    def swapcase(self) -> str:
        return self.of(super().swapcase())

    def title(self) -> str:
        return self.of(super().title())

    def translate(self, __table: typing.Mapping[int, int | str | None] | typing.Sequence[int | str | None]) -> str:
        return self.of(super().translate(__table))

    def upper(self) -> str:
        return self.of(super().upper())

    def zfill(self, __width: typing.SupportsIndex) -> str:
        return self.of(super().zfill(__width))

    def __add__(self, other):
        return self.of(super().__add__(other))

    def __hash__(self):
        return hash(super().lower())