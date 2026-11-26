import asyncio


def test_rag_turn_counts_and_remembers(container, retrieval):
    r1 = container.chat.handle_message("s", "What is JIBB?")
    assert r1.answer == "ANSWER: What is JIBB?" and r1.turn_count == 1 and not r1.trigger_lead_capture
    assert r1.source_names == ["site.md"]
    r2 = container.chat.handle_message("s", "Where is Tokyo office?")
    assert r2.turn_count == 2 and r2.trigger_lead_capture
    # second call saw the first exchange as history
    assert retrieval.calls[1][1] == [("user", "What is JIBB?"), ("assistant", "ANSWER: What is JIBB?")]


def test_lead_details_bypass_retrieval_and_enter_history(container, retrieval):
    container.chat.handle_message("s", "q1")
    container.chat.handle_message("s", "q2")
    r = container.chat.handle_message("s", "My name is Priya Sharma")
    assert r.is_lead_intake and not r.lead_complete and "Priya Sharma" in r.answer
    assert len(retrieval.calls) == 2
    hist = container.sessions.history("s")
    assert hist[-2].text == "My name is Priya Sharma" and "Priya Sharma" in hist[-1].text


def test_async_and_sessions_isolated(container):
    a = asyncio.run(container.chat.ahandle_message("a", "hello"))
    b = asyncio.run(container.chat.ahandle_message("b", "hello"))
    assert a.turn_count == 1 and b.turn_count == 1
    assert len(container.sessions.history("a")) == 2


def test_stream_saves_history_after_completion(container):
    stream = container.chat.start_stream("s", "What is JIBB?")
    assert stream.lead_reply is None and stream.turn_count == 1

    async def collect():
        return [ev.token async for ev in stream.events() if ev.kind == "token"]

    tokens = asyncio.run(collect())
    assert "".join(tokens).strip() == "ANSWER: What is JIBB?"
    assert stream.source_names == ["site.md"]
    assert [m.role for m in container.sessions.history("s")] == ["user", "assistant"]


def test_clear(container):
    container.chat.handle_message("s", "hi")
    container.chat.clear("s")
    assert container.sessions.history("s") == []
