from types import SimpleNamespace

import pytest

from orion import streaming


def chunk(content=None, reasoning=None, calls=None):
    delta = SimpleNamespace(content=content, model_extra={"reasoning": reasoning} if reasoning else {}, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def call(index, id=None, name=None, args=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))


class FakeStream:
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    def __iter__(self):
        return iter(self.chunks)

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, chunks):
        self.stream = FakeStream(chunks)
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.stream


def test_pieces_are_joined_like_a_normal_answer():
    client = FakeClient([chunk(reasoning="Мисля "), chunk(reasoning="малко."), chunk(content="17 по 23 "), chunk(content="са 391.")])
    seen = []
    reply = streaming.create_streamed(client, on_delta=lambda kind, text: seen.append((kind, text)), model="m", messages=[])
    message = reply.choices[0].message
    assert message.content == "17 по 23 са 391."
    assert message.model_extra == {"reasoning": "Мисля малко."}
    assert message.tool_calls is None
    assert seen == [("reasoning", "Мисля "), ("reasoning", "малко."), ("content", "17 по 23 "), ("content", "са 391.")]
    assert client.kwargs["stream"] is True and client.kwargs["model"] == "m"
    assert client.stream.closed


def test_tool_call_pieces_are_merged():
    client = FakeClient([chunk(calls=[call(0, "c1", "calcu", '{"expr')]), chunk(calls=[call(0, None, "late", 'ession": "1+1"}')])])
    message = streaming.create_streamed(client).choices[0].message
    assert len(message.tool_calls) == 1
    assert message.tool_calls[0].id == "c1"
    assert message.tool_calls[0].function.name == "calculate"
    assert message.tool_calls[0].function.arguments == '{"expression": "1+1"}'


def test_a_broken_observer_does_not_break_the_answer():
    client = FakeClient([chunk(content="а"), chunk(content="б")])
    def broken(kind, text):
        raise RuntimeError("window gone")
    assert streaming.create_streamed(client, on_delta=broken).choices[0].message.content == "аб"


def test_check_stops_the_stream_and_closes_it():
    class Interrupted(Exception):
        pass
    client = FakeClient([chunk(content="а"), chunk(content="б")])
    calls = iter([None, None, Interrupted])
    with pytest.raises(Interrupted):
        streaming.create_streamed(client, check=lambda: next(calls))
    assert client.stream.closed
