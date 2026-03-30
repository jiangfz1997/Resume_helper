_TECH_IMPLIES: dict[str, set[str]] = {
    "fastapi": {"python"},
    "django": {"python"},
    "flask": {"python"},
    "sqlalchemy": {"python"},
    "celery": {"python"},
    "pytest": {"python"},
    "pandas": {"python"},
    "numpy": {"python"},
    "scikit-learn": {"python"},
    "tensorflow": {"python"},
    "pytorch": {"python"},
    "spring": {"java"},
    "spring boot": {"java"},
    "hibernate": {"java"},
    "rails": {"ruby"},
    "express": {"javascript", "node.js"},
    "nestjs": {"typescript", "node.js"},
    "next.js": {"javascript", "typescript", "react"},
    "nuxt": {"javascript", "vue"},
    "react native": {"javascript", "react"},
    "jest": {"javascript"},
    "typeorm": {"typescript"},
    "prisma": {"typescript", "javascript"},
}


def expand_implied(keywords: list[str]) -> list[str]:
    """Return inferred parent technologies not already present in the keyword list."""
    kw_set = {k.lower() for k in keywords}
    implied: set[str] = set()
    for kw in kw_set:
        for implied_tech in _TECH_IMPLIES.get(kw, set()):
            if implied_tech not in kw_set:
                implied.add(implied_tech)
    return sorted(implied)
