"""
Unit tests for Cosine Similarity, In-Memory Caching, and Notifier logic.
"""

import unittest
import numpy as np
from src.database import FaceDatabase
from src.config import Config

class TestFaceGuardLogic(unittest.TestCase):
    def setUp(self):
        self.db = FaceDatabase(auto_connect=False)
        # Create dummy owner embeddings
        np.random.seed(42)
        v1 = np.random.randn(512).astype(np.float32)
        v1 = v1 / np.linalg.norm(v1)
        v2 = np.random.randn(512).astype(np.float32)
        v2 = v2 / np.linalg.norm(v2)

        self.db.cached_embeddings = np.array([v1, v2])
        self.db.cached_labels = ["pose_neutral", "pose_smile"]

    def test_verify_owner_exact_match(self):
        query = self.db.cached_embeddings[0].copy()
        is_owner, score, label = self.db.verify_face(query, use_cache=True)
        self.assertTrue(is_owner)
        self.assertAlmostEqual(score, 1.0, places=4)
        self.assertEqual(label, "pose_neutral")

    def test_verify_owner_slight_variation(self):
        # Add slight noise to simulate lighting/pose variation
        query = self.db.cached_embeddings[1].copy() + np.random.normal(0, 0.05, 512).astype(np.float32)
        query = query / np.linalg.norm(query)
        is_owner, score, label = self.db.verify_face(query, use_cache=True)
        self.assertTrue(is_owner)
        self.assertGreaterEqual(score, Config.SIMILARITY_THRESHOLD)
        self.assertEqual(label, "pose_smile")

    def test_verify_stranger_rejection(self):
        # Orthogonal/random stranger vector
        stranger_vec = np.random.randn(512).astype(np.float32)
        stranger_vec = stranger_vec / np.linalg.norm(stranger_vec)
        is_owner, score, label = self.db.verify_face(stranger_vec, use_cache=True)
        self.assertFalse(is_owner)
        self.assertLess(score, Config.SIMILARITY_THRESHOLD)

    def test_empty_cache_fallback(self):
        empty_db = FaceDatabase(auto_connect=False)
        empty_db.cached_embeddings = None
        empty_db.cached_labels = []
        dummy = np.random.randn(512).astype(np.float32)
        is_owner, score, label = empty_db.verify_face(dummy, use_cache=True)
        self.assertFalse(is_owner)
        self.assertEqual(score, 0.0)

if __name__ == "__main__":
    unittest.main()

