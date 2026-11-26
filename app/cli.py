"""Command-line entry point (`python main.py ...`)."""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import List, Optional

from app.container import Container, build
from app.config import Settings

EPILOG = """
Examples:
  python main.py --ingest              # Ingest & index all documents in the knowledge folder
  python main.py --chat                # Start interactive chat in terminal
  python main.py --query "What is RAG?" # Ask a quick single question
  python main.py --serve               # Start the API + demo UI
  python main.py                       # Defaults to starting interactive chat
"""


def _print_result(r) -> None:
    print(f"\n🤖 Assistant:\n{r.answer}")
    sources = sorted({d.source for d in r.context})
    if sources:
        print(f"\n📑 Sources: {', '.join(sources)}")


def run_ingestion(c: Container) -> bool:
    print("\n🚀 Running document ingestion pipeline")
    n_docs, n_chunks = c.ingestion.reindex()
    if not n_docs:
        print(f"❌ No supported documents found in '{c.settings.knowledge_dir}/'.")
        return False
    print(f"🎉 Indexed {n_docs} documents into {n_chunks} chunks.")
    return True


def interactive_chat(c: Container, session_id: str) -> None:
    print("\n" + "=" * 65)
    print("💬 Conversational RAG ChatBot")
    print(f"📌 Session ID: {session_id}")
    print("💡 Commands: 'exit' to quit, 'clear' to reset memory")
    print("=" * 65)
    while True:
        try:
            text = input("\n👤 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            return
        if not text:
            continue
        if text.lower() in {"exit", "quit", "q"}:
            print("👋 Goodbye!")
            return
        if text.lower() == "clear":
            c.chat.clear(session_id)
            print(f"🧹 History cleared for session: {session_id}")
            continue
        try:
            _print_result(c.chat.handle_message(session_id, text))
        except Exception as e:
            print(f"\n❌ Error: {e}")


def main(argv: Optional[List[str]] = None) -> None:
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    p = argparse.ArgumentParser(description="🤖 Document Intelligence & Conversational RAG ChatBot",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG)
    p.add_argument("--ingest", action="store_true", help="Rebuild the vector index from the knowledge folder")
    p.add_argument("--chat", action="store_true", help="Interactive chat in the terminal")
    p.add_argument("--query", type=str, help="Ask one question and exit")
    p.add_argument("--session", type=str, default="cli_user", help="Session id (default: cli_user)")
    p.add_argument("--clear", action="store_true", help="Clear conversation memory for the session")
    p.add_argument("--docs-dir", type=str, help="Knowledge folder (default: KNOWLEDGE_DIR or 'knowledge')")
    p.add_argument("--serve", action="store_true", help="Start the FastAPI server and demo UI")
    p.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    args = p.parse_args(argv)

    if args.serve:
        import uvicorn

        print(f"\n🚀 Starting FastAPI server on http://127.0.0.1:{args.port}")
        print(f"📖 Swagger Docs: http://127.0.0.1:{args.port}/docs\n")
        uvicorn.run("api:app", host="0.0.0.0", port=args.port, reload=True)
        return

    settings = Settings.from_env()
    if args.docs_dir:
        settings = settings.with_overrides(knowledge_dir=Path(args.docs_dir))
    c = build(settings)

    if args.clear:
        c.chat.clear(args.session)
        if not (args.chat or args.query or args.ingest):
            return
    if args.ingest:
        if not run_ingestion(c):
            sys.exit(1)
        if not (args.chat or args.query):
            return
    if args.query:
        print(f"\n❓ Question: {args.query}")
        _print_result(c.chat.handle_message(args.session, args.query))
        return
    interactive_chat(c, args.session)
