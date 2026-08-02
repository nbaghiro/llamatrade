"""Local type stub correcting aiokafka's ``AbstractTokenProvider.token`` annotation.

aiokafka ships no ``py.typed``; pyright infers ``token``'s return as ``None`` from
its docstring-only abstract body, which makes any real (``-> str``) implementation
look like an incompatible override. The upstream docstring states it returns a
``str`` token — this stub encodes that so OAUTHBEARER providers type-check.
"""

import abc

class AbstractTokenProvider(abc.ABC):
    @abc.abstractmethod
    async def token(self) -> str: ...
    def extensions(self) -> dict[str, str]: ...
