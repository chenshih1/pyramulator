from collections.abc import Callable
from typing import Any, ClassVar, overload

class RequestType:
    READ: ClassVar[RequestType]
    WRITE: ClassVar[RequestType]
    REFRESH: ClassVar[RequestType]
    POWERDOWN: ClassVar[RequestType]
    SELFREFRESH: ClassVar[RequestType]
    EXTENSION: ClassVar[RequestType]

    @property
    def value(self) -> int: ...

class Config:
    @overload
    def __init__(self) -> None: ...
    @overload
    def __init__(self, config_file: str) -> None: ...
    def add(self, name: str, value: str) -> None: ...
    def contains(self, name: str) -> bool: ...
    def set_core_num(self, num: int) -> None: ...
    def __getitem__(self, name: str) -> str: ...
    def __contains__(self, name: str) -> bool: ...

class MemorySystem:
    def __init__(
        self, config: Config, cacheline: int = 64, num_cores: int = 1
    ) -> None: ...
    def tick(self) -> None: ...
    def drain_completed(self) -> list[tuple[Any, ...]]: ...
    def run(self, cycles: int) -> tuple[int, list[tuple[Any, ...]]]: ...
    def run_until_idle(
        self, max_cycles: int = 1000000
    ) -> tuple[int, list[tuple[Any, ...]]]: ...
    def send(
        self,
        addr: int,
        type: RequestType | int,
        core_id: int = 0,
        callback: Callable[..., Any] | None = None,
    ) -> bool: ...
    def send_batch(
        self,
        addrs: list[int],
        type: RequestType | int,
        core_id: int = 0,
        callback: Callable[..., Any] | None = None,
    ) -> list[bool]: ...
    def send_range(
        self,
        start: int,
        count: int,
        stride: int,
        type: RequestType | int,
        core_id: int = 0,
        callback: Callable[..., Any] | None = None,
    ) -> list[bool]: ...
    def drive(
        self,
        addrs: list[int],
        queue_depth: int = 32,
        batch: int = 100,
        max_cycles: int = 1000000,
        callback: Callable[..., Any] | None = None,
    ) -> tuple[int, int, list[tuple[Any, ...]]]: ...
    def drive_range(
        self,
        start: int,
        count: int,
        stride: int,
        queue_depth: int = 32,
        batch: int = 100,
        max_cycles: int = 1000000,
        callback: Callable[..., Any] | None = None,
    ) -> tuple[int, int, list[tuple[Any, ...]]]: ...
    def finish(self) -> None: ...
    def set_high_writeq_watermark(self, watermark: float) -> None: ...
    def set_low_writeq_watermark(self, watermark: float) -> None: ...
    @property
    def tck(self) -> float: ...
    @property
    def pending(self) -> int: ...
    def get_stats(self) -> dict[str, Any]: ...
    def reset_stats(self) -> None: ...
