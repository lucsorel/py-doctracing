from doctrace.doctrace import trace_to_puml

from tests.doctrace.test_ecoindex import ecoindex


def test_trace_to_puml():
    decorated_ecoindex = trace_to_puml(ecoindex)
    decorated_ecoindex(dom_elements_nb=960, requests_nb=70, size_kb=1500)

    assert False
