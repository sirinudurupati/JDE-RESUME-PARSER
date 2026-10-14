import io

from conftest import make_pdf

JD_PY = ("Job Title: Python Developer\nRequirements:\n- Python, SQL and FastAPI\n- 1 year of experience\n"
         "- Bachelor's degree\n")
JD_SF = ("Job Title: Salesforce Developer\nRequirements:\n- Apex, LWC and SOQL\n- 1 year of experience\n"
         "- Bachelor's degree\n")


def cv(i, skills):
    return (f"Person Number{chr(65 + i)} Test\nperson{i}@example.com | +91 90000 1000{i}\nSKILLS\n{skills}\n"
            f"EXPERIENCE\nDeveloper\nCo {i}\nJan 2023 - Dec 2024\n- Built apps with {skills.split(',')[0]}\n"
            f"EDUCATION\nB.Tech in Computer Science 2022\n")


def jde(client, text, reuse=None):
    data = {"file": (io.BytesIO(text.encode()), "jd.txt")}
    if reuse is not None:
        data["reuse_resumes"] = reuse
    r = client.post("/api/jobs/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def add(client, job_id, files):
    out = client.post(f"/api/jobs/{job_id}/resumes",
                      data={"files": [(io.BytesIO(make_pdf(t)), n) for n, t in files]},
                      content_type="multipart/form-data").get_json()["results"]
    assert all(x["status"] == "ok" for x in out), out


def cands(client, job_id):
    return client.get(f"/api/jobs/{job_id}/candidates").get_json()["candidates"]


def test_new_jd_scores_resumes_already_uploaded_and_old_jd_keeps_history(client):
    a = jde(client, JD_PY)["job"]["id"]
    add(client, a, [("a1.pdf", cv(0, "Python, SQL, FastAPI")), ("a2.pdf", cv(1, "Apex, LWC, SOQL, Salesforce"))])
    before = {c["name"]: c["overall"] for c in cands(client, a)}

    out = jde(client, JD_SF)                      # default: reuse the resumes already uploaded
    b = out["job"]["id"]
    assert out["carried"] == 2
    new = {c["name"]: c for c in cands(client, b)}
    assert len(new) == 2
    # the LATEST JD decides the ranking: the Salesforce person is now first
    ranked = sorted(new.values(), key=lambda c: -c["overall"])
    assert ranked[0]["filename"] == "a2.pdf" and ranked[0]["overall"] > ranked[1]["overall"]
    assert all(c["result"]["skills"][0]["name"] in ("apex", "lwc", "soql") for c in new.values())
    # old job untouched
    assert {c["name"]: c["overall"] for c in cands(client, a)} == before


def test_opt_out_and_idempotent_use_existing(client):
    a = jde(client, JD_PY)["job"]["id"]
    add(client, a, [("o1.pdf", cv(2, "Python, SQL"))])
    b = jde(client, JD_SF, reuse="0")["job"]["id"]
    assert cands(client, b) == []                                         # checkbox off: starts empty
    assert client.post(f"/api/jobs/{b}/use-existing-resumes").get_json()["carried"] >= 1
    n = len(cands(client, b))
    assert client.post(f"/api/jobs/{b}/use-existing-resumes").get_json()["carried"] == 0
    assert len(cands(client, b)) == n                                     # no duplicates the second time


def test_copies_are_independent_deleting_one_keeps_the_other(client):
    a = jde(client, JD_PY)["job"]["id"]
    add(client, a, [("d1.pdf", cv(3, "Python, SQL"))])
    b = jde(client, JD_SF)["job"]["id"]
    cb = [c for c in cands(client, b) if c["filename"] == "d1.pdf"][0]
    ca = [c for c in cands(client, a) if c["filename"] == "d1.pdf"][0]
    assert client.delete(f"/api/candidates/{cb['id']}").status_code == 200
    assert client.get(f"/api/candidates/{ca['id']}/file").status_code == 200       # original file still there


def test_pool_count_in_api(client):
    d = client.get("/api/jobs").get_json()["counts"]
    assert "distinct_resumes" in d and d["distinct_resumes"] >= 0
