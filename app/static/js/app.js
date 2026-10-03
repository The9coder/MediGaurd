const STORAGE_KEY = 'mediguard-jwt';
const ROLE_KEY = 'mediguard-role';
const THEME_KEY = 'mediguard-theme';
const SAMPLE_INPUT = {
  age: 55,
  sex: 1,
  cp: 3,
  trestbps: 140,
  chol: 250,
  fbs: 0,
  restecg: 1,
  thalach: 150,
  exang: 0,
  oldpeak: 1.5,
  slope: 2,
  ca: 0,
  thal: 3,
};

const state = {
  token: localStorage.getItem(STORAGE_KEY) || '',
  role: localStorage.getItem(ROLE_KEY) || '',
};

document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const predictForm = document.getElementById('predict-form');
  const patientForm = document.getElementById('patient-form');
  const createPatientForm = document.getElementById('create-patient-form');

  applyTheme(localStorage.getItem(THEME_KEY) || 'dark');

  if (state.token) {
    showDashboard();
  } else {
    showLogin();
  }

  loginForm.addEventListener('submit', handleLogin);
  registerForm.addEventListener('submit', handleRegistration);
  predictForm.addEventListener('submit', handlePrediction);
  patientForm.addEventListener('submit', handlePatientLookup);
  createPatientForm.addEventListener('submit', handlePatientCreation);
  document.getElementById('sample-btn').addEventListener('click', fillSampleInput);
  document.getElementById('logout-btn').addEventListener('click', logout);
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
  document.getElementById('refresh-patients-btn').addEventListener('click', loadAdminPatients);
  document.getElementById('refresh-predictions-btn').addEventListener('click', loadPredictionHistory);
  document.getElementById('show-register-btn').addEventListener('click', () => {
    loginForm.classList.add('hidden');
    registerForm.classList.remove('hidden');
    clearBanner();
  });
  document.getElementById('show-login-btn').addEventListener('click', () => {
    registerForm.classList.add('hidden');
    loginForm.classList.remove('hidden');
    clearBanner();
  });
  fillSampleInput();
});

function applyTheme(theme) {
  document.body.setAttribute('data-theme', theme);
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
  }
  localStorage.setItem(THEME_KEY, theme);
}

function toggleTheme() {
  const next = document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}

function showLogin() {
  document.getElementById('login-card').classList.remove('hidden');
  document.getElementById('dashboard').classList.add('hidden');
  document.getElementById('logout-btn').classList.add('hidden');
  document.getElementById('register-form').classList.add('hidden');
  document.getElementById('login-form').classList.remove('hidden');
}

function showDashboard() {
  document.getElementById('login-card').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
  document.getElementById('logout-btn').classList.remove('hidden');
  document.getElementById('patient-records-title').textContent =
    state.role === 'admin' ? 'Patient directory' : 'My patient records';
  document.getElementById('patient-records-description').textContent =
    state.role === 'admin'
      ? 'View all patient records and add a record assigned to your account.'
      : 'Create and view patient records assigned to your account.';
  loadAdminPatients();
  loadPredictionHistory();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function setBanner(message, kind = 'info') {
  const banner = document.getElementById('status-banner');
  banner.textContent = message;
  banner.classList.remove('error', 'success', 'hidden');
  if (kind === 'error') {
    banner.classList.add('error');
  } else if (kind === 'success') {
    banner.classList.add('success');
  }
}

function clearBanner() {
  const banner = document.getElementById('status-banner');
  banner.classList.add('hidden');
  banner.textContent = '';
}

function buildHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${state.token}`,
    ...extra,
  };
}

function updatePredictionStats(result) {
  document.getElementById('alert-count').textContent =
    result.risk_label === 'HIGH' ? '1' : '0';
  document.getElementById('risk-score').textContent =
    `${Math.round(Number(result.risk_probability) * 100)}%`;
}

function updateReviewedPatient(patient) {
  document.getElementById('patient-preview').textContent = patient.name || '--';
}

async function handleLogin(event) {
  event.preventDefault();
  clearBanner();

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  try {
    const response = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || 'Login failed');
    }

    state.token = payload.token;
    state.role = payload.role;
    localStorage.setItem(STORAGE_KEY, state.token);
    localStorage.setItem(ROLE_KEY, state.role);
    showDashboard();
    setBanner(`Welcome, ${username}! You are now signed in.`, 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to sign in.', 'error');
  }
}

async function handleRegistration(event) {
  event.preventDefault();
  clearBanner();
  const username = document.getElementById('register-username').value.trim();
  const password = document.getElementById('register-password').value;

  try {
    const response = await fetch('/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || 'Account creation failed');
    }

    state.token = payload.token;
    state.role = payload.role;
    localStorage.setItem(STORAGE_KEY, state.token);
    localStorage.setItem(ROLE_KEY, state.role);
    showDashboard();
    setBanner('Account created. You are now signed in.', 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to create account.', 'error');
  }
}

function fillSampleInput() {
  const form = document.getElementById('predict-form');
  Object.entries(SAMPLE_INPUT).forEach(([name, value]) => {
    const el = form.elements.namedItem(name);
    if (el) el.value = value;
  });
}

function renderPredictionCard(result) {
  const resultBox = document.getElementById('prediction-result');
  const badgeClass = result.risk_label === 'HIGH' ? 'high' : 'low';

  resultBox.classList.remove('hidden');
  resultBox.innerHTML = `
    <div class="risk-card">
      <div class="risk-header">
        <h3>Prediction outcome</h3>
        <span class="risk-badge ${badgeClass}">${escapeHtml(result.risk_label)}</span>
      </div>
      <div class="risk-metric">${(Number(result.risk_probability) * 100).toFixed(1)}%</div>
      <ul class="detail-list">
        <li><strong>Prediction:</strong> ${escapeHtml(result.prediction)}</li>
        <li><strong>Risk probability:</strong> ${(Number(result.risk_probability) * 100).toFixed(1)}%</li>
      </ul>
      <div class="disclaimer">${escapeHtml(result.disclaimer)}</div>
    </div>
  `;

  updatePredictionStats(result);
}

function renderPatientCard(patient) {
  const resultBox = document.getElementById('patient-result');
  resultBox.classList.remove('hidden');
  resultBox.innerHTML = `
    <div class="patient-card">
      <div class="patient-header">
        <h3>${escapeHtml(patient.name)}</h3>
        <span class="risk-badge ${patient.diagnosis && patient.diagnosis.toLowerCase().includes('hypertension') ? 'high' : 'low'}">
          ${escapeHtml(patient.diagnosis || 'Review')}
        </span>
      </div>
      <div class="patient-grid">
        <div class="patient-meta"><span>MRN</span><strong>${escapeHtml(patient.mrn)}</strong></div>
        <div class="patient-meta"><span>Gender</span><strong>${escapeHtml(patient.gender)}</strong></div>
        <div class="patient-meta"><span>DOB</span><strong>${escapeHtml(new Date(patient.dob).toLocaleDateString())}</strong></div>
        <div class="patient-meta"><span>Assigned</span><strong>${escapeHtml(patient.assigned_to)}</strong></div>
      </div>
      <div class="disclaimer">Diagnosis: ${escapeHtml(patient.diagnosis)}</div>
    </div>
  `;

  updateReviewedPatient(patient);
}

async function handlePrediction(event) {
  event.preventDefault();
  clearBanner();

  const formData = new FormData(event.currentTarget);
  const payload = {};

  for (const [key, value] of formData.entries()) {
    payload[key] = Number(value);
  }

  try {
    const response = await fetch('/predict', {
      method: 'POST',
      headers: buildHeaders(),
      body: JSON.stringify(payload),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || 'Prediction failed');
    }

    renderPredictionCard(result);
    await loadPredictionHistory();
    setBanner('Prediction completed successfully.', 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to complete prediction.', 'error');
  }
}

async function handlePatientLookup(event) {
  event.preventDefault();
  clearBanner();

  const patientId = document.getElementById('patient-id').value.trim();

  try {
    const response = await fetch(`/patients/${encodeURIComponent(patientId)}`, {
      method: 'GET',
      headers: buildHeaders(),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || 'Patient lookup failed');
    }

    renderPatientCard(result);
    setBanner('Patient record retrieved.', 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to fetch patient record.', 'error');
  }
}

async function loadAdminPatients() {
  try {
    const response = await fetch('/patients', {
      method: 'GET',
      headers: buildHeaders(),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || 'Unable to load patient list');
    }

    const tableBody = document.getElementById('patient-table-body');
    if (!result.patients || result.patients.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="7">No patient records available yet.</td></tr>';
      return;
    }

    tableBody.innerHTML = result.patients.map((patient) => `
      <tr>
        <td>${escapeHtml(patient.id)}</td>
        <td>${escapeHtml(patient.name)}</td>
        <td>${escapeHtml(patient.mrn)}</td>
        <td>${escapeHtml(patient.dob)}</td>
        <td>${escapeHtml(patient.gender)}</td>
        <td>${escapeHtml(patient.diagnosis || '—')}</td>
        <td>${escapeHtml(patient.assigned_to || 'Unassigned')}</td>
      </tr>
    `).join('');
  } catch (error) {
    setBanner(error.message || 'Unable to load patient records.', 'error');
  }
}

async function handlePatientCreation(event) {
  event.preventDefault();
  clearBanner();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const patient = Object.fromEntries(formData.entries());

  try {
    const response = await fetch('/patients', {
      method: 'POST',
      headers: buildHeaders(),
      body: JSON.stringify(patient),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || 'Unable to save patient record');
    }

    form.reset();
    await loadAdminPatients();
    setBanner(`Patient record saved (${result.mrn}).`, 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to save patient record.', 'error');
  }
}

async function loadPredictionHistory() {
  try {
    const response = await fetch('/predictions', {
      method: 'GET',
      headers: buildHeaders(),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || 'Unable to load prediction history');
    }

    const tableBody = document.getElementById('prediction-table-body');
    if (!result.predictions || result.predictions.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="4">No saved predictions yet.</td></tr>';
      return;
    }

    tableBody.innerHTML = result.predictions.map((record) => `
      <tr>
        <td>${escapeHtml(new Date(record.created_at).toLocaleString())}</td>
        <td><span class="risk-badge ${record.risk_label === 'HIGH' ? 'high' : 'low'}">${escapeHtml(record.risk_label)}</span></td>
        <td>${(Number(record.risk_probability) * 100).toFixed(1)}%</td>
        <td>${escapeHtml(record.prediction)}</td>
      </tr>
    `).join('');
  } catch (error) {
    setBanner(error.message || 'Unable to load prediction history.', 'error');
  }
}

function logout() {
  state.token = '';
  state.role = '';
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(ROLE_KEY);
  document.getElementById('predict-form').reset();
  document.getElementById('patient-result').innerHTML = '';
  document.getElementById('patient-result').classList.add('hidden');
  document.getElementById('prediction-result').innerHTML = '';
  document.getElementById('prediction-result').classList.add('hidden');
  document.getElementById('patient-table-body').innerHTML = '';
  document.getElementById('prediction-table-body').innerHTML = '';
  document.getElementById('create-patient-form').reset();
  document.getElementById('alert-count').textContent = '0';
  document.getElementById('risk-score').textContent = '--';
  document.getElementById('patient-preview').textContent = '--';
  clearBanner();
  showLogin();
}
