from time import time

from simple_github.util.types import BaseResponse


def is_rate_limited(resp: BaseResponse) -> bool:
    """
    Determine if a response indicates a rate limit has been reached.

    Checks the response headers and body to identify if the request was
    rate-limited. It handles both GraphQL and REST API responses, looking for
    specific status codes, headers, and error messages.

    Args:
        resp (Response): The HTTP response object to evaluate.

    Returns:
        bool: True if the response indicates a rate limit, False otherwise.
    """
    resource = resp.headers.get("x-ratelimit-resource")

    if resource == "graphql":
        if resp.status_code in (200, 403):
            data = resp.json()
            errors = data.get("errors", [])
            for error in errors:
                if (
                    error.get("type") == "RATE_LIMITED"
                    or error.get("extensions", {}).get("code") == "RATE_LIMITED"
                    or "rate limit" in error.get("message", "").lower()
                ):
                    return True

    elif resp.status_code in (403, 429):
        if resp.headers.get("x-ratelimit-remaining") == "0" or resp.headers.get(
            "retry-after"
        ):
            return True

        try:
            data = resp.json()
            message = data.get("message", "").lower()
            if "rate limit exceeded" or "too many requests" in message:
                return True
        except ValueError:
            pass

    return False


def get_wait_time(resp: BaseResponse, attempt: int = 1) -> int:
    """
    Calculate the wait time before retrying a request after hitting a rate limit.

    Determines the appropriate wait time based on the response headers and the
    number of retry attempts. It prioritizes the `x-ratelimit-reset` and
    `retry-after` headers if available, and falls back to a default wait time
    strategy otherwise.

    Args:
        resp (Response): The HTTP response object containing rate limit headers.
        attempt (int): The current retry attempt number (default is 1).

    Returns:
        int: The calculated wait time in seconds.
    """
    attempt = max(attempt, 1)
    remaining = resp.headers.get("x-ratelimit-remaining")
    reset = resp.headers.get("x-ratelimit-reset")
    retry_after = resp.headers.get("retry-after")

    if remaining == "0" and reset:
        wait_time = max(0, int(reset) - int(time()))
    elif retry_after:
        wait_time = int(retry_after)
    else:
        # If the `x-ratelimit-reset` or `retry-after` headers aren't set, then
        # the recommendation is to wait at least one minute and increase the
        # interval with each new attempt.
        wait_time = 60 + (20 * (attempt - 1))

    return wait_time
