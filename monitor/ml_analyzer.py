# monitor/ml_analyzer.py
from transformers import pipeline

classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

def evaluate_defacement(text: str) -> float:
    candidate_labels = ["defacement", "normal"]
    result = classifier(text, candidate_labels)
    if "defacement" in result["labels"]:
        index = result["labels"].index("defacement")
        return result["scores"][index]
    return 0.0
