"""
Utils for invoking subprocess calls
"""
import os

import logging
from time import sleep

import sys
from subprocess import Popen, PIPE

from typing import Callable, Dict, Any, Optional, Union, AnyStr, IO

from samcli.commands.exceptions import UserException
from samcli.lib.utils.stream_writer import StreamWriter

LOG = logging.getLogger(__name__)


class LoadingPatternError(UserException):
    def __init__(self, ex):
        self.ex = ex
        message_fmt = f"Failed to execute the subprocess. {ex}"
        super().__init__(message=message_fmt.format(ex=self.ex))


def default_loading_pattern(stream_writer: Optional[StreamWriter] = None, loading_pattern_rate: float = 0.5) -> None:
    """
    A loading pattern that just prints '.' to the terminal

    Parameters
    ----------
    stream_writer: Optional[StreamWriter]
        The stream to which to write the pattern
    loading_pattern_rate: int
        How frequently to generate the pattern
    """
    stream_writer = stream_writer or StreamWriter(sys.stderr)
    stream_writer.write(".")
    stream_writer.flush()
    sleep(loading_pattern_rate)


def invoke_subprocess_with_loading_pattern(
    command_args: Dict[str, Any],
    loading_pattern: Callable[[StreamWriter], None] = default_loading_pattern,
    stream_writer: Optional[StreamWriter] = None,
) -> Optional[Union[str, bytes]]:
    """
    Wrapper for Popen to asynchronously invoke a subprocess while
    printing a given pattern until the subprocess is complete.
    If the log level is lower than INFO, stream the process stdout instead.

    Parameters
    ----------
    command_args: Dict[str, Any]
        The arguments to give to the Popen call, should contain at least one parameter "args"
    loading_pattern: Callable[[StreamWriter], None]
        A function generating a pattern to the given stream
    stream_writer: Optional[StreamWriter]
        The stream to which to write the pattern

    Returns
    -------
    str
        A string containing the process output
    """
    stream_writer = stream_writer or StreamWriter(sys.stderr)
    process_output = ""

    if not command_args.get("stdout"):
        # Default stdout to PIPE if not specified so
        # that output isn't printed along with dots
        command_args["stdout"] = PIPE

    try:
        # Popen is async as opposed to run so we can print while we wait
        with Popen(**command_args) as process:
            if LOG.getEffectiveLevel() >= logging.INFO:
                # process.poll() returns None until the process exits
                while process.poll() is None:
                    loading_pattern(stream_writer)
            elif process.stdout:
                # Logging level is DEBUG, streaming logs instead
                for line in process.stdout:
                    decoded_line = _check_and_process_bytes(line)
                    LOG.debug(decoded_line)
                    process_output += decoded_line

            return_code = process.wait()

            stream_writer.write(os.linesep)
            stream_writer.flush()

            if not process_output:
                process_output = _check_and_convert_stream_to_string(process.stdout)

            process_stderr = _check_and_convert_stream_to_string(process.stderr)

            if return_code:
                raise LoadingPatternError(
                    f"The process {command_args.get('args', [])} returned a "
                    f"non-zero exit code {process.returncode}. {process_stderr}"
                )

    except (OSError, ValueError) as e:
        raise LoadingPatternError(f"Subprocess execution failed {command_args.get('args', [])}. {e}") from e

    return process_output


def _check_and_convert_stream_to_string(stream: Optional[IO[AnyStr]]) -> str:
    stream_as_str = ""
    if stream:
        byte_stream = stream.read()
        stream_as_str = _check_and_process_bytes(byte_stream)
    return stream_as_str


def _check_and_process_bytes(check_value: AnyStr) -> str:
    if isinstance(check_value, bytes):
        return check_value.decode("utf-8").strip()
    return check_value