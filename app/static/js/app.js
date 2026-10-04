const THEME_KEY = 'mediguard-theme';
const SAMPLE_INPUT = {
  age: 55, sex: 1, cp: 3, trestbps: 140, chol: 250, fbs: 0, restecg: 1,
  thalach: 150, exang: 0, oldpeak: 1.5, slope: 2, ca: 0, thal: 3,
};

const state = { csrfToken: '', role: '', patientAfterId: 0 };

document.addEventListener('DOMContentLoaded', async () => {
  applyTheme(localStorage.getItem(THEME_KEY) || 'dark');
  document.getElementById('oidc-login-btn').addEventListener('click', () => {
    window.location.assign('/auth/login');
  });
  document.getElementById('predict-form').addEventListener('submit', handlePrediction);
  document.getElementById('patient-form').addEventListener('submit', handlePatientLookup);
  document.getElementById('create-patient-form').addEventListener('submit', handlePatientCreation);
  document.getElementById('sample-btn').addEventListener('click', fillSampleInput);
  document.getElementById('logout-btn').addEventListener('click', logout);
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
  document.getElementById('refresh-patients-btn').addEventListener('click', () => loadPatients(true));
  document.getElementById('load-more-patients-btn').addEventListener('click', () => loadPatients(false));
  fillSampleInput();
  await refreshSession();
});

function applyTheme(theme) {
  document.body.setAttribute('data-theme', theme);
  document.getElementById('theme-toggle').textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
  localStorage.setItem(THEME_KEY, theme);
}

function toggleTheme() {
  applyTheme(document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
}

function showLogin() {
  document.getElementById('login-card').classList.remove('hidden');
  document.getElementById('dashboard').classList.add('hidden');
  document.getElementById('logout-btn').classList.add('hidden');
}

function showDashboard() {
  document.getElementById('login-card').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
  document.getElementById('logout-btn').classList.remove('hidden');
  document.getElementById('patient-records-title').textContent =
    state.role === 'admin' ? 'Patient directory' : 'My patient records';
  document.getElementById('patient-records-description').textContent =
    state.role === 'admin'
      ? 'View records and add a record assigned to your account.'
      : 'Create and view patient records assigned to your account.';
  loadPatients(true);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function setBanner(message, kind = 'info') {
  const banner = document.getElementById('status-banner');
  banner.textContent = message;
  banner.classList.remove('error', 'success', 'hidden');
  if (kind === 'error') banner.classList.add('error');
  if (kind === 'success') banner.classList.add('success');
}

function clearBanner() {
  const banner = document.getElementById('status-banner');
  banner.classList.add('hidden');
  banner.textContent = '';
}

function buildHeaders(extra = {}) {
  return { 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrfToken, ...extra };
}

async function parseResponse(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

async function refreshSession() {
  try {
    const response = await fetch('/auth/session', { cache: 'no-store' });
    const result = await parseResponse(response);
    if (!result.authenticated) {
      state.csrfToken = '';
      state.role = '';
      showLogin();
      return;
    }
    state.csrfToken = result.csrf_token;
    state.role = result.role;
    showDashboard();
  } catch (error) {
    showLogin();
    setBanner(error.message || 'Unable to check sign-in status.', 'error');
  }
}

function fillSampleInput() {
  const form = document.getElementById('predict-form');
  Object.entries(SAMPLE_INPUT).forEach(([name, value]) => {
    const input = form.elements.namedItem(name);
    if (input) input.value = value;
  });
}

function updatePredictionStats(result) {
  document.getElementById('alert-count').textContent = result.risk_label === 'HIGH' ? '1' : '0';
  document.getElementById('risk-score').textContent =
    `${Math.round(Number(result.risk_probability) * 100)}%`;
}

function renderPredictionCard(result) {
  const resultBox = document.getElementById('prediction-result');
  const label = result.risk_label === 'HIGH' ? 'HIGH' : 'LOW';
  resultBox.classList.remove('hidden');
  resultBox.innerHTML = `
    <div class="risk-card">
      <div class="risk-header"><h3>Prediction outcome</h3>
        <span class="risk-badge ${label.toLowerCase()}">${label}</span></div>
      <div class="risk-metric">${(Number(result.risk_probability) * 100).toFixed(1)}%</div>
      <ul class="detail-list">
        <li><strong>Prediction:</strong> ${escapeHtml(result.prediction)}</li>
        <li><strong>Risk probability:</strong> ${(Number(result.risk_probability) * 100).toFixed(1)}%</li>
      </ul>
      <div class="disclaimer">${escapeHtml(result.disclaimer)}</div>
    </div>`;
  updatePredictionStats(result);
}

async function handlePrediction(event) {
  event.preventDefault();
  clearBanner();
  const payload = Object.fromEntries(
    [...new FormData(event.currentTarget)].map(([key, value]) => [key, Number(value)]),
  );
  try {
    const response = await fetch('/predict', {
      method: 'POST', headers: buildHeaders(), body: JSON.stringify(payload),
    });
    renderPredictionCard(await parseResponse(response));
    setBanner('Prediction completed successfully.', 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to complete prediction.', 'error');
  }
}

function renderPatientCard(patient) {
  const resultBox = document.getElementById('patient-result');
  resultBox.classList.remove('hidden');
  resultBox.innerHTML = `
    <div class="patient-card">
      <div class="patient-header"><h3>${escapeHtml(patient.name)}</h3></div>
      <div class="patient-grid">
        <div class="patient-meta"><span>MRN</span><strong>${escapeHtml(patient.mrn)}</strong></div>
        <div class="patient-meta"><span>Gender</span><strong>${escapeHtml(patient.gender)}</strong></div>
        <div class="patient-meta"><span>DOB</span><strong>${escapeHtml(patient.dob)}</strong></div>
      </div>
      <div class="disclaimer">Diagnosis: ${escapeHtml(patient.diagnosis || '')}</div>
    </div>`;
  document.getElementById('patient-preview').textContent = patient.name || '--';
}

async function handlePatientLookup(event) {
  event.preventDefault();
  clearBanner();
  const patientId = document.getElementById('patient-id').value.trim();
  try {
    const response = await fetch(`/patients/${encodeURIComponent(patientId)}`, {
      headers: buildHeaders(),
    });
    renderPatientCard(await parseResponse(response));
    setBanner('Patient record retrieved.', 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to fetch patient record.', 'error');
  }
}

async function loadPatients(reset = true) {
  try {
    const tableBody = document.getElementById('patient-table-body');
    const loadMoreButton = document.getElementById('load-more-patients-btn');
    if (reset) {
      state.patientAfterId = 0;
      tableBody.innerHTML = '';
    }
    const query = new URLSearchParams({
      limit: '100',
      after_id: String(state.patientAfterId),
    });
    const response = await fetch(`/patients?${query}`, {
      headers: buildHeaders(),
      cache: 'no-store',
    });
    const result = await parseResponse(response);
    if (!result.patients?.length && reset) {
      tableBody.innerHTML = '<tr><td colspan="7">No patient records available yet.</td></tr>';
    } else {
      tableBody.insertAdjacentHTML('beforeend', result.patients.map((patient) => `
        <tr>
          <td>${escapeHtml(patient.id)}</td><td>${escapeHtml(patient.name)}</td>
          <td>${escapeHtml(patient.mrn)}</td><td>${escapeHtml(patient.dob)}</td>
          <td>${escapeHtml(patient.gender)}</td><td>${escapeHtml(patient.diagnosis || '')}</td>
          <td>${escapeHtml(state.role === 'admin' ? patient.assigned_to : 'You')}</td>
        </tr>`).join(''));
    }
    state.patientAfterId = result.next_after_id || state.patientAfterId;
    loadMoreButton.classList.toggle('hidden', !result.next_after_id);
  } catch (error) {
    setBanner(error.message || 'Unable to load patient records.', 'error');
  }
}

async function handlePatientCreation(event) {
  event.preventDefault();
  clearBanner();
  const form = event.currentTarget;
  const patient = Object.fromEntries(new FormData(form).entries());
  try {
    const response = await fetch('/patients', {
      method: 'POST', headers: buildHeaders(), body: JSON.stringify(patient),
    });
    const result = await parseResponse(response);
    form.reset();
    await loadPatients(true);
    setBanner(`Patient record saved (${result.mrn}).`, 'success');
  } catch (error) {
    setBanner(error.message || 'Unable to save patient record.', 'error');
  }
}

async function logout() {
  try {
    await parseResponse(await fetch('/auth/logout', {
      method: 'POST', headers: { 'X-CSRF-Token': state.csrfToken },
    }));
    state.csrfToken = '';
    state.role = '';
    document.getElementById('predict-form').reset();
    document.getElementById('patient-result').innerHTML = '';
    document.getElementById('prediction-result').innerHTML = '';
    document.getElementById('patient-table-body').innerHTML = '';
    document.getElementById('create-patient-form').reset();
    document.getElementById('alert-count').textContent = '0';
    document.getElementById('risk-score').textContent = '--';
    document.getElementById('patient-preview').textContent = '--';
    clearBanner();
    showLogin();
  } catch (error) {
    setBanner(error.message || 'Unable to sign out.', 'error');
  }
}
