import asyncio
from pathlib import Path


class WorkMode:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._output_path = "data/.jarvis_output.txt"
        Path("data").mkdir(exist_ok=True)

    async def start_task(self, prompt: str) -> str:
        if await self.is_running():
            await self.stop_task()

        Path(self._output_path).write_text("")

        out = open(self._output_path, "ab")
        self._process = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            stdout=out,
            stderr=out,
        )
        out.close()
        return "Task started. I will notify you when it is complete, sir."

    async def continue_task(self, prompt: str) -> str:
        out = open(self._output_path, "ab")
        self._process = await asyncio.create_subprocess_exec(
            "claude", "-p", "--continue", prompt,
            stdout=out,
            stderr=out,
        )
        out.close()
        return "Continuing the task."

    async def get_output(self) -> str:
        try:
            content = Path(self._output_path).read_text()
            return content[-500:] if len(content) > 500 else content
        except FileNotFoundError:
            return "No output available."

    async def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def stop_task(self) -> str:
        if self._process and self._process.returncode is None:
            self._process.terminate()
            await self._process.wait()
            return "Task stopped."
        return "No task running."
