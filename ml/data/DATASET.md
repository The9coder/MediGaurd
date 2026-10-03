# UCI Heart Disease Dataset – Cleveland Subset

## Source
- **Repository**: UCI Machine Learning Repository  
- **Dataset**: Heart Disease (Cleveland subset)  
- **UCI ID**: 45  
- **URL**: https://archive.ics.uci.edu/dataset/45/heart+disease  
- **Downloaded via**: `ucimlrepo` Python package (`pip install ucimlrepo`)

## License
Creative Commons Attribution 4.0 International (CC BY 4.0)  
Citation: Janosi, A., Steinbrunn, W., Pfisterer, M., Detrano, R. (1989). Heart Disease. UCI Machine Learning Repository.

## Rows / Columns
- **Rows**: 303 patients (Cleveland clinic)  
- **Features**: 13 numeric/categorical  
- **Target**: `num` (0–4 severity scale → binarized to 0 = no disease, 1 = disease)

## Feature Definitions

| # | Name     | Type        | Description                                                 |
|---|----------|-------------|-------------------------------------------------------------|
| 1 | age      | int         | Age in years                                                |
| 2 | sex      | binary      | 1 = male, 0 = female                                        |
| 3 | cp       | categorical | Chest-pain type (1=typical angina, 2=atypical, 3=non-anginal, 4=asymptomatic) |
| 4 | trestbps | int         | Resting blood pressure (mmHg on admission)                  |
| 5 | chol     | int         | Serum cholesterol (mg/dl)                                   |
| 6 | fbs      | binary      | Fasting blood sugar > 120 mg/dl (1 = true, 0 = false)      |
| 7 | restecg  | categorical | Resting ECG results (0=normal, 1=ST-T abnormality, 2=LV hypertrophy) |
| 8 | thalach  | int         | Maximum heart rate achieved                                 |
| 9 | exang    | binary      | Exercise-induced angina (1 = yes, 0 = no)                  |
|10 | oldpeak  | float       | ST depression induced by exercise relative to rest          |
|11 | slope    | categorical | Slope of peak exercise ST segment (1=upsloping, 2=flat, 3=downsloping) |
|12 | ca       | categorical | Number of major vessels coloured by flourosopy (0–3); **has missing values** |
|13 | thal     | categorical | Thalassemia (3=normal, 6=fixed defect, 7=reversible defect); **has missing values** |

## Target
`target` = binarized `num`:  
- **0** = no heart disease (original value 0)  
- **1** = heart disease (original values 1, 2, 3, 4)

## Missing Values
`ca` and `thal` have missing values represented as `?` in the raw CSV.  
These are imputed with the column mode during preprocessing.

## Ethics Note
This dataset contains de-identified patient records from a 1988 study.  
It is used here **for educational ML demonstration only**.  
It must **not** be used for real clinical decision-making.
