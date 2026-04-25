import asyncio


async def run_applescript(script: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode().strip())
    return stdout.decode().strip()


async def open_terminal(command: str | None = None) -> str:
    if command:
        safe = command.replace('"', '\\"')
        await run_applescript(f'tell application "Terminal" to do script "{safe}"')
    await run_applescript('tell application "Terminal" to activate')
    if command:
        return f"Terminal opened with command: {command}"
    return "Terminal opened"


async def open_chrome(url: str | None = None) -> str:
    if url:
        safe = url.replace('"', '%22')
        await run_applescript(f'tell application "Google Chrome" to open location "{safe}"')
    await run_applescript('tell application "Google Chrome" to activate')
    return f"Chrome opened: {url}" if url else "Chrome opened"


async def open_app(app_name: str) -> str:
    safe = app_name.replace('"', '\\"')
    await run_applescript(f'tell application "{safe}" to activate')
    return f"{app_name} opened"


async def set_volume(level: int) -> str:
    level = max(0, min(100, level))
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", f"set volume output volume {level}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return f"Volume set to {level}"


async def get_volume() -> int:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", "output volume of (get volume settings)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    try:
        return int(stdout.decode().strip())
    except ValueError:
        return 50
