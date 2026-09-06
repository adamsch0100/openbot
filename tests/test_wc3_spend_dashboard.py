"""
WC-3: Spend Dashboard Tests

Acceptance criteria:
1. Per-CEO cost breakdown in UI
2. Week-over-week trend chart
3. Proactive 50% alerts
4. Cap-exceeded notices
5. Comprehensive tests with real assertions
"""

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import os

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from openbot.spend import per_ceo_breakdown, weekly_trend, check_cap_alerts
from openbot.store import ROOT, JOBS, write_job


class TestWC3SpendDashboard(unittest.TestCase):
    """WC-3: Spend Dashboard comprehensive tests"""

    def setUp(self):
        """Set up test environment"""
        self.test_jobs_dir = JOBS
        self.test_jobs_dir.mkdir(exist_ok=True)
        
        # Create test org structure (profile.json, not org.json)
        org_dir = ROOT / "org"
        org_dir.mkdir(parents=True, exist_ok=True)
        profile_file = org_dir / "profile.json"
        profile_file.write_text(json.dumps({
            "name": "OPENBOT",
            "folder": str(ROOT),
            "projects": [
                {"id": "test-ceo-1", "name": "CEO Alpha", "folder": str(ROOT / "alpha"), "primary": True},
                {"id": "test-ceo-2", "name": "CEO Beta", "folder": str(ROOT / "beta")},
                {"id": "test-ceo-3", "name": "CEO Gamma", "folder": str(ROOT / "gamma")},
            ]
        }), encoding="utf-8")
        
        # Clean up old test jobs
        if self.test_jobs_dir.exists():
            for f in self.test_jobs_dir.glob("test-*.json"):
                f.unlink()

    def tearDown(self):
        """Clean up test jobs"""
        if self.test_jobs_dir.exists():
            for f in self.test_jobs_dir.glob("test-*.json"):
                f.unlink()

    def _create_test_job(self, job_id, project_id, usd_estimate, days_ago=0, engine="opencode"):
        """Helper to create a test job"""
        now = datetime.now(timezone.utc)
        job_time = now - timedelta(days=days_ago)
        
        job = {
            "id": f"test-{job_id}",
            "project_id": project_id,
            "preset": "builder",
            "engine": engine,
            "model": "test-model",
            "usd_estimate": usd_estimate,
            "at": job_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rejected": False,
        }
        write_job(job)
        return job

    def test_per_ceo_breakdown_with_multiple_ceos(self):
        """Test 1: Per-CEO cost breakdown aggregates correctly"""
        # Create 10 jobs across 3 CEOs
        self._create_test_job("1", "test-ceo-1", 0.50, days_ago=1)
        self._create_test_job("2", "test-ceo-1", 0.30, days_ago=2)
        self._create_test_job("3", "test-ceo-1", 0.20, days_ago=3)
        
        self._create_test_job("4", "test-ceo-2", 1.00, days_ago=1)
        self._create_test_job("5", "test-ceo-2", 0.75, days_ago=2)
        self._create_test_job("6", "test-ceo-2", 0.50, days_ago=4)
        
        self._create_test_job("7", "test-ceo-3", 0.25, days_ago=1)
        self._create_test_job("8", "test-ceo-3", 0.15, days_ago=2)
        self._create_test_job("9", "test-ceo-3", 0.10, days_ago=3)
        self._create_test_job("10", "test-ceo-3", 0.05, days_ago=5)
        
        # Get breakdown
        cap_usd = 5.0
        breakdown = per_ceo_breakdown(cap_usd, "week", policy={"bind": "all", "mode": "hard"})
        
        # Verify structure
        self.assertIn("ceos", breakdown)
        self.assertIn("period", breakdown)
        self.assertEqual(breakdown["period"], "week")
        
        # Find each CEO in results
        ceos = {ceo["id"]: ceo for ceo in breakdown["ceos"]}
        
        # Verify CEO 1 totals
        self.assertIn("test-ceo-1", ceos)
        ceo1 = ceos["test-ceo-1"]
        self.assertAlmostEqual(ceo1["weekly_usd"], 1.00, places=2)  # 0.50 + 0.30 + 0.20
        self.assertEqual(ceo1["name"], "CEO Alpha")
        
        # Verify CEO 2 totals
        self.assertIn("test-ceo-2", ceos)
        ceo2 = ceos["test-ceo-2"]
        self.assertAlmostEqual(ceo2["weekly_usd"], 2.25, places=2)  # 1.00 + 0.75 + 0.50
        
        # Verify CEO 3 totals
        self.assertIn("test-ceo-3", ceos)
        ceo3 = ceos["test-ceo-3"]
        self.assertAlmostEqual(ceo3["weekly_usd"], 0.55, places=2)  # 0.25 + 0.15 + 0.10 + 0.05
        
        # Verify total adds up
        total_weekly = sum(ceo["weekly_usd"] for ceo in breakdown["ceos"])
        self.assertAlmostEqual(total_weekly, 3.80, places=2)

    def test_50_percent_alert_triggers(self):
        """Test 2: 50% weekly cap alert triggers correctly"""
        cap_usd = 2.0
        
        # Create jobs that put CEO 1 at 55% of cap (above 50% threshold)
        self._create_test_job("11", "test-ceo-1", 0.60, days_ago=1)
        self._create_test_job("12", "test-ceo-1", 0.50, days_ago=2)
        
        # Create jobs that put CEO 2 at 40% of cap (below threshold)
        self._create_test_job("13", "test-ceo-2", 0.50, days_ago=1)
        self._create_test_job("14", "test-ceo-2", 0.30, days_ago=2)
        
        # Check alerts
        alerts = check_cap_alerts(cap_usd, "week", policy={"bind": "all", "mode": "hard"})
        
        self.assertIn("alerts", alerts)
        self.assertTrue(alerts["has_alerts"])
        
        # Find CEO 1 alert (should have 50% warning)
        ceo1_alerts = [a for a in alerts["alerts"] if a["ceo_id"] == "test-ceo-1"]
        self.assertEqual(len(ceo1_alerts), 1)
        self.assertEqual(ceo1_alerts[0]["level"], "50_percent")
        self.assertEqual(ceo1_alerts[0]["kind"], "warning")
        self.assertGreater(ceo1_alerts[0]["percent"], 50)
        
        # Verify CEO 2 has no alert (below 50%)
        ceo2_alerts = [a for a in alerts["alerts"] if a["ceo_id"] == "test-ceo-2" and a["level"] == "50_percent"]
        self.assertEqual(len(ceo2_alerts), 0)

    def test_cap_exceeded_notice(self):
        """Test 3: Cap-exceeded notice appears when CEO hits cap"""
        cap_usd = 1.0
        
        # Create jobs that exceed cap for CEO 1
        self._create_test_job("15", "test-ceo-1", 0.60, days_ago=1)
        self._create_test_job("16", "test-ceo-1", 0.50, days_ago=2)
        
        # Check alerts
        alerts = check_cap_alerts(cap_usd, "week", policy={"bind": "all", "mode": "hard"})
        
        # Find CEO 1 cap-exceeded alert
        cap_alerts = [a for a in alerts["alerts"] if a["ceo_id"] == "test-ceo-1" and a["level"] == "cap_exceeded"]
        self.assertEqual(len(cap_alerts), 1)
        
        alert = cap_alerts[0]
        self.assertEqual(alert["kind"], "error")
        self.assertIn("resets in", alert["message"])
        self.assertIn("reset_message", alert)

    def test_weekly_trend_last_14_days(self):
        """Test 4: Week-over-week trend returns 14 days of data"""
        # Create jobs spread over 14 days
        for i in range(14):
            self._create_test_job(f"trend-{i}", "test-ceo-1", 0.10 * (i + 1), days_ago=i)
        
        # Get trend
        trend = weekly_trend(project_id="test-ceo-1", policy={"bind": "all", "mode": "hard"})
        
        self.assertIn("series", trend)
        self.assertIn("days", trend)
        self.assertEqual(trend["days"], 14)
        self.assertEqual(len(trend["series"]), 14)
        
        # Verify series structure
        for day_data in trend["series"]:
            self.assertIn("date", day_data)
            self.assertIn("usd", day_data)
            self.assertIsInstance(day_data["usd"], (int, float))

    def test_no_alerts_below_thresholds(self):
        """Test 5: No alerts when spend is below thresholds"""
        cap_usd = 10.0
        
        # Create minimal spend
        self._create_test_job("17", "test-ceo-1", 0.10, days_ago=1)
        self._create_test_job("18", "test-ceo-2", 0.20, days_ago=1)
        
        # Check alerts
        alerts = check_cap_alerts(cap_usd, "week", policy={"bind": "all", "mode": "hard"})
        
        self.assertFalse(alerts["has_alerts"])
        self.assertEqual(len(alerts["alerts"]), 0)

    def test_breakdown_with_no_jobs(self):
        """Test 6: Breakdown handles empty job list gracefully"""
        # No jobs created
        
        breakdown = per_ceo_breakdown(5.0, "week", policy={"bind": "all", "mode": "hard"})
        
        self.assertIn("ceos", breakdown)
        # All CEOs should have zero spend
        for ceo in breakdown["ceos"]:
            self.assertEqual(ceo["weekly_usd"], 0.0)
            self.assertFalse(ceo["alert_50_percent"])
            self.assertFalse(ceo["at_cap"])

    def test_multiple_ceos_at_different_thresholds(self):
        """Test 7: Multiple CEOs can have different alert states simultaneously"""
        cap_usd = 2.0
        
        # CEO 1: Below threshold (30%)
        self._create_test_job("19", "test-ceo-1", 0.60, days_ago=1)
        
        # CEO 2: At 50% threshold
        self._create_test_job("20", "test-ceo-2", 1.00, days_ago=1)
        
        # CEO 3: Exceeded cap
        self._create_test_job("21", "test-ceo-3", 2.50, days_ago=1)
        
        # Check breakdown and alerts
        breakdown = per_ceo_breakdown(cap_usd, "week", policy={"bind": "all", "mode": "hard"})
        alerts = check_cap_alerts(cap_usd, "week", policy={"bind": "all", "mode": "hard"})
        
        ceos = {ceo["id"]: ceo for ceo in breakdown["ceos"]}
        
        # CEO 1: No alert
        self.assertFalse(ceos["test-ceo-1"]["alert_50_percent"])
        self.assertFalse(ceos["test-ceo-1"]["at_cap"])
        
        # CEO 2: 50% alert but not at cap
        self.assertTrue(ceos["test-ceo-2"]["alert_50_percent"])
        self.assertFalse(ceos["test-ceo-2"]["at_cap"])
        
        # CEO 3: At cap (and implicitly past 50%)
        self.assertTrue(ceos["test-ceo-3"]["at_cap"])
        
        # Verify alerts exist for CEOs 2 and 3
        ceo2_alerts = [a for a in alerts["alerts"] if a["ceo_id"] == "test-ceo-2"]
        ceo3_alerts = [a for a in alerts["alerts"] if a["ceo_id"] == "test-ceo-3"]
        
        self.assertGreater(len(ceo2_alerts), 0)
        self.assertGreater(len(ceo3_alerts), 0)


if __name__ == "__main__":
    unittest.main()
