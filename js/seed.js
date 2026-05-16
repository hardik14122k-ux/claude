// Demo seed against Supabase. Inserts vacancies, candidates, interviews,
// and lets DB triggers populate history + activity_logs + employees.

import { sb } from './lib/supabase.js';
import { unwrap } from './lib/errors.js';
import { createVacancy } from './services/vacancies.js';
import { createCandidate, moveCandidate } from './services/candidates.js';
import { scheduleInterview } from './services/interviews.js';

export async function seedDemoData() {
  // Skip if any vacancies already exist.
  const { count } = await sb.from('vacancies').select('*', { count: 'exact', head: true });
  if (count && count > 0) return false;

  const vacancies = [];
  for (const v of [
    { title: 'Senior Backend Engineer', department: 'Engineering', location: 'Bengaluru, IN', hiringManager: 'Priya Raman', openings: 2, priority: 'high',   targetClose: daysFromNow(14, true), skills: ['Python','PostgreSQL','AWS','Kubernetes'] },
    { title: 'Product Designer',        department: 'Design',      location: 'Remote',        hiringManager: 'Alex Hughes', openings: 1, priority: 'medium', targetClose: daysFromNow(21, true), skills: ['Figma','UX','Prototyping'] },
    { title: 'Data Scientist',          department: 'Data',        location: 'London, UK',    hiringManager: 'Rahul Nair',  openings: 1, priority: 'high',   targetClose: daysFromNow(10, true), skills: ['Python','PyTorch','SQL'] },
    { title: 'Technical Recruiter',     department: 'People',      location: 'New York, US',  hiringManager: 'Sara Owens',  openings: 1, priority: 'low',    targetClose: daysFromNow(30, true), skills: ['Sourcing','ATS','Greenhouse'] },
  ]) {
    vacancies.push(await createVacancy(v));
  }

  const names = [
    ['Ananya Iyer','ananya.iyer@example.com', ['Python','Django','PostgreSQL','AWS']],
    ['Marcus Hale','marcus.hale@example.com', ['Go','Kubernetes','Terraform','AWS']],
    ['Yuki Tanaka','yuki.tanaka@example.com', ['Python','Airflow','Snowflake','SQL']],
    ['Isla Fernández','isla.fernandez@example.com', ['Figma','UX','A/B Testing']],
    ['Kenji Park','kenji.park@example.com', ['React','TypeScript','Node.js']],
    ['Zoe Lewis','zoe.lewis@example.com', ['PyTorch','TensorFlow','Python']],
    ['Rahul Mehta','rahul.mehta@example.com', ['Sourcing','Greenhouse','ATS']],
    ['Nadia Khan','nadia.khan@example.com', ['Java','Spring','Microservices']],
    ['Oliver Schmidt','oliver.schmidt@example.com', ['Python','FastAPI','Redis']],
    ['Chen Wei','chen.wei@example.com', ['Figma','Product Management','UI']],
    ['Farah Aziz','farah.aziz@example.com', ['SQL','BigQuery','Python']],
    ['Leo Romano','leo.romano@example.com', ['React','Next.js','TypeScript']],
  ];
  const stages = ['sourced','sourced','screening','screening','interview','interview','offer','rejected','hired','screening','interview','sourced'];

  const created = [];
  for (let i = 0; i < names.length; i++) {
    const [name, email, skills] = names[i];
    const vac = vacancies[i % vacancies.length];
    const c = await createCandidate({
      name, email,
      phone: randomPhone(),
      location: vac.location,
      headline: headlineFor(skills),
      skills,
      experienceYears: 2 + (i % 8),
      vacancyId: vac.id,
      source: i % 2 ? 'LinkedIn' : 'Referral',
      rating: (i % 5) + 1,
    });
    created.push(c);
    // Walk the candidate through stages so triggers populate history + activity.
    if (stages[i] !== 'sourced') await moveCandidate(c.id, stages[i]);
  }

  // A few interviews
  for (let i = 0; i < 5; i++) {
    await scheduleInterview({
      candidateId: created[i].id,
      interviewer: ['Priya Raman','Alex Hughes','Rahul Nair','Sara Owens'][i % 4],
      type: ['screening','technical','culture','final'][i % 4],
      scheduledAt: hoursFromNow((i + 1) * 20),
      status: 'scheduled',
    });
  }

  return true;
}

export async function resetAllData() {
  // Order matters: respect FK direction.
  for (const t of ['payroll','attendance','employees','interviews','candidates','vacancies','activity_logs']) {
    await unwrap(sb.from(t).delete().neq('id', '00000000-0000-0000-0000-000000000000'), `Failed clearing ${t}`);
  }
}

function daysFromNow(d, dateOnly = false) {
  const t = new Date(Date.now() + d * 86400000);
  return dateOnly ? t.toISOString().slice(0, 10) : t.toISOString();
}
function hoursFromNow(hh) { return new Date(Date.now() + hh * 3600000).toISOString(); }
function randomPhone() { return '+1 ' + Math.floor(200 + Math.random() * 800) + '-' + Math.floor(1000 + Math.random() * 9000); }
function headlineFor(skills) {
  if (skills.some(s => /figma|ux|ui|product/i.test(s)))    return 'Senior Product Designer';
  if (skills.some(s => /torch|tensor|scikit/i.test(s)))    return 'Machine Learning Engineer';
  if (skills.some(s => /sourcing|ats|greenhouse/i.test(s))) return 'Talent Acquisition Partner';
  if (skills.some(s => /react|next|typescript/i.test(s))) return 'Full-stack Engineer';
  return 'Senior Backend Engineer';
}
