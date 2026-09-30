"""
Quick Groq LLM connectivity test.
Run from the backend/ directory:
    python test_llm.py
"""
import asyncio
import sys
import os

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


async def main():
    print("=" * 55)
    print("  LLM Connectivity Test  —  Groq")
    print("=" * 55)

    if not GROQ_API_KEY:
        print("  GROQ_API_KEY is not set in .env")
        sys.exit(1)

    print(f"  Model  : {GROQ_MODEL}")
    print(f"  Key    : {GROQ_API_KEY[:12]}... (truncated)")
    print("-" * 55)

    try:
        from groq import AsyncGroq
    except ImportError:
        print("  'groq' package not installed. Run: python -m pip install groq")
        sys.exit(1)

    client = AsyncGroq(api_key=GROQ_API_KEY)

    print("  Sending test message to Groq ...")
    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=64,
            messages=[{"role": "user", "content": "Reply with exactly: LLM_OK"}],
        )
        text = response.choices[0].message.content or ""
        print(f"\n  Model replied: {text.strip()!r}")
        print("\n  LLM (Groq) is WORKING correctly!\n")

    except Exception as e:
        print(f"\n  LLM call FAILED: {type(e).__name__}: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
