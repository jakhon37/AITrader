#!/usr/bin/env python3
"""Downloads and caches the FinBERT model and tokenizer for offline use."""

import sys
from transformers import AutoTokenizer, AutoModelForSequenceClassification

def main():
    print("Downloading and caching FinBERT (ProsusAI/finbert) model and tokenizer...")
    try:
        AutoTokenizer.from_pretrained("ProsusAI/finbert")
        AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        print("FinBERT model and tokenizer downloaded and cached successfully!")
    except Exception as e:
        print(f"Error downloading FinBERT: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
