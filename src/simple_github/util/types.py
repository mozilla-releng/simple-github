from typing import Any, Coroutine, Dict, Optional, Union

from aiohttp import ClientResponse
from requests import Response as RequestsResponse

Response = Union[RequestsResponse, ClientResponse]
RequestData = Optional[Dict[str, Any]]

# Implementations of the base class can be either sync or async.
BaseDict = Union[Dict[str, Any], Coroutine[None, None, Dict[str, Any]]]
BaseNone = Union[None, Coroutine[None, None, None]]
BaseResponse = Union[Response, Coroutine[None, None, Response]]
