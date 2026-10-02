from orion import reflexes


def test_quick_command_is_recognised():
    reflex = reflexes.respond("Хвърли монета")
    assert reflex is not None and reflex.tool == "flip_coin"
