"""Local ML classifier for transaction categorization.

Trains a TF-IDF + SGD classifier per user on their categorized transactions.
Zero API cost, millisecond inference, improves as user corrects categories.

Model is stored in memory (per-process) and retrained when:
- Manual categorization happens
- Import completes with new categorized transactions
- Explicitly triggered
"""
import logging
import os
import pickle
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Transaction, Category

logger = logging.getLogger(__name__)

# Persisted so trained models survive a container restart. In Docker this is
# backed by the `classifier_models` named volume (see docker-compose.yml,
# CLASSIFIER_MODEL_DIR=/data/models on the api service). Outside Docker it
# falls back to a gitignored directory under the backend package rather than
# /tmp, which gets wiped on reboot and is world-readable on shared hosts.
_DEFAULT_LOCAL_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / ".local" / "models"
MODEL_DIR = Path(os.environ.get("CLASSIFIER_MODEL_DIR") or _DEFAULT_LOCAL_MODEL_DIR)
MIN_SAMPLES = 50  # Minimum categorized transactions before training
MIN_SAMPLES_PER_CLASS = 3  # Minimum samples per category to include

# In-memory cache: user_id -> (model, label_map)
_model_cache: dict[str, tuple[Pipeline, dict[str, str]]] = {}


def _model_path(user_id: str) -> Path:
    return MODEL_DIR / f"classifier_{user_id}.pkl"


async def train_classifier(db: AsyncSession, user_id: str) -> dict:
    """Train/retrain the classifier on user's categorized transactions.

    Returns stats about training: sample count, category count, etc.
    """
    # Fetch all categorized transactions with their category names
    result = await db.execute(
        select(Transaction.merchant, Transaction.notes, Transaction.amount, Category.name)
        .join(Category, Transaction.category_id == Category.id)
        .where(and_(
            Transaction.user_id == user_id,
            Transaction.category_id.isnot(None),
        ))
    )
    rows = result.all()

    if len(rows) < MIN_SAMPLES:
        logger.info(f"Not enough samples to train ({len(rows)}/{MIN_SAMPLES})")
        return {"status": "skipped", "reason": f"Need {MIN_SAMPLES} categorized transactions, have {len(rows)}"}

    # Build features: merchant name + notes (description context)
    texts = []
    labels = []
    for merchant, notes, amount, cat_name in rows:
        # Combine merchant + notes for richer features
        parts = [merchant or ""]
        if notes:
            # First part of notes is usually the original description
            parts.append(notes.split("|")[0].strip())
        # Add amount sign as a feature (income vs expense)
        parts.append("income" if amount > 0 else "expense")
        texts.append(" ".join(parts).lower())
        labels.append(cat_name)

    # Filter categories with too few samples
    from collections import Counter
    label_counts = Counter(labels)
    valid_labels = {l for l, c in label_counts.items() if c >= MIN_SAMPLES_PER_CLASS}

    filtered_texts = []
    filtered_labels = []
    for t, l in zip(texts, labels):
        if l in valid_labels:
            filtered_texts.append(t)
            filtered_labels.append(l)

    if len(set(filtered_labels)) < 2:
        logger.info("Not enough distinct categories to train classifier")
        return {"status": "skipped", "reason": "Need at least 2 categories with enough samples"}

    # Build pipeline
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            strip_accents="unicode",
        )),
        ("clf", SGDClassifier(
            loss="modified_huber",  # Gives probability estimates
            max_iter=1000,
            random_state=42,
            class_weight="balanced",  # Handle imbalanced categories
        )),
    ])

    pipeline.fit(filtered_texts, filtered_labels)

    # Build category name -> id mapping
    cat_result = await db.execute(
        select(Category).where(Category.user_id == user_id)
    )
    cat_map = {c.name: c.id for c in cat_result.scalars().all()}

    # Cache in memory
    _model_cache[user_id] = (pipeline, cat_map)

    # Persist to disk
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_data = {"pipeline": pipeline, "cat_map": cat_map}
    joblib.dump(model_data, _model_path(user_id))

    stats = {
        "status": "trained",
        "samples": len(filtered_texts),
        "categories": len(set(filtered_labels)),
        "category_counts": dict(Counter(filtered_labels).most_common()),
    }
    logger.info(f"Classifier trained: {stats['samples']} samples, {stats['categories']} categories")
    return stats


def _load_model(user_id: str) -> tuple[Pipeline, dict[str, str]] | None:
    """Load model from cache or disk."""
    if user_id in _model_cache:
        return _model_cache[user_id]

    path = _model_path(user_id)
    if path.exists():
        try:
            data = joblib.load(path)
            _model_cache[user_id] = (data["pipeline"], data["cat_map"])
            return _model_cache[user_id]
        except Exception as e:
            logger.warning(f"Failed to load classifier model: {e}")

    return None


def predict(user_id: str, merchant: str, description: str = "", amount: float = 0) -> tuple[str | None, str | None, float]:
    """Predict category for a transaction.

    Returns: (category_id, category_name, confidence)
    """
    model_data = _load_model(user_id)
    if model_data is None:
        return None, None, 0.0

    pipeline, cat_map = model_data

    # Build feature text same way as training
    parts = [merchant or ""]
    if description:
        parts.append(description.split("|")[0].strip())
    parts.append("income" if amount > 0 else "expense")
    text = " ".join(parts).lower()

    try:
        proba = pipeline.predict_proba([text])[0]
        classes = pipeline.classes_
        best_idx = proba.argmax()
        confidence = float(proba[best_idx])
        cat_name = classes[best_idx]
        cat_id = cat_map.get(cat_name)

        return cat_id, cat_name, confidence
    except Exception as e:
        logger.warning(f"Classifier prediction failed: {e}")
        return None, None, 0.0


def invalidate_cache(user_id: str):
    """Clear cached model for a user (call after retraining)."""
    _model_cache.pop(user_id, None)
