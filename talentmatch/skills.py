"""Skill ontology: canonical names, aliases and directed relations.

This is the "semantic" layer. It is deterministic and runs fully offline, so
no resume text ever leaves the machine. Relations are directed:
RELATIONS[(have, need)] = credit, i.e. how much a candidate who HAS `have`
satisfies a job that NEEDS `need`. Unrelated skills (e.g. JavaScript vs
Python) are intentionally absent and score 0.
"""
import re

# canonical -> aliases (lowercase). The canonical name is also an alias.
SKILLS = {
    # languages
    "python": ["python", "python3", "python 3"],
    "java": ["java", "core java", "java se", "java ee", "j2ee"],
    "javascript": ["javascript", "java script", "js", "ecmascript", "es6"],
    "typescript": ["typescript", "ts"],
    "c#": ["c#", "c sharp", "csharp"],
    "c++": ["c++", "cpp"],
    "c": ["c programming", "c language"],
    "go": ["golang", "go lang", "go programming"],
    "rust": ["rust"],
    "php": ["php"],
    "ruby": ["ruby"],
    "kotlin": ["kotlin"],
    "swift": ["swift"],
    "scala": ["scala"],
    "r": ["r programming", "r language"],
    "bash": ["bash", "shell scripting", "shell script"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    # backend frameworks
    "fastapi": ["fastapi", "fast api"],
    "flask": ["flask"],
    "django": ["django", "django rest framework", "drf"],
    "spring boot": ["spring boot", "springboot", "spring framework", "spring"],
    "node.js": ["node.js", "nodejs", "node js", "node"],
    "express": ["express.js", "expressjs", "express js"],
    ".net": [".net", "dotnet", "asp.net", ".net core", "dot net"],
    "laravel": ["laravel"],
    "rest api": ["rest api", "rest apis", "restful", "restful api", "restful apis",
                 "rest services", "web services", "apis", "api integration", "api integrations"],
    "graphql": ["graphql"],
    "microservices": ["microservices", "microservice"],
    # frontend
    "react": ["react", "reactjs", "react.js", "react js"],
    "angular": ["angular", "angularjs", "angular.js"],
    "vue": ["vue", "vue.js", "vuejs"],
    "next.js": ["next.js", "nextjs"],
    "tailwind": ["tailwind", "tailwindcss", "tailwind css"],
    # data stores
    "sql": ["sql", "t-sql", "pl/sql", "plsql"],
    "postgresql": ["postgresql", "postgres", "psql"],
    "mysql": ["mysql", "mariadb"],
    "sql server": ["sql server", "mssql", "ms sql", "microsoft sql server"],
    "oracle": ["oracle db", "oracle database", "oracle"],
    "sqlite": ["sqlite"],
    "mongodb": ["mongodb", "mongo db", "mongo"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "nosql": ["nosql", "no-sql"],
    "dynamodb": ["dynamodb", "dynamo db"],
    "kafka": ["kafka", "apache kafka"],
    "rabbitmq": ["rabbitmq", "rabbit mq"],
    "sqlalchemy": ["sqlalchemy"],
    "orm": ["orm", "object relational mapping"],
    # devops / cloud
    "docker": ["docker", "containerization", "containers"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services", "ec2"],
    "azure": ["azure", "microsoft azure"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "terraform": ["terraform"],
    "ansible": ["ansible"],
    "jenkins": ["jenkins"],
    "github actions": ["github actions"],
    "gitlab ci": ["gitlab ci", "gitlab-ci", "gitlab ci/cd"],
    "ci/cd": ["ci/cd", "cicd", "ci cd", "continuous integration",
              "continuous delivery", "continuous deployment"],
    "git": ["git"],
    "github": ["github"],
    "gitlab": ["gitlab"],
    "linux": ["linux", "unix", "ubuntu"],
    "nginx": ["nginx"],
    # data / ml
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"],
    "data analysis": ["data analysis", "data analytics"],
    "data visualization": ["data visualization", "data visualisation"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "excel": ["excel", "microsoft excel", "ms excel"],
    "spark": ["spark", "apache spark", "pyspark"],
    "hadoop": ["hadoop"],
    "airflow": ["airflow", "apache airflow"],
    "etl": ["etl", "data pipelines", "data pipeline"],
    # quality / practices
    "pytest": ["pytest"],
    "unit testing": ["unit testing", "unit tests", "unit test", "unittest",
                     "test automation", "tdd"],
    "selenium": ["selenium"],
    "junit": ["junit"],
    "agile": ["agile", "scrum", "kanban"],
    "jira": ["jira"],
    "oop": ["oop", "object oriented programming", "object-oriented programming",
            "object oriented"],
    "design patterns": ["design patterns"],
    "api design": ["api design", "api development"],
    # mobile
    "android": ["android"],
    "ios": ["ios"],
    "flutter": ["flutter"],
    "react native": ["react native"],
    # security / misc
    "oauth": ["oauth", "oauth2", "jwt"],
    "cybersecurity": ["cybersecurity", "cyber security", "information security"],
    "networking": ["networking", "tcp/ip"],
    "figma": ["figma"],
    "salesforce": ["salesforce", "sfdc", "salesforce admin", "salesforce administration",
                   "salesforce administrator"],
    "apex": ["apex", "apex triggers", "apex classes"],
    "lwc": ["lwc", "lightning web components", "lightning web component"],
    "soql": ["soql", "sosl"],
    "visualforce": ["visualforce"],
    "salesforce flow": ["salesforce flow", "flows", "flow builder"],
    "sap": ["sap"],
    # soft / business (matched as ordinary phrases)
    "communication": ["communication skills", "communication"],
    "leadership": ["leadership", "team leadership"],
    "project management": ["project management"],
    "stakeholder management": ["stakeholder management"],
    "problem solving": ["problem solving", "problem-solving"],
    # data science terms
    "matplotlib": ["matplotlib"],
    "seaborn": ["seaborn"],
    "jupyter notebook": ["jupyter notebook", "jupyter", "jupyter notebooks"],
    "statistics": ["statistics", "statistical analysis", "statistical modelling", "statistical modeling"],
    "regression": ["regression", "linear regression", "logistic regression"],
    "classification": ["classification"],
    "clustering": ["clustering", "k-means", "kmeans"],
    "feature engineering": ["feature engineering"],
    "model evaluation": ["model evaluation", "model validation"],
    "eda": ["exploratory data analysis", "eda"],
    "data cleaning": ["data cleaning", "data cleansing", "data preprocessing", "data wrangling",
                      "data preparation"],
    "predictive modelling": ["predictive modelling", "predictive modeling", "predictive models"],
    "hypothesis testing": ["hypothesis testing"],
    "computer vision": ["computer vision", "opencv"],
    "llm": ["llm", "llms", "large language models", "generative ai", "genai"],
}

DISPLAY = {
    "lwc": "LWC", "eda": "EDA", "llm": "LLM", "soql": "SOQL", "visualforce": "Visualforce", "salesforce flow": "Salesforce Flow",
    "aws": "AWS", "gcp": "GCP", "sql": "SQL", "nlp": "NLP", "orm": "ORM",
    "oop": "OOP", "etl": "ETL", "ci/cd": "CI/CD", "html": "HTML", "css": "CSS",
    "fastapi": "FastAPI", "mysql": "MySQL", "postgresql": "PostgreSQL",
    "mongodb": "MongoDB", "nosql": "NoSQL", "sql server": "SQL Server",
    "javascript": "JavaScript", "typescript": "TypeScript", "github": "GitHub",
    "gitlab": "GitLab", "rest api": "REST API", "oauth": "OAuth", "ios": "iOS",
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "dynamodb": "DynamoDB",
    "rabbitmq": "RabbitMQ", "graphql": "GraphQL", "power bi": "Power BI",
    "scikit-learn": "scikit-learn", "sqlalchemy": "SQLAlchemy", "sqlite": "SQLite",
    "api design": "API Design", "elasticsearch": "Elasticsearch", ".net": ".NET",
    "node.js": "Node.js", "next.js": "Next.js", "c#": "C#", "c++": "C++",
    "c": "C", "r": "R", "go": "Go", "gitlab ci": "GitLab CI", "junit": "JUnit",
    "numpy": "NumPy", "php": "PHP", "jira": "Jira",
}


def display(name: str) -> str:
    if name in DISPLAY:
        return DISPLAY[name]
    return name.title() if " " in name else name.capitalize()


RELATIONS = {}


def _sym(a, b, s):
    RELATIONS[(a, b)] = s
    RELATIONS[(b, a)] = s


def _dir(have, need, s):
    RELATIONS[(have, need)] = s


# --- databases
for _db in ("postgresql", "mysql", "sql server", "oracle", "sqlite"):
    _dir(_db, "sql", 0.85)
    _dir("sql", _db, 0.5)
_sym("postgresql", "mysql", 0.6)
_sym("postgresql", "sql server", 0.55)
_sym("mysql", "sql server", 0.55)
_sym("postgresql", "oracle", 0.5)
_sym("mongodb", "dynamodb", 0.5)
for _db in ("mongodb", "dynamodb", "redis"):
    _dir(_db, "nosql", 0.85)
    _dir("nosql", _db, 0.4)
_dir("sqlalchemy", "orm", 0.85)
_dir("django", "orm", 0.6)
_dir("sqlalchemy", "sql", 0.4)
# --- backend
_sym("flask", "fastapi", 0.5)
_sym("django", "flask", 0.5)
_sym("django", "fastapi", 0.5)
for _fw in ("fastapi", "flask", "django", "express", "spring boot", "node.js", ".net", "laravel"):
    _dir(_fw, "rest api", 0.7)
    _dir(_fw, "api design", 0.6)
_dir("rest api", "api design", 0.7)
_dir("api design", "rest api", 0.7)
_dir("spring boot", "java", 0.6)
_dir("express", "node.js", 0.8)
_dir("node.js", "javascript", 0.5)
_dir("typescript", "javascript", 0.85)
_dir("javascript", "typescript", 0.5)
_sym("java", "kotlin", 0.4)
_sym("java", "c#", 0.35)
_sym("spring boot", ".net", 0.35)
_dir("pytest", "unit testing", 0.85)
_dir("junit", "unit testing", 0.85)
_dir("selenium", "unit testing", 0.4)
_dir("microservices", "rest api", 0.4)
# --- frontend
_sym("react", "angular", 0.4)
_sym("react", "vue", 0.4)
_sym("angular", "vue", 0.4)
_dir("next.js", "react", 0.8)
_dir("react native", "react", 0.6)
_dir("react", "react native", 0.5)
_dir("react", "javascript", 0.4)
_dir("angular", "typescript", 0.4)
# --- cloud / devops
_sym("aws", "azure", 0.5)
_sym("aws", "gcp", 0.5)
_sym("azure", "gcp", 0.5)
_dir("kubernetes", "docker", 0.5)
_dir("docker", "kubernetes", 0.4)
for _ci in ("jenkins", "github actions", "gitlab ci"):
    _dir(_ci, "ci/cd", 0.85)
    _dir("ci/cd", _ci, 0.5)
_sym("jenkins", "github actions", 0.6)
_sym("jenkins", "gitlab ci", 0.6)
_sym("github actions", "gitlab ci", 0.6)
_dir("github", "git", 0.85)
_dir("gitlab", "git", 0.85)
_dir("git", "github", 0.6)
_dir("git", "gitlab", 0.6)
_sym("terraform", "ansible", 0.4)
# --- data / ml
for _ml in ("tensorflow", "pytorch", "scikit-learn"):
    _dir(_ml, "machine learning", 0.7)
for _dl in ("tensorflow", "pytorch"):
    _dir(_dl, "deep learning", 0.85)
_sym("tensorflow", "pytorch", 0.7)
_dir("deep learning", "machine learning", 0.85)
_dir("nlp", "machine learning", 0.5)
_dir("pandas", "data analysis", 0.7)
_dir("numpy", "data analysis", 0.5)
_dir("power bi", "data visualization", 0.8)
_dir("tableau", "data visualization", 0.8)
_sym("power bi", "tableau", 0.7)
_dir("airflow", "etl", 0.6)
_dir("spark", "etl", 0.5)
_dir("etl", "airflow", 0.4)
_sym("kafka", "rabbitmq", 0.5)
_dir("agile", "jira", 0.3)
_dir("jira", "agile", 0.3)
_sym("android", "kotlin", 0.4)
_sym("flutter", "react native", 0.5)
for _ds in ("regression", "classification", "clustering", "feature engineering", "model evaluation"):
    _dir("scikit-learn", _ds, 0.5)
    _dir("machine learning", _ds, 0.4)
_dir("statistics", "hypothesis testing", 0.5)
_dir("hypothesis testing", "statistics", 0.6)
_dir("regression", "statistics", 0.4)
_dir("eda", "data analysis", 0.7)
_dir("data analysis", "eda", 0.6)
_dir("pandas", "data cleaning", 0.6)
_dir("matplotlib", "data visualization", 0.7)
_dir("seaborn", "data visualization", 0.7)
_dir("llm", "nlp", 0.4)
_dir("nlp", "llm", 0.3)
# --- salesforce ecosystem
for _sf in ("apex", "lwc", "soql", "visualforce", "salesforce flow"):
    _dir(_sf, "salesforce", 0.7)
_dir("salesforce", "apex", 0.3)
_dir("salesforce", "lwc", 0.3)
_dir("salesforce", "soql", 0.3)
_dir("soql", "sql", 0.5)
_dir("sql", "soql", 0.4)
_dir("apex", "java", 0.3)
_dir("java", "apex", 0.3)
_dir("lwc", "javascript", 0.5)
_dir("javascript", "lwc", 0.3)
_dir("visualforce", "lwc", 0.4)
_dir("lwc", "visualforce", 0.4)

# ---------------------------------------------------------------- detection
_ALIAS_TO_CANON = {}
for _canon, _aliases in SKILLS.items():
    for _a in (set(_aliases) | ({_canon} - {"go", "c", "r"})):
        _ALIAS_TO_CANON.setdefault(_a.lower(), _canon)

# Short/ambiguous aliases only count when written in one of these exact forms.
_EXACT_FORMS = {
    "js": {"JS", "js"}, "ts": {"TS"}, "ml": {"ML"}, "sap": {"SAP"}, "ios": {"iOS", "IOS"},
    "spring": {"Spring"}, "node": {"Node"}, "ec2": {"EC2"}, "drf": {"DRF"},
    "es6": {"ES6"}, "orm": {"ORM"}, "oop": {"OOP"}, "swift": {"Swift"}, "rust": {"Rust"},
    "ruby": {"Ruby"}, "oracle": {"Oracle", "ORACLE"}, "mongo": {"Mongo"},
}

_PRE = r"(?<![A-Za-z0-9+#])"
_POST = r"(?![A-Za-z0-9+#])"
_PATTERNS = []
for _alias, _canon in _ALIAS_TO_CANON.items():
    body = re.escape(_alias).replace(r"\ ", r"[\s\-]+")
    _PATTERNS.append((re.compile(_PRE + body + _POST, re.IGNORECASE), _canon, _alias))
# longest aliases first so "spring boot" wins over "spring"
_PATTERNS.sort(key=lambda t: -len(t[2]))


def find_skills(text: str):
    """Return {canonical: [(start, end), ...]} for every ontology skill in text."""
    found = {}
    claimed = []
    for pattern, canon, alias in _PATTERNS:
        for m in pattern.finditer(text):
            exact = _EXACT_FORMS.get(alias)
            if exact is not None and m.group(0) not in exact:
                continue
            s, e = m.span()
            if any(s < ce and cs < e for cs, ce in claimed):
                continue
            claimed.append((s, e))
            found.setdefault(canon, []).append((s, e))
    return found


def canonical(name: str):
    return _ALIAS_TO_CANON.get(name.strip().lower())


def best_relation(have_skills, need: str):
    """Best (credit, via_skill) a candidate holding `have_skills` gets for `need`."""
    if need in have_skills:
        return 1.0, need
    best = (0.0, None)
    for h in have_skills:
        c = RELATIONS.get((h, need), 0.0)
        if c > best[0]:
            best = (c, h)
    return best
