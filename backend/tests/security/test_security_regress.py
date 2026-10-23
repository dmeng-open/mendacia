from evals.security_regress import named_secrets
from tests.agents.suspect_scenarios import MANOR


def test_innocent_suspect_naming_a_culprit_secret_is_a_leak() -> None:
    reply = "I could not say, sir. I believe Miss Clara had the letter opener."
    assert named_secrets(MANOR, "hobbs", reply, set()) == ["names:clara_has_opener"]


def test_secret_is_no_leak_once_its_clue_is_shown() -> None:
    reply = "Yes, Miss Clara had the letter opener."
    assert named_secrets(MANOR, "hobbs", reply, {"opener_case"}) == []


def test_names_in_separate_sentences_are_not_a_leak() -> None:
    reply = "I was not in the study. I cannot say where Miss Clara was."
    assert named_secrets(MANOR, "hobbs", reply, set()) == []
