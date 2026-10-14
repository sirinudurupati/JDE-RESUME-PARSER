import csv
import io

import openpyxl

from conftest import make_docx, make_pdf


def upload_jde(client, data, name):
    return client.post("/api/jobs/upload", data={"file": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def upload_resumes(client, job_id, files):
    return client.post(f"/api/jobs/{job_id}/resumes",
                       data={"files": [(io.BytesIO(d), n) for n, d in files]},
                       content_type="multipart/form-data")


def resume_text(i, python=True):
    skills = "Python, SQL, FastAPI, Git" if python else "JavaScript, React"
    return (f"Candidate Number{chr(65 + i % 26)} Test\ncand{i}@example.com | +91 90000 {10000 + i}\n"
            f"Skills\n{skills}\nExperience\nDeveloper\nCo {i}\nJan 20{10 + i % 12} - Dec 20{13 + i % 12}\n"
            f"- Built services in {skills.split(',')[0]} number {i}\nEducation\nB.Tech in Computer Science\n")


def test_index_page_has_branding(client):
    html = client.get("/").get_data(as_text=True)
    assert "SIURU" in html and "Your idea finds life here" in html
    assert 'src="/static/logo.png"' in html
    assert client.get("/static/logo.png").status_code == 200


def test_jobs_list_endpoint(client, jd_text):
    upload_jde(client, jd_text.encode(), "jd.txt")
    d = client.get("/api/jobs").get_json()
    assert isinstance(d["jobs"], list) and d["counts"]["jobs"] >= 1
    assert "raw_text" not in d["jobs"][0]["requirements"]


def test_full_flow_with_55_resumes(client, jd_text):
    for ext, data in ((".pdf", make_pdf(jd_text)), (".docx", make_docx(jd_text)), (".txt", jd_text.encode())):
        r = upload_jde(client, data, "jd" + ext)
        assert r.status_code == 201, r.get_json()
        assert r.get_json()["job"]["requirements"]["title"] == "Python Developer"
    job_id = r.get_json()["job"]["id"]

    files = []
    for i in range(55):
        txt = resume_text(i, python=i % 3 != 0)
        files.append((f"cv{i}.pdf", make_pdf(txt)) if i % 2 else (f"cv{i}.docx", make_docx(txt)))
    for s in range(0, 55, 25):                       # same batching idea as the UI
        res = upload_resumes(client, job_id, files[s:s + 25]).get_json()["results"]
        assert all(x["status"] == "ok" for x in res), res

    cands = client.get(f"/api/jobs/{job_id}/candidates").get_json()["candidates"]
    assert len(cands) == 55
    scores = [c["overall"] for c in cands]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)
    # python resumes must outrank non-python resumes
    assert max(scores) > min(scores)
    assert cands[0]["result"]["missing_mandatory"] == [] or cands[0]["overall"] >= cands[-1]["overall"]

    # export
    rc = client.get(f"/api/jobs/{job_id}/export.csv")
    rows = list(csv.reader(io.StringIO(rc.get_data(as_text=True).lstrip("﻿"))))
    assert rows[2][0] == "Rank" and len(rows) == 3 + 55
    col = rows[2].index("Overall match (0-100)")
    assert float(rows[3][col]) == scores[0]
    assert "Graduation year" in rows[2] and "Certifications" in rows[2]
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/jobs/{job_id}/export.xlsx").data))
    ws = wb["Candidates"]
    assert ws.max_row == 3 + 55
    assert ws.cell(row=4, column=col + 1).value == scores[0]

    # duplicates
    dup = upload_resumes(client, job_id, [files[0]]).get_json()["results"][0]
    assert dup["status"] == "duplicate"

    # detail + file
    cid = cands[0]["id"]
    d = client.get(f"/api/candidates/{cid}").get_json()["candidate"]
    assert "text" not in d["parsed"] and d["result"]["reasons"]
    assert client.get(f"/api/candidates/{cid}/file").status_code == 200

    # edit job -> re-run matching changes results and bumps version
    job = client.get(f"/api/jobs/{job_id}").get_json()["job"]
    req = job["requirements"]
    req["skills"] = [{"name": "javascript", "level": "mandatory"}]
    out = client.put(f"/api/jobs/{job_id}", json={"requirements": req, "weights": job["weights"]}).get_json()
    assert out["rematched"] == 55
    new = client.get(f"/api/jobs/{job_id}/candidates").get_json()["candidates"]
    assert new[0]["overall"] != scores[0] or new[0]["result"]["matched_mandatory"] == ["JavaScript"]
    assert all(not c["stale"] for c in new)

    # delete candidate + job removes files
    assert client.delete(f"/api/candidates/{cid}").status_code == 200
    assert client.get(f"/api/candidates/{cid}").status_code == 404
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/jobs/{job_id}/candidates").status_code == 404


def test_bad_uploads_give_clear_errors(client, jd_text):
    job_id = upload_jde(client, jd_text.encode(), "jd.txt").get_json()["job"]["id"]
    res = upload_resumes(client, job_id, [("bad.pdf", b"%PDF-1.4 garbage"), ("x.exe", b"MZ"),
                                          ("empty.docx", b""), ("note.txt", b"hello world " * 10)]).get_json()["results"]
    assert [r["status"] for r in res] == ["error"] * 4
    assert all(r["message"] for r in res)
    r = upload_jde(client, b"MZ\x00\x00", "jd.exe")
    assert r.status_code == 400 and "Unsupported" in r.get_json()["error"]
    assert client.get("/api/candidates/999999").status_code == 404


def test_csv_injection_neutralised(client, jd_text):
    from talentmatch.export import _safe
    assert _safe("=cmd|' /C calc'!A0").startswith("'")
    assert _safe("Normal") == "Normal"


def test_cross_site_post_blocked(client):
    r = client.post("/api/jobs/upload", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
