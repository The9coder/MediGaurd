# Model Card – MediGuard Heart Disease Risk Predictor

> **⚠️ EDUCATIONAL / PORTFOLIO PROJECT – NOT FOR CLINICAL USE**  
> This model is built for learning DevSecOps and ML engineering concepts.  
> It must **never** be used to diagnose or treat real patients.

---

## Model Details

| Field | Value |
|-------|-------|
| **Model name** | MediGuard Heart Disease Risk Predictor |
| **Version** | 1.0.0 |
| **Model type** | Best of: Logistic Regression / Random Forest / SVM (sklearn Pipeline) |
| **Selection metric** | 0.6 × Recall + 0.4 × ROC-AUC (recall-weighted composite) |
| **Input features** | 13 clinical features (see below) |
| **Output** | Binary label (0 = no disease, 1 = disease) + risk probability |
| **Framework** | scikit-learn ≥ 1.5, joblib |
| **Training script** | `ml/train.py` |
| **Artifact** | `ml/model/heart_model.joblib` |

---

## Intended Use

### In-scope
- Educational demonstration of ML model deployment in a DevSecOps pipeline
- Interview and portfolio showcasing model evaluation, bias analysis, and secure deployment
- Teaching material for AI/ML students learning about healthcare AI ethics

### Out-of-scope (critical)
- **Clinical diagnosis, screening, or risk stratification of real patients**
- **Any deployment in a production healthcare system**
- **Any jurisdiction's definition of a medical device**
- Making treatment or referral decisions

---

## Training Data

| Property | Value |
|----------|-------|
| **Dataset** | UCI Heart Disease – Cleveland subset |
| **Source** | https://archive.ics.uci.edu/dataset/45/heart+disease |
| **License** | CC BY 4.0 |
| **Size** | 303 rows, 14 columns |
| **Collection year** | 1988 (V.A. Medical Center, Cleveland Clinic Foundation) |
| **Population** | Patients presenting for angiography at a single US clinic |
| **Train/test split** | 80% training (242 rows), 20% test (61 rows), stratified |

### Known Data Limitations
- **Single site, 1988**: Demographics, equipment, and clinical practice have changed dramatically since 1988.
- **Small N = 303**: High variance; metrics can shift noticeably across random seeds.
- **No feature for race/ethnicity**: Cannot assess disparate performance across racial groups.
- **No temporal or geographic diversity**: Generalises poorly to non-US or contemporary populations.
- **Missing value imputation**: `ca` and `thal` have missing values (6 rows); mode imputation introduces minor information leakage.
- **Selection bias**: Only patients referred for angiography; does not represent the general population.

---

## Feature Definitions

| Feature | Type | Range / Values | Clinical Meaning |
|---------|------|----------------|------------------|
| age | int | 29–77 | Age in years |
| sex | binary | 0=female, 1=male | Biological sex |
| cp | int | 1–4 | Chest pain type |
| trestbps | int | 94–200 | Resting blood pressure (mmHg) |
| chol | int | 126–564 | Serum cholesterol (mg/dl) |
| fbs | binary | 0,1 | Fasting blood sugar > 120 mg/dl |
| restecg | int | 0–2 | Resting ECG results |
| thalach | int | 71–202 | Max heart rate achieved |
| exang | binary | 0,1 | Exercise-induced angina |
| oldpeak | float | 0.0–6.2 | ST depression (exercise vs rest) |
| slope | int | 1–3 | Slope of peak exercise ST segment |
| ca | int | 0–3 | Major vessels coloured by fluoroscopy |
| thal | int | 3,6,7 | Thalassemia type |

---

## Metrics (Reported After Training)

> Actual metrics are written to `ml/model/metadata.json` at training time.  
> See that file for the definitive numbers from the last training run.

### Why Recall is the Primary Metric
In cardiac risk screening:
- **False Negative** (predict "no disease", patient actually has disease) → patient goes untreated → **high clinical cost**
- **False Positive** (predict "disease", no disease) → further testing → **lower cost, detectable**

We therefore maximise **recall** (sensitivity) and use ROC-AUC as a threshold-independent complement.

### Cross-Validation Summary (5-fold, stratified)
See `ml/reports/cv_comparison.png` for the visual comparison.

---

## Known Weaknesses / Biases

1. **Gender bias**: The dataset is 68% male. Female patients may be underrepresented.
2. **Age distribution skew**: Mean age ~54; performance on young or elderly patients is uncertain.
3. **No calibration**: Probability outputs are not Platt-scaled on an external set; use as ranking, not absolute probability.
4. **Single-institution data**: May not generalise to different hospital systems, countries, or populations.
5. **Temporal staleness**: 1988 data; modern patients have different risk profiles (statins, obesity epidemic, etc.)
6. **Mode imputation**: Imputing `ca`/`thal` with training-set mode may slightly inflate metrics (minor).

---

## Ethical Considerations

| Issue | Status |
|-------|--------|
| Real patient data used in training? | No – publicly released, de-identified 1988 dataset |
| Model makes autonomous decisions? | No – always returns a disclaimer; human clinician required |
| Explainability | Feature importances available for Random Forest; logistic regression coefficients interpretable |
| Fairness auditing | Not performed on this 303-row dataset – would need larger, diverse dataset |
| Regulatory compliance | Not evaluated – not a medical device |

---

## Deployment Notes (Portfolio Context)

- The model artifact is served by `app/routes/predict.py`
- All API responses include a mandatory disclaimer
- The model path is configurable via `MODEL_PATH` environment variable
- A CI/CD stage verifies the artifact loads successfully before any deployment

---

## Citation

Janosi, A., Steinbrunn, W., Pfisterer, M., & Detrano, R. (1989).  
Heart Disease [Dataset]. UCI Machine Learning Repository.  
https://doi.org/10.24432/C52P4X
