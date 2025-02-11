import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.impute import SimpleImputer
import pickle
import requests
from flask import Flask, request, render_template
import os
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables (DeepSeek API key)
load_dotenv()
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

# Load the dataset
file_path = "/Users/alexjoseph/Downloads/raredisease/Rare_Diseases_Dataset.csv"
dataset = pd.read_csv(file_path)

# Feature selection
features = ['Prevalence (per million)', 'Genetic Marker', 'Symptoms', 'Age of Onset', 'Affected System']
target = 'Disease Name'

# Encode the target (Disease Name) using LabelEncoder
label_encoder = LabelEncoder()
dataset[target] = label_encoder.fit_transform(dataset[target])

# Feature and target
X = dataset[features].copy()  # Ensure it's a copy
y = dataset[target]

# Convert Age of Onset to numeric values
def convert_age_of_onset(age_of_onset):
    age_map = {'Infancy': 0, 'Childhood': 1, 'Adulthood': 2, 'Adolescence': 3}
    return age_map.get(age_of_onset, -1)  # default to -1 if no match

X.loc[:, 'Age of Onset'] = X['Age of Onset'].apply(convert_age_of_onset)  # FIXED: Avoid modifying a slice

# Preprocessing pipeline for categorical columns
preprocessor = ColumnTransformer(
    transformers=[
        ('categorical', OneHotEncoder(handle_unknown='ignore'), ['Genetic Marker', 'Symptoms', 'Affected System']),
        ('age_of_onset', SimpleImputer(strategy='constant', fill_value=-1), ['Age of Onset']),
        ('prevalence', SimpleImputer(strategy='mean'), ['Prevalence (per million)'])  # Handle missing values for prevalence
    ],
    remainder='passthrough'
)

# Model pipeline
model_pipeline = Pipeline([
    ('preprocessor', preprocessor),
    ('classifier', RandomForestClassifier(random_state=42))  # FIXED: Removed invalid argument
])

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train the model
model_pipeline.fit(X_train, y_train)

# Save the trained model
model_path = "model.pkl"
with open(model_path, "wb") as f:
    pickle.dump(model_pipeline, f)

print("Model trained and saved successfully.")

# Function to get insights from DeepSeek API
def get_deepseek_insights(disease_name):
    try:
        # DeepSeek API URL and headers
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {deepseek_api_key}"
        }
        
        # Prepare the request payload
        data = {
            "model": "deepseek-chat",  # or 'deepseek-reasoner' for reasoning model
            "messages": [
                {"role": "system", "content": "You are a helpful medical assistant."},
                {"role": "user", "content": f"Provide medical insights about {disease_name}."}
            ],
            "stream": False  # Set to False for non-streaming response
        }

        # Make the API request
        response = requests.post(url, json=data, headers=headers)
        response_json = response.json()

        # Print the full response for debugging
        print("DeepSeek API Response:", response_json)  # For debugging

        # Check for successful response
        if response.status_code != 200:
            return f"DeepSeek API Error: {response_json.get('error', 'Unknown error')}"

        # Check if the response contains insights
        if "choices" in response_json and len(response_json["choices"]) > 0:
            # Extract the insight text
            insight = response_json["choices"][0]["message"]["content"].strip()
            if not insight:
                return "No insights found for this disease."
            return insight
        else:
            return "No insights available from DeepSeek."

    except Exception as e:
        return f"Error fetching DeepSeek insights: {e}"

# Flask route for prediction
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    try:
        # Get user input data
        prevalence = request.form['prevalence']
        genetic_marker = request.form['genetic_marker']
        symptoms = request.form['symptoms']
        age_of_onset = request.form['age_of_onset']
        affected_system = request.form['affected_system']

        # Convert Age of Onset to numeric value
        age_of_onset = convert_age_of_onset(age_of_onset)

        # Prepare the input data for prediction
        input_data = pd.DataFrame([{
            'Prevalence (per million)': prevalence,
            'Genetic Marker': genetic_marker,
            'Symptoms': symptoms,
            'Age of Onset': age_of_onset,
            'Affected System': affected_system
        }])

        # Load the saved model
        with open("model.pkl", "rb") as f:
            model_pipeline = pickle.load(f)

        # Preprocess the data and make prediction
        input_data_transformed = model_pipeline.named_steps['preprocessor'].transform(input_data)
        prediction_proba = model_pipeline.named_steps['classifier'].predict_proba(input_data_transformed)
        prediction = model_pipeline.named_steps['classifier'].predict(input_data_transformed)

        # Decode the prediction to the original label
        disease_name = label_encoder.inverse_transform(prediction)[0]

        # **Get the actual confidence percentage for this disease**
        disease_index = list(model_pipeline.named_steps['classifier'].classes_).index(prediction[0])
        confidence = round(prediction_proba[0][disease_index] * 100, 2)  # Convert to percentage

        # Check if the disease exists in the dataset
        disease_info = dataset[dataset[target] == label_encoder.transform([disease_name])[0]]

        if not disease_info.empty:
            disease_info = disease_info.iloc[0]
            diagnostic_method = disease_info['Diagnostic Method']
            treatment = disease_info['Treatment']
        else:
            return f"Disease information for {disease_name} not found in the dataset."

        # **Fetch insights from DeepSeek**
        chatgpt_insights = get_deepseek_insights(disease_name)

        return render_template('result.html', result={
            'Predicted Disease': disease_name,
            'Prediction Confidence': f"{confidence}%",  # FIXED: Proper confidence %
            'Diagnostic Method': diagnostic_method,
            'Treatment': treatment,
            'ChatGPT Insights': chatgpt_insights
        })

    except Exception as e:
        return f"Error during prediction: {e}"

if __name__ == "__main__":
    app.run(debug=True)
