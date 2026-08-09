from pathlib import Path
import subprocess
from typing import Any


class ToolRegistry:
    """
    Minimal software demo tool registry.

    Later can be replaced by:
    FileEditor
    ShellRunner
    TestRunner
    GitClient
    """

    def execute(
        self,
        tool_name: str,
        **kwargs: Any
    ) -> dict[str, Any]:

        if tool_name == "test_runner":

            command = kwargs.get(
                "command"
            )
            if not isinstance(command, str) or not command.strip():
                raise ValueError("test_runner requires a non-empty string command")

            cwd_arg = kwargs.get(
                "cwd",
                "."
            )
            cwd = Path(cwd_arg)


            result = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True
            )


            return {

                "tool": "test_runner",

                "success":
                    result.returncode == 0,

                "exit_code":
                    result.returncode,

                "stdout":
                    result.stdout,

                "stderr":
                    result.stderr,

                "arguments":{
                    "command":command
                }
            }


        raise ValueError(
            f"Unknown tool: {tool_name}"
        )
