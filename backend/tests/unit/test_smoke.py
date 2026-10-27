import charie
import charie.chat
import charie.learner
import charie.shared


def test_package_imports():
    assert charie is not None
    assert charie.shared is not None
    assert charie.learner is not None
    assert charie.chat is not None
