"""Flask app factory + JSON API + the single dashboard page."""
import os
from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from . import config, export, service, storage
from .config import normalize_weights
from .extract import ExtractionError

ROOT = config.BASE_DIR


def create_app():
    app = Flask(__name__, template_folder=str(ROOT / "templates"),
                static_folder=str(ROOT / "static"))
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_REQUEST_MB * 1024 * 1024
    app.config["MAX_FORM_PARTS"] = 5000
    storage.init()

    @app.before_request
    def csrf_guard():
        # Cross-site form posts carry an Origin header that differs from our own host.
        if request.method in ("POST", "PUT", "DELETE") and request.headers.get("Origin"):
            if urlparse(request.headers["Origin"]).netloc != request.host:
                abort(403)

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "frame-ancestors 'self'")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error=f"Upload too large (limit {config.MAX_REQUEST_MB} MB per request)."), 413

    @app.errorhandler(403)
    def forbidden(_):
        return jsonify(error="Forbidden."), 403

    @app.errorhandler(404)
    def missing(_):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return "Not found", 404

    def need_job(job_id):
        job = storage.get_job(job_id)
        if not job:
            abort(404)
        return job

    # ------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return render_template("index.html", max_file_mb=config.MAX_FILE_MB,
                               batch=config.MAX_FILES_PER_REQUEST)

    @app.get("/api/config")
    def api_config():
        return jsonify(weights=config.DEFAULT_WEIGHTS, labels=config.CATEGORY_LABELS,
                       counting=config.DEFAULT_EXPERIENCE_COUNTING,
                       type_labels=config.EXPERIENCE_TYPE_LABELS,
                       max_file_mb=config.MAX_FILE_MB, max_files=config.MAX_FILES_PER_REQUEST,
                       **storage.counts())

    # -------------------------------------------------------------- jobs
    @app.get("/api/jobs")
    def api_jobs():
        jobs = storage.list_jobs()
        for j in jobs:
            j["requirements"].pop("raw_text", None)
        return jsonify(jobs=jobs, counts=storage.counts())

    @app.post("/api/jobs/upload")
    def api_job_upload():
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify(error="Choose a job description file (PDF, DOCX or TXT)."), 400
        data = f.read(config.MAX_FILE_MB * 1024 * 1024 + 1)
        if len(data) > config.MAX_FILE_MB * 1024 * 1024:
            return jsonify(error=f"File larger than {config.MAX_FILE_MB} MB."), 400
        try:
            job_id, _ = service.create_job_from_upload(f.filename, data)
        except ExtractionError as e:
            return jsonify(error=str(e)), 400
        job = storage.get_job(job_id)
        job["requirements"].pop("raw_text", None)
        return jsonify(job=job), 201

    @app.get("/api/jobs/<int:job_id>")
    def api_job(job_id):
        job = need_job(job_id)
        job["requirements"].pop("raw_text", None)
        return jsonify(job=job)

    @app.put("/api/jobs/<int:job_id>")
    def api_job_update(job_id):
        job = need_job(job_id)
        body = request.get_json(silent=True) or {}
        req = service.clean_requirements(body.get("requirements", {}), job["requirements"])
        if not req["title"]:
            return jsonify(error="Job title is required."), 400
        weights = normalize_weights(body.get("weights"))
        storage.update_job(job_id, req["title"], req, weights)
        n = service.rematch_job(job_id)
        job = storage.get_job(job_id)
        job["requirements"].pop("raw_text", None)
        return jsonify(job=job, rematched=n)

    @app.post("/api/jobs/<int:job_id>/reextract")
    def api_reextract(job_id):
        """Re-run the JD parser on the stored document text (discards manual edits)."""
        from .jde_parser import parse_jde
        import unicodedata
        job = need_job(job_id)
        raw = unicodedata.normalize("NFKC", job["requirements"].get("raw_text", ""))
        if not raw.strip():
            return jsonify(error="The original document text is not available."), 400
        req = parse_jde(raw)
        req["raw_text"] = raw
        storage.update_job(job_id, req["title"] or job["title"], req, job["weights"])
        with storage.db() as c:
            c.execute("UPDATE jobs SET reviewed=0 WHERE id=?", (job_id,))
        n = service.rematch_job(job_id)
        job = storage.get_job(job_id)
        job["requirements"].pop("raw_text", None)
        return jsonify(job=job, rematched=n)

    @app.post("/api/jobs/<int:job_id>/rematch")
    def api_rematch(job_id):
        need_job(job_id)
        return jsonify(rematched=service.rematch_job(job_id))

    @app.delete("/api/jobs/<int:job_id>")
    def api_job_delete(job_id):
        need_job(job_id)
        for name in storage.delete_job(job_id):
            service.remove_file(name)
        return jsonify(ok=True)

    # ---------------------------------------------------------- resumes
    @app.post("/api/jobs/<int:job_id>/resumes")
    def api_upload_resumes(job_id):
        need_job(job_id)
        files = [f for f in request.files.getlist("files") if f and f.filename]
        if not files:
            return jsonify(error="No files received."), 400
        if len(files) > config.MAX_FILES_PER_REQUEST:
            return jsonify(error=f"At most {config.MAX_FILES_PER_REQUEST} files per request."), 400
        results = []
        for f in files:
            data = f.read(config.MAX_FILE_MB * 1024 * 1024 + 1)
            results.append(service.ingest_resume(job_id, f.filename, data))
        return jsonify(results=results)

    @app.get("/api/jobs/<int:job_id>/candidates")
    def api_candidates(job_id):
        job = need_job(job_id)
        rows = storage.list_candidates(job_id)
        for r in rows:
            r.pop("stored_name", None)
            r["stale"] = r["job_version"] != job["version"]
        return jsonify(candidates=rows, job_version=job["version"])

    @app.get("/api/candidates/<int:cid>")
    def api_candidate(cid):
        c = storage.get_candidate(cid)
        if not c:
            abort(404)
        c.pop("stored_name", None)
        p = c["parsed"]
        # return a trimmed parse: no raw text, no per-entry text
        c["parsed"] = {"name": p.get("name"), "links": p.get("links"), "flags": p.get("flags"),
                       "total_years": p.get("total_years"), "claimed_years": p.get("claimed_years"),
                       "certifications": p.get("certifications"), "projects": p.get("projects"),
                       "education": p.get("education"),
                       "experience": [{k: v for k, v in e.items() if k not in ("text", "start", "end")}
                                      for e in p.get("experience", [])]}
        return jsonify(candidate=c)

    @app.get("/api/candidates/<int:cid>/file")
    def api_candidate_file(cid):
        c = storage.get_candidate(cid)
        if not c:
            abort(404)
        path = (config.UPLOAD_DIR / c["stored_name"]).resolve()
        if config.UPLOAD_DIR.resolve() not in path.parents or not path.exists():
            abort(404)
        inline = c["stored_name"].endswith(".pdf") and request.args.get("download") != "1"
        return send_file(path, as_attachment=not inline, download_name=c["filename"])

    @app.delete("/api/candidates/<int:cid>")
    def api_candidate_delete(cid):
        name = storage.delete_candidate(cid)
        if name is None:
            abort(404)
        service.remove_file(name)
        return jsonify(ok=True)

    # ------------------------------------------------------------ export
    @app.get("/api/jobs/<int:job_id>/export.<fmt>")
    def api_export(job_id, fmt):
        job = need_job(job_id)
        cands = storage.list_candidates(job_id)
        safe = "".join(ch if ch.isalnum() else "_" for ch in job["title"])[:40] or "job"
        if fmt == "csv":
            return Response(export.to_csv(job, cands), mimetype="text/csv",
                            headers={"Content-Disposition": f'attachment; filename="siuru_{safe}.csv"'})
        if fmt == "xlsx":
            return Response(export.to_xlsx(job, cands),
                            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f'attachment; filename="siuru_{safe}.xlsx"'})
        abort(404)

    return app
