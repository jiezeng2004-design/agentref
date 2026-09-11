from dataclasses import dataclass, field, asdict
from typing import Protocol
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
    agent: str
    def discoverSessions(self) -> list[Path]: ...
    def getSessionMetadata(self, path: Path) -> dict: ...
    def readSession(self, path: Path) -> SessionIR: ...
    def readSessionIncrementally(self, path: Path, offset: int = 0): ...
    def extractWorkspace(self, session: SessionIR) -> str: ...
    def getSessionStatus(self, session: SessionIR) -> str: ...
