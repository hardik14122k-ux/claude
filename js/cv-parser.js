// CV parser: extracts text from PDF / DOCX-like / plain text files
// and runs heuristics to pull out the structured fields used by the app.

const SKILL_LIBRARY = [
  // languages
  'JavaScript','TypeScript','Python','Java','Kotlin','Go','Rust','Ruby','PHP','C#','C++','C','Swift','Scala','R','Perl','SQL','HTML','CSS','SASS','LESS','Bash','Shell',
  // frameworks / libs
  'React','Next.js','Vue','Angular','Svelte','Redux','Node.js','Express','NestJS','Django','Flask','FastAPI','Spring','Spring Boot','Rails','Laravel','jQuery','Tailwind','Bootstrap','GraphQL','REST',
  // data / ml
  'PostgreSQL','MySQL','MongoDB','Redis','Elasticsearch','Kafka','RabbitMQ','Snowflake','BigQuery','Airflow','Spark','Hadoop','Pandas','NumPy','TensorFlow','PyTorch','Scikit-learn','Keras','LangChain','OpenAI',
  // devops / cloud
  'AWS','Azure','GCP','Docker','Kubernetes','Terraform','Ansible','Jenkins','CircleCI','GitHub Actions','Linux','Nginx','Prometheus','Grafana','Datadog','Splunk',
  // practices
  'Agile','Scrum','Kanban','TDD','BDD','Microservices','CI/CD','OAuth','JWT',
  // HR / ops
  'Recruiting','Sourcing','ATS','Greenhouse','Lever','Workday','HRIS','Onboarding','People Analytics',
  // design / product
  'Figma','Sketch','Product Management','UX','UI','A/B Testing','Mixpanel','Amplitude',
];

const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/g;
const PHONE_RE = /(\+?\d[\d\s().-]{7,}\d)/g;
const URL_RE = /\bhttps?:\/\/\S+|\bwww\.\S+/gi;
const LINKEDIN_RE = /linkedin\.com\/in\/[\w-]+/gi;

const SECTION_HEADERS = [
  'summary','profile','objective','about me','about',
  'skills','technical skills','core competencies','core skills',
  'experience','work experience','employment','professional experience',
  'education','academic',
  'projects','certifications','awards','publications','languages',
];

const MONTHS = '(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)';
const DATE_RANGE_RE = new RegExp(`${MONTHS}\\.?\\s*\\d{4}\\s*[-–—to]+\\s*(?:present|current|now|${MONTHS}\\.?\\s*\\d{4}|\\d{4})`, 'gi');
const YEAR_RANGE_RE = /\b(19|20)\d{2}\s*[-–—to]+\s*(present|current|now|(?:19|20)\d{2})\b/gi;

export async function extractText(file) {
  const name = (file.name || '').toLowerCase();
  if (name.endsWith('.pdf') || file.type === 'application/pdf') {
    return await extractPdfText(file);
  }
  if (name.endsWith('.docx') || name.endsWith('.doc')) {
    // DOCX is a zip of XML; without a full parser, we best-effort read as text.
    return await file.text();
  }
  return await file.text();
}

async function extractPdfText(file) {
  if (!window.pdfjsLib) throw new Error('PDF.js not loaded');
  const buf = await file.arrayBuffer();
  const pdf = await window.pdfjsLib.getDocument({ data: buf }).promise;
  let out = '';
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const content = await page.getTextContent();
    // Preserve line breaks by grouping by y-coordinate.
    const rows = new Map();
    content.items.forEach(item => {
      const y = Math.round(item.transform[5]);
      const line = rows.get(y) || [];
      line.push(item.str);
      rows.set(y, line);
    });
    const ordered = [...rows.entries()].sort((a, b) => b[0] - a[0]);
    out += ordered.map(([, parts]) => parts.join(' ')).join('\n') + '\n';
  }
  return out;
}

export function parseCv(text, opts = {}) {
  const cleaned = text.replace(/\r/g, '').replace(/\u00a0/g, ' ');
  const lines = cleaned.split('\n').map(l => l.trim()).filter(Boolean);

  const email = (cleaned.match(EMAIL_RE) || [])[0] || '';
  const phone = (cleaned.match(PHONE_RE) || []).map(s => s.trim()).find(s => s.replace(/\D/g, '').length >= 8) || '';
  const linkedin = (cleaned.match(LINKEDIN_RE) || [])[0] || '';
  const urls = (cleaned.match(URL_RE) || []).slice(0, 5);

  const name = guessName(lines, email);
  const headline = guessHeadline(lines, name);
  const location = guessLocation(cleaned);

  const sections = splitSections(lines);
  const skills = extractSkills(cleaned, sections.skills);
  const education = extractEducation(sections.education || []);
  const experience = extractExperience(sections.experience || []);
  const experienceYears = estimateYears(cleaned, experience);

  return {
    name, email, phone, linkedin, urls, headline, location,
    skills, education, experience, experienceYears,
    rawCv: cleaned,
    fileName: opts.fileName || '',
  };
}

function guessName(lines, email) {
  // Heuristic: first 4 non-empty lines, pick the one that looks most like a person name.
  const candidates = lines.slice(0, 6).filter(l => l.length < 80 && !EMAIL_RE.test(l) && !PHONE_RE.test(l));
  EMAIL_RE.lastIndex = 0; PHONE_RE.lastIndex = 0;
  const scored = candidates.map(l => {
    const words = l.split(/\s+/).filter(w => /^[A-Za-zÀ-ÿ'.-]+$/.test(w));
    const capRatio = words.filter(w => /^[A-Z]/.test(w)).length / Math.max(1, words.length);
    const upperRatio = l.replace(/[^A-Za-z]/g,'').split('').filter(ch => ch === ch.toUpperCase()).length / Math.max(1, l.replace(/[^A-Za-z]/g,'').length);
    let score = 0;
    if (words.length >= 2 && words.length <= 5) score += 2;
    if (capRatio > 0.6) score += 2;
    if (upperRatio > 0.4 && upperRatio < 0.95) score += 1;
    if (/\d/.test(l)) score -= 2;
    if (/resume|curriculum|cv/i.test(l)) score -= 3;
    return { l, score };
  }).sort((a, b) => b.score - a.score);

  if (scored[0]?.score >= 2) return toTitleCase(scored[0].l);
  if (email) {
    const local = email.split('@')[0].replace(/[._-]+/g, ' ');
    return toTitleCase(local);
  }
  return '';
}

function toTitleCase(s) {
  return s.toLowerCase().replace(/\b([a-z])/g, (_, c) => c.toUpperCase()).trim();
}

function guessHeadline(lines, name) {
  // Look for a line near the top that reads like a title
  const hints = /engineer|developer|manager|designer|analyst|consultant|scientist|architect|recruiter|lead|director|intern|officer|specialist|product/i;
  for (let i = 0; i < Math.min(8, lines.length); i++) {
    const l = lines[i];
    if (!l || l.toLowerCase() === name.toLowerCase()) continue;
    if (hints.test(l) && l.length < 80) return l;
  }
  return '';
}

function guessLocation(text) {
  const m = text.match(/\b([A-Z][a-zA-Z]+(?:[\s-][A-Z][a-zA-Z]+)*,\s*[A-Z][a-zA-Z]+(?:,\s*[A-Z]{2,})?)\b/);
  return m ? m[1] : '';
}

function splitSections(lines) {
  const map = {};
  let current = null;
  lines.forEach(line => {
    const low = line.toLowerCase().replace(/[:#*•\-]+$/,'').trim();
    const header = SECTION_HEADERS.find(h => low === h || low.startsWith(h + ' ') || low === h + ':');
    if (header && line.length < 40) {
      current = normalizeHeader(header);
      map[current] = map[current] || [];
      return;
    }
    if (current) map[current].push(line);
  });
  return map;
}

function normalizeHeader(h) {
  if (/skill/.test(h)) return 'skills';
  if (/experience|employment/.test(h)) return 'experience';
  if (/education|academic/.test(h)) return 'education';
  if (/summary|profile|objective|about/.test(h)) return 'summary';
  if (/project/.test(h)) return 'projects';
  if (/cert/.test(h)) return 'certifications';
  return h;
}

function extractSkills(fullText, skillLines = []) {
  const found = new Set();
  const hay = (skillLines.join(' ') + ' ' + fullText).toLowerCase();
  SKILL_LIBRARY.forEach(s => {
    const escaped = s.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(?:^|[^a-z0-9+#])${escaped}(?:$|[^a-z0-9+#])`, 'i');
    if (re.test(hay)) found.add(s);
  });
  // Also pick comma/bullet-separated words from the Skills section
  if (skillLines.length) {
    skillLines.join('\n').split(/[,;|•\n·]/).map(s => s.trim()).filter(s => s && s.length <= 30 && s.length >= 2)
      .forEach(s => {
        const clean = s.replace(/^[-*]\s*/, '').trim();
        if (/^[A-Za-z][A-Za-z0-9+.#\- /]{1,29}$/.test(clean)) found.add(clean);
      });
  }
  return [...found].slice(0, 40);
}

function extractEducation(lines) {
  const out = [];
  const degree = /(bachelor|b\.?sc|b\.?a|b\.?e|b\.?tech|master|m\.?sc|m\.?a|m\.?b\.?a|m\.?tech|ph\.?d|doctorate|diploma|associate)/i;
  let buf = [];
  const flush = () => {
    if (!buf.length) return;
    const text = buf.join(' | ');
    const year = (text.match(/\b(19|20)\d{2}\b/g) || []).slice(-1)[0] || '';
    const deg = (text.match(degree)?.[0]) || '';
    out.push({ text, degree: deg, year });
    buf = [];
  };
  lines.forEach(l => {
    buf.push(l);
    if (buf.length >= 3) flush();
  });
  flush();
  return out.slice(0, 6);
}

function extractExperience(lines) {
  const out = [];
  let current = null;
  const isHeader = l => /\b(19|20)\d{2}\b/.test(l) || DATE_RANGE_RE.test(l) || /,/.test(l);
  DATE_RANGE_RE.lastIndex = 0;
  lines.forEach(l => {
    if (/^[-*•]/.test(l) && current) {
      current.bullets.push(l.replace(/^[-*•]\s*/, ''));
      return;
    }
    if (isHeader(l)) {
      if (current) out.push(current);
      const dateMatch = l.match(DATE_RANGE_RE) || l.match(YEAR_RANGE_RE);
      DATE_RANGE_RE.lastIndex = 0; YEAR_RANGE_RE.lastIndex = 0;
      const period = dateMatch ? dateMatch[0] : '';
      current = { title: l.replace(period, '').trim().replace(/\s+\|\s+$/, ''), period, bullets: [] };
    } else if (current) {
      current.title = (current.title + ' ' + l).trim().slice(0, 200);
    }
  });
  if (current) out.push(current);
  return out.slice(0, 8);
}

function estimateYears(text, experience) {
  const explicit = text.match(/(\d{1,2})\+?\s+years?\s+of\s+experience/i);
  if (explicit) return Math.min(40, parseInt(explicit[1], 10));

  const ranges = [...text.matchAll(DATE_RANGE_RE), ...text.matchAll(YEAR_RANGE_RE)];
  let months = 0;
  ranges.forEach(m => {
    const s = m[0];
    const years = s.match(/\b(19|20)\d{2}\b/g) || [];
    if (years.length >= 2) {
      months += (parseInt(years[1], 10) - parseInt(years[0], 10)) * 12;
    } else if (years.length === 1 && /present|current|now/i.test(s)) {
      months += (new Date().getFullYear() - parseInt(years[0], 10)) * 12;
    }
  });
  if (months > 0) return Math.min(40, Math.round(months / 12));
  return experience.length || null;
}
