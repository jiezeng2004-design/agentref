from dataclasses import dataclass, field, asdict
from typing import Iterable, Literal, Mapping, Protocol
from pathlib import Path


@dataclass
class SessionIR:
    agent: str
    sessionId: str = ""
    title: str = ""
    cwd: str = ""
    createdAt: str = ""
    updatedAt: str = ""
    messages: list = field(default_factory=list)
    toolCalls: list = field(default_factory=list)
    fileOperations: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    testRuns: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    originalGoal: str = ""
    latestUserRequest: str = ""
    latestAgentState: str = "unknown"
    possibleTodos: list = field(default_factory=list)
    sourcePath: str = ""
    parseWarnings: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    unknownTypes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class AgentAdapter(Protocol):
    """Common index boundary; metadata hooks must never read session bodies."""
    agent: str
    roots: list[Path]
    index_mode: Literal["incremental", "snapshot"]
    def read_indexed(self, row: Mapping) -> SessionIR: ...
    def overlay_metadata(self, rows: list[dict]) -> None: ...
    def extractWorkspace(self, session: SessionIR) -> str: ...
    def getSessionStatus(self, session: SessionIR) -> str: ...


class IncrementalAdapter(AgentAdapter, Protocol):
    """File discovery, append parsing and source-specific cache repair."""
    def discoverSessions(self) -> list[Path]: ...
    def getSessionMetadata(self, path: Path) -> dict: ...
    def readSession(self, path: Path) -> SessionIR: ...
    def readSessionIncrementally(self, path: Path, offset: int = 0): ...
    def consume(self, session: SessionIR, record: dict) -> None: ...
    def metadata_needs_refresh(self, row: Mapping) -> bool: ...


class SnapshotSourceAdapter(AgentAdapter, Protocol):
    """Metadata snapshots and exact indexed reads (including virtual locators)."""
    scan_errors: list[str]
    def scan_metadata(self) -> Iterable[SessionIR]: ...
