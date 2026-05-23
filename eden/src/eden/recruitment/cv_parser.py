"""Extract text from CVs and pull out structured fields via heuristics.

Supports PDF (via pypdf) and DOCX (via python-docx). Plain .txt is read
directly. Falls back to best-effort decoding for unknown types.
"""
from __future__ import annotations

import io
import re
from typing import BinaryIO

try:
    from pypdf import PdfReader
except BaseException:  # pragma: no cover - optional; broad: cryptography can panic
    PdfReader = None  # type: ignore

try:
    import docx  # python-docx
except BaseException:  # pragma: no cover - optional
    docx = None  # type: ignore


SKILL_LIBRARY = [
    # languages
    "JavaScript","TypeScript","Python","Java","Kotlin","Go","Rust","Ruby","PHP","C#","C++","C",
    "Swift","Scala","R","Perl","SQL","HTML","CSS","SASS","LESS","Bash","Shell",
    # frameworks / libs
    "React","Next.js","Vue","Angular","Svelte","Redux","Node.js","Express","NestJS","Django","Flask",
    "FastAPI","Spring","Spring Boot","Rails","Laravel","jQuery","Tailwind","Bootstrap","GraphQL","REST",
    # data / ml
    "PostgreSQL","MySQL","MongoDB","Redis","Elasticsearch","Kafka","RabbitMQ","Snowflake","BigQuery",
    "Airflow","Spark","Hadoop","Pandas","NumPy","TensorFlow","PyTorch","Scikit-learn","Keras",
    "LangChain","OpenAI",
    # devops / cloud
    "AWS","Azure","GCP","Docker","Kubernetes","Terraform","Ansible","Jenkins","CircleCI",
    "GitHub Actions","Linux","Nginx","Prometheus","Grafana","Datadog","Splunk",
    # practices
    "Agile","Scrum","Kanban","TDD","BDD","Microservices","CI/CD","OAuth","JWT",
    # HR / ops
    "Recruiting","Sourcing","ATS","Greenhouse","Lever","Workday","HRIS","Onboarding","People Analytics",
    # design / product
    "Figma","Sketch","Product Management","UX","UI","A/B Testing","Mixpanel","Amplitude",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
URL_RE = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.IGNORECASE)
LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w-]+", re.IGNORECASE)

MONTHS = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_RANGE_RE = re.compile(
    rf"{MONTHS}\.?\s*\d{{4}}\s*[-–—to]+\s*(?:present|current|now|{MONTHS}\.?\s*\d{{4}}|\d{{4}})",
    re.IGNORECASE,
)
YEAR_RANGE_RE = re.compile(
    r"\b(19|20)\d{2}\s*[-–—to]+\s*(present|current|now|(?:19|20)\d{2})\b",
    re.IGNORECASE,
)

SECTION_HEADERS = [
    "summary","profile","objective","about me","about",
    "skills","technical skills","core competencies","core skills",
    "experience","work experience","employment","professional experience",
    "education","academic",
    "projects","certifications","awards","publications","languages",
]


def extract_text(stream: BinaryIO, filename: str = "", content_type: str = "") -> str:
    name = (filename or "").lower()
    data = stream.read()
    if name.endswith(".pdf") or content_type == "application/pdf":
        return _extract_pdf(data)
    if name.endswith(".docx"):
        return _extract_docx(data)
    return _decode_best(data)


def _extract_pdf(data: bytes) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf not installed")
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n".join(pages)


def _extract_docx(data: bytes) -> str:
    if docx is None:
        return _decode_best(data)
    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)


def _decode_best(data: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def parse_cv(text: str, file_name: str = "") -> dict:
    cleaned = text.replace("\r", "").replace(" ", " ")
    lines = [l.strip() for l in cleaned.split("\n") if l.strip()]

    email_m = EMAIL_RE.search(cleaned)
    email = email_m.group(0) if email_m else ""

    phone = ""
    for m in PHONE_RE.finditer(cleaned):
        candidate = m.group(0).strip()
        if len(re.sub(r"\D", "", candidate)) >= 8:
            phone = candidate
            break

    linkedin_m = LINKEDIN_RE.search(cleaned)
    linkedin = linkedin_m.group(0) if linkedin_m else ""
    urls = URL_RE.findall(cleaned)[:5]

    name = _guess_name(lines, email)
    headline = _guess_headline(lines, name)
    location = _guess_location(cleaned)

    sections = _split_sections(lines)
    skills = _extract_skills(cleaned, sections.get("skills", []))
    education = _extract_education(sections.get("education", []))
    experience = _extract_experience(sections.get("experience", []))
    years = _estimate_years(cleaned, experience)

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "urls": urls,
        "headline": headline,
        "location": location,
        "skills": skills,
        "education": education,
        "experience": experience,
        "experience_years": years,
        "raw_cv": cleaned,
        "file_name": file_name,
    }


def _guess_name(lines: list[str], email: str) -> str:
    candidates = []
    for line in lines[:6]:
        if len(line) >= 80:
            continue
        if EMAIL_RE.search(line) or PHONE_RE.search(line):
            continue
        candidates.append(line)

    scored: list[tuple[int, str]] = []
    for line in candidates:
        words = [w for w in line.split() if re.fullmatch(r"[A-Za-zÀ-ÿ'.\-]+", w)]
        if not words:
            continue
        cap_ratio = sum(1 for w in words if w[:1].isupper()) / max(1, len(words))
        letters = re.sub(r"[^A-Za-z]", "", line)
        upper_ratio = (sum(1 for c in letters if c.isupper()) / max(1, len(letters))) if letters else 0
        score = 0
        if 2 <= len(words) <= 5:
            score += 2
        if cap_ratio > 0.6:
            score += 2
        if 0.4 < upper_ratio < 0.95:
            score += 1
        if re.search(r"\d", line):
            score -= 2
        if re.search(r"resume|curriculum|\bcv\b", line, re.IGNORECASE):
            score -= 3
        scored.append((score, line))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored and scored[0][0] >= 2:
        return _title_case(scored[0][1])
    if email:
        local = re.sub(r"[._\-]+", " ", email.split("@")[0])
        return _title_case(local)
    return ""


def _title_case(s: str) -> str:
    return " ".join(w.capitalize() if w and w.isalpha() else w for w in s.split()).strip()


def _guess_headline(lines: list[str], name: str) -> str:
    hints = re.compile(r"engineer|developer|manager|designer|analyst|consultant|scientist|architect|recruiter|lead|director|intern|officer|specialist|product", re.IGNORECASE)
    for line in lines[:8]:
        if not line or line.lower() == name.lower():
            continue
        if hints.search(line) and len(line) < 80:
            return line
    return ""


def _guess_location(text: str) -> str:
    m = re.search(r"\b([A-Z][a-zA-Z]+(?:[\s\-][A-Z][a-zA-Z]+)*,\s*[A-Z][a-zA-Z]+(?:,\s*[A-Z]{2,})?)\b", text)
    return m.group(1) if m else ""


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        low = line.lower().rstrip(":*#•- ").strip()
        match = None
        for h in SECTION_HEADERS:
            if low == h or low.startswith(h + " ") or low == h + ":":
                match = h
                break
        if match and len(line) < 40:
            current = _normalize_header(match)
            out.setdefault(current, [])
            continue
        if current:
            out[current].append(line)
    return out


def _normalize_header(h: str) -> str:
    if "skill" in h:
        return "skills"
    if "experience" in h or "employment" in h:
        return "experience"
    if "education" in h or "academic" in h:
        return "education"
    if h in ("summary", "profile", "objective", "about me", "about"):
        return "summary"
    if "project" in h:
        return "projects"
    if "cert" in h:
        return "certifications"
    return h


def _extract_skills(full: str, skill_lines: list[str]) -> list[str]:
    found: list[str] = []
    seen = set()
    hay = (" ".join(skill_lines) + " " + full).lower()
    for s in SKILL_LIBRARY:
        pattern = re.escape(s.lower())
        if re.search(rf"(?:^|[^a-z0-9+#]){pattern}(?:$|[^a-z0-9+#])", hay):
            if s not in seen:
                seen.add(s)
                found.append(s)
    if skill_lines:
        for raw in re.split(r"[,;|•\n·]", "\n".join(skill_lines)):
            clean = re.sub(r"^[-*]\s*", "", raw).strip()
            if 2 <= len(clean) <= 30 and re.fullmatch(r"[A-Za-z][A-Za-z0-9+.#\- /]{1,29}", clean):
                if clean not in seen:
                    seen.add(clean)
                    found.append(clean)
    return found[:40]


def _extract_education(lines: list[str]) -> list[dict]:
    out = []
    degree_re = re.compile(r"(bachelor|b\.?sc|b\.?a|b\.?e|b\.?tech|master|m\.?sc|m\.?a|m\.?b\.?a|m\.?tech|ph\.?d|doctorate|diploma|associate)", re.IGNORECASE)
    year_re = re.compile(r"\b(?:19|20)\d{2}\b")
    buf: list[str] = []
    def flush():
        if not buf:
            return
        text = " | ".join(buf)
        years = year_re.findall(text)
        year = years[-1] if years else ""
        deg_m = degree_re.search(text)
        out.append({"text": text, "degree": deg_m.group(0) if deg_m else "", "year": year})
    for line in lines:
        buf.append(line)
        if len(buf) >= 3:
            flush()
            buf = []
    flush()
    return out[:6]


def _extract_experience(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    current: dict | None = None
    def is_header(line: str) -> bool:
        if re.search(r"\b(19|20)\d{2}\b", line):
            return True
        if DATE_RANGE_RE.search(line):
            return True
        if "," in line and re.search(r"[A-Za-z]", line):
            return True
        return False

    for line in lines:
        if line.startswith(("-", "*", "•")) and current:
            current["bullets"].append(re.sub(r"^[-*•]\s*", "", line))
            continue
        if is_header(line):
            if current:
                out.append(current)
            period_m = DATE_RANGE_RE.search(line) or YEAR_RANGE_RE.search(line)
            period = period_m.group(0) if period_m else ""
            title = line.replace(period, "").strip().rstrip(" |")
            current = {"title": title, "period": period, "bullets": []}
        elif current:
            current["title"] = (current["title"] + " " + line).strip()[:200]
    if current:
        out.append(current)
    return out[:8]


def _estimate_years(text: str, experience: list[dict]) -> int | None:
    m = re.search(r"(\d{1,2})\+?\s+years?\s+of\s+experience", text, re.IGNORECASE)
    if m:
        return min(40, int(m.group(1)))

    months = 0
    for rng in list(DATE_RANGE_RE.finditer(text)) + list(YEAR_RANGE_RE.finditer(text)):
        s = rng.group(0)
        years = re.findall(r"\b(?:19|20)\d{2}\b", s)
        if len(years) >= 2:
            months += (int(years[1]) - int(years[0])) * 12
        elif len(years) == 1 and re.search(r"present|current|now", s, re.IGNORECASE):
            from datetime import datetime
            months += (datetime.now().year - int(years[0])) * 12
    if months > 0:
        return min(40, round(months / 12))
    return len(experience) or None
