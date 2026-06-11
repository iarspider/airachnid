"""
AIrachnid CLI — simple text interface for the agent.
Usage:
    uv run python cli.py
    uv run python cli.py --session my-session
"""

import asyncio
import argparse
import uuid

import httpx

from config import agent_settings

PROMPT = "You> "
THINKING = "🧠 ..."
AGENT_URL = f"http://localhost:{agent_settings.port}"


async def ask(message: str, session_id: str, user: str = "cli") -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{AGENT_URL}/invoke",
            json={"request": message, "session": session_id, "user": user},
        )
        resp.raise_for_status()
        return resp.json()


async def reindex(session_id: str) -> None:
    async with httpx.AsyncClient(timeout=300.0) as client:
        await client.post(
            f"{AGENT_URL}/reindex",
        )


async def main(session_id: str) -> None:
    print(f"🕷️  AIrachnid CLI  (session: {session_id})")
    print("Type your message. Commands: /reindex, /exit\n")

    while True:
        try:
            user_input = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
            print("Bye!")
            break

        if user_input.lower() == "/reindex":
            print("⏳ Reindexing...")
            try:
                await reindex(session_id)
                print("✅ Done!\n")
            except Exception as e:
                print(f"❌ Reindex failed: {e}\n")
            continue

        print(THINKING, end="\r")
        try:
            ans = await ask(user_input, session_id)
        except httpx.HTTPError as e:
            print(f"❌ Request failed: {e}\n")
            continue
        except Exception as e:
            print(f"❌ Unexpected error: {e}\n")
            continue

        # clear "thinking" line
        print(" " * len(THINKING), end="\r")

        if "error" in ans:
            print(f"❌ {ans['error']}\n")
        elif "text" in ans:
            print(f"🤖 {ans['text']}\n")
        else:
            print("❌ No answer from agent\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIrachnid CLI")
    parser.add_argument(
        "--session",
        default=str(uuid.uuid4()),
        help="Session ID (default: random UUID)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.session))
