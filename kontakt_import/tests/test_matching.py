from yuvomi_import.matching import find_existing, name_key


def _idx():
    return {
        name_key("Brigitte", "Giese"): {"id": 1},
        name_key("Hans Erich", "Giese"): {"id": 2},
        name_key("Susanne", "Stephan"): {"id": 3},
        name_key("Eva", "Feuser"): {"id": 4},
    }


def test_titel_werden_ignoriert():
    assert find_existing(_idx(), name_key("Oma Brigitte", "Giese"))["id"] == 1
    assert find_existing(_idx(), name_key("Opa Hans Erich", "Giese"))["id"] == 2


def test_zusatzname_in_klammern():
    assert find_existing(_idx(), name_key("Susanne (Susi)", "Stephan"))["id"] == 3


def test_gleicher_vorname_anderer_nachname_ist_neu():
    assert find_existing(_idx(), name_key("Eva", "Giese")) is None
    assert find_existing(_idx(), name_key("Martina", "Stephan")) is None
