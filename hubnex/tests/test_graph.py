from fastapi.testclient import TestClient

from hubnex.graph import build_graph
from hubnex.main import create_app


async def test_graph_links_knowledge_to_agents_and_shared_keywords(make_hq):
    hq = make_hq([])
    await hq.store.remember("work", "Listino caldaie", "Prezzi caldaie a condensazione fornitore Bianchi", "sales")
    await hq.store.remember("work", "Manutenzione caldaie", "Controllo annuale caldaie cliente condominio", "technical")
    await hq.store.remember("global", "Preferenza", "Il signore preferisce risposte brevi")  # no author
    did = await hq.store.deadline_add("Revisione caldaie condominio", "2026-11-20", "work", "technical")
    tid = await hq.store.task_start("technical", "Verifica norma caldaie", "user")
    await hq.store.task_finish(tid, "done", "Controllo semestrale obbligatorio")

    g = await build_graph(hq)
    ids = {n["id"] for n in g["nodes"]}
    edges = {(l["source"], l["target"]) for l in g["links"]}

    assert {"jarvis", "c:work", "d:work/sales", "a:mail"} <= ids
    assert ("a:sales", "m:1") in edges and ("a:technical", "m:2") in edges
    assert ("jarvis", "m:3") in edges  # global memory without author hangs off Jarvis
    assert ("a:technical", f"s:{did}") in edges and ("a:technical", f"t:{tid}") in edges
    # "caldaie" appears everywhere -> a keyword that ties the knowledge together
    assert "k:caldaie" in ids
    assert {("m:1", "k:caldaie"), ("m:2", "k:caldaie"), (f"s:{did}", "k:caldaie")} <= edges
    assert "k:signore" not in ids  # stopwords never become keywords
    assert g["stats"]["memories"] == 3 and g["stats"]["nodes"] == len(g["nodes"])


def test_graph_endpoint(settings, make_hq):
    app = create_app(settings, hq=make_hq([]), start_workers=False)
    with TestClient(app) as client:
        g = client.get("/api/graph").json()
        assert g["stats"]["nodes"] > 10 and g["links"]
