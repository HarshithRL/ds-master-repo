from __future__ import annotations


class HeadingStack:
    def __init__(self) -> None:
        self._items: list[tuple[int, str]] = []

    def push(self, level: int, title: str) -> list[str]:
        while self._items and self._items[-1][0] >= level:
            self._items.pop()
        self._items.append((level, title))
        return self.path()

    def path(self) -> list[str]:
        return [title for _, title in self._items]
