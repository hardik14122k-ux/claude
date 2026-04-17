// Demo data to populate the tracker so the dashboard feels alive.

import { createVacancy, createCandidate, scheduleInterview, moveCandidate, getState } from './store.js';

export function seedDemoData() {
  const state = getState();
  if (state.vacancies.length || state.candidates.length) return false;

  const vacancies = [
    { title: 'Senior Backend Engineer', department: 'Engineering', location: 'Bengaluru, IN', hiringManager: 'Priya Raman', openings: 2, priority: 'High',   targetClose: daysFromNow(14), skills: ['Python','PostgreSQL','AWS','Kubernetes'] },
    { title: 'Product Designer',       department: 'Design',      location: 'Remote',       hiringManager: 'Alex Hughes', openings: 1, priority: 'Medium', targetClose: daysFromNow(21), skills: ['Figma','UX','Prototyping'] },
    { title: 'Data Scientist',          department: 'Data',        location: 'London, UK',   hiringManager: 'Rahul Nair', openings: 1, priority: 'High',   targetClose: daysFromNow(10), skills: ['Python','PyTorch','SQL'] },
    { title: 'Technical Recruiter',     department: 'People',      location: 'New York, US', hiringManager: 'Sara Owens', openings: 1, priority: 'Low',    targetClose: daysFromNow(30), skills: ['Sourcing','ATS','Greenhouse'] },
  ].map(createVacancy);

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

  names.forEach(([name, email, skills], i) => {
    const vac = vacancies[i % vacancies.length];
    const cand = createCandidate({
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
    // Move through history with realistic back-dates.
    cand.history = backdate(cand.createdAt, stages[i]);
    cand.stage = stages[i];
  });

  // A few interviews spread across the next week
  const all = getState().candidates.slice(0, 5);
  all.forEach((c, i) => scheduleInterview({
    candidateId: c.id,
    interviewer: ['Priya Raman','Alex Hughes','Rahul Nair','Sara Owens'][i % 4],
    type: ['Screening','Technical','Culture','Final'][i % 4],
    date: hoursFromNow((i + 1) * 20),
    status: 'Scheduled',
  }));

  return true;
}

function daysFromNow(d) { return new Date(Date.now() + d * 86400000).toISOString(); }
function hoursFromNow(h) { return new Date(Date.now() + h * 3600000).toISOString(); }
function randomPhone() { return '+1 ' + Math.floor(200 + Math.random() * 800) + '-' + Math.floor(1000 + Math.random() * 9000); }

function headlineFor(skills) {
  if (skills.some(s => /figma|ux|ui|product/i.test(s))) return 'Senior Product Designer';
  if (skills.some(s => /torch|tensor|scikit/i.test(s))) return 'Machine Learning Engineer';
  if (skills.some(s => /sourcing|ats|greenhouse/i.test(s))) return 'Talent Acquisition Partner';
  if (skills.some(s => /react|next|typescript/i.test(s))) return 'Full-stack Engineer';
  return 'Senior Backend Engineer';
}

function backdate(createdAt, stage) {
  const flow = ['sourced','screening','interview','offer','hired'];
  const idx = flow.indexOf(stage);
  const out = [];
  if (idx >= 0) {
    for (let i = 0; i <= idx; i++) {
      const d = new Date(Date.now() - (idx - i + 1) * (3 + Math.random() * 5) * 86400000);
      out.push({ stage: flow[i], at: d.toISOString(), from: i ? flow[i - 1] : undefined });
    }
  } else if (stage === 'rejected') {
    out.push({ stage: 'sourced', at: new Date(Date.now() - 12 * 86400000).toISOString() });
    out.push({ stage: 'screening', at: new Date(Date.now() - 9 * 86400000).toISOString(), from: 'sourced' });
    out.push({ stage: 'rejected', at: new Date(Date.now() - 4 * 86400000).toISOString(), from: 'screening' });
  } else {
    out.push({ stage, at: createdAt });
  }
  return out;
}
