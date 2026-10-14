"""siuru TalentMatch - run with:  python app.py   ->  http://localhost:8080"""
from talentmatch import config
from talentmatch.web import create_app

app = create_app()

if __name__ == "__main__":
    print(f"siuru TalentMatch running at http://localhost:{config.PORT}  (Ctrl+C to stop)")
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
