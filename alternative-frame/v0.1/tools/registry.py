from pathlib import Path
import subprocess


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
        **kwargs
    ):

        if tool_name == "test_runner":

            command = kwargs.get(
                "command"
            )

            cwd = kwargs.get(
                "cwd",
                "."
            )


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
