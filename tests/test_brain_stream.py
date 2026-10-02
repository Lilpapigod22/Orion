from types import SimpleNamespace

from orion.brain import Brain
from tests.test_streaming import FakeStream, call, chunk

SCHEMA = {"type": "function", "function": {"name": "calculate", "description": "Maths",
                                           "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}}}}


class Tools:
    def names(self):
        return ["calculate"]

    def schemas(self, hidden=frozenset()):
        return [SCHEMA]

    def call(self, name, arguments):
        return "17 * 23 = 391"


class Knowledge:
    def build_context(self, text):
        return ""


class Memory:
    def last_user_text(self):
        return ""

    def last_assistant_text(self):
        return ""

    def as_messages(self):
        return []

    def add_turn(self, *args):
        pass


class Client:
    """First round: a tool call. Second round: the answer."""
    def __init__(self, rounds):
        self.rounds, self.kwargs = list(rounds), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        return self.rounds.pop(0)


def make_brain(client, stream=True):
    brain = Brain(Tools(), Knowledge(), Memory(), base_url="http://x", api_key="x", model="m", persona="p")
    brain.client, brain.stream = client, stream
    return brain


def test_streamed_think_reports_route_rounds_and_pieces():
    client = Client([FakeStream([chunk(calls=[call(0, "c1", "calculate", '{"expression": "17*23"}')])]),
                     FakeStream([chunk(content="17 по 23 "), chunk(content="са 391.")])])
    steps, pieces = [], []
    answer = make_brain(client).think("Колко е 17 по 23?", on_step=lambda kind, info: steps.append((kind, info)),
                                      on_delta=lambda kind, text: pieces.append(text))
    assert answer == "17 по 23 са 391."
    assert [kind for kind, _ in steps] == ["route", "model_start", "model_end", "model_start", "model_end"]
    assert "shown" in steps[0][1] and "hidden" in steps[0][1]
    end = steps[-1][1]
    assert end["round"] == 1 and end["tokens"] == 2 and end["tps"] >= 0
    assert pieces == ["17 по 23 ", "са 391."]
    assert all(k["stream"] is True for k in client.kwargs)


def test_test_mode_brain_does_not_stream_twice():
    message = SimpleNamespace(content="Добре.", tool_calls=None, model_extra={})
    client = Client([SimpleNamespace(choices=[SimpleNamespace(message=message)])])
    assert make_brain(client, stream=False).think("Здравей") == "Добре."
    assert "stream" not in client.kwargs[0]


def test_a_broken_step_observer_does_not_break_the_answer():
    client = Client([FakeStream([chunk(content="Добре.")])])
    def broken(kind, info):
        raise RuntimeError("window gone")
    assert make_brain(client).think("Здравей", on_step=broken) == "Добре."
