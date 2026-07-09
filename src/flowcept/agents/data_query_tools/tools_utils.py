"""Shared retry loop for query runtime errors.

Covers only errors raised when *executing* a generated query — pandas runtime
errors for the DF path and MongoDB OperationFailure for the DB path.

Out of scope: JSON/code parse errors, LLM output format errors, network errors,
auth errors, and schema validation errors.
"""


def query_runtime_retry(execute_fn, fix_fn, max_attempts: int = 3):
    """Run *execute_fn*; on runtime error call *fix_fn* to get a corrected
    callable and retry, up to *max_attempts* total attempts.

    Parameters
    ----------
    execute_fn : callable
        Parameterless callable that executes the query.  Returns a value on
        success; raises an exception on query runtime error.
    fix_fn : callable(exc, attempt) -> new_execute_fn
        Called with the caught exception and the zero-based attempt index.
        Must return a new (or updated) parameterless callable that re-runs the
        corrected query.  Raise from *fix_fn* to signal that the error is
        unrecoverable — no further retries will be made.
    max_attempts : int, optional
        Total number of attempts, including the first.  Default is 3.

    Returns
    -------
    object
        Whatever the first successful *execute_fn* call returns.

    Raises
    ------
    Exception
        Re-raises the last caught exception when all attempts are exhausted or
        *fix_fn* itself raises.
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return execute_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                try:
                    execute_fn = fix_fn(exc, attempt)
                except Exception:
                    break
    raise last_exc
