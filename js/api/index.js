// Barrel export of the high-level API surface.
// Frontend code should prefer these functions over direct service calls
// when the operation involves multiple domains (dashboard, onboarding, etc.).

export { getDashboardData } from './dashboard.js';

// Re-export the most commonly used service functions so consumers can
// import everything from `js/api` if they prefer a single import surface.
export {
  createCandidate, moveCandidate, listCandidates, getCandidate, deleteCandidate,
} from '../services/candidates.js';
export {
  createVacancy, listVacancies, updateVacancy, deleteVacancy,
} from '../services/vacancies.js';
export {
  scheduleInterview, listInterviews, updateInterview,
} from '../services/interviews.js';
export {
  listEmployees as getEmployees, getEmployee, createEmployee, updateEmployee, setSalary,
} from '../services/employees.js';
export {
  markAttendance, checkIn, checkOut, getAttendanceByEmployee, monthlySummary, deriveStatus,
} from '../services/attendance.js';
export {
  generatePayroll, generateMonthlyPayroll, listPayrollByEmployee, listPayrollByPeriod,
  markPaid, calculatePayslip,
} from '../services/payroll.js';
export {
  applyLeave, decideRequest, cancelRequest, listRequests as listLeaveRequests,
  listLeaveTypes, upsertLeaveType, getBalances as getLeaveBalances, adjustBalance,
} from '../services/leaves.js';
export {
  listUsers, getUser, createUserProfile, updateUser, deactivateUser,
} from '../services/users.js';
export {
  signIn, signUp, signOut, currentUser, loadCurrentUser, onAuthChange, requireRole,
} from '../lib/auth.js';
