"""Test Hermes cron list parsing (multi-line block format)."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openbot.hermes import _parse_cron_table, cron_digest, cron_outcome, cron_title, is_valid_job_id, parse_skill_list, read_home_crons
from openbot.live import finish, snapshot, start


class TestHermesCronParsing(unittest.TestCase):
    def test_parse_empty(self):
        """Empty output returns empty list."""
        self.assertEqual(_parse_cron_table(""), [])
        self.assertEqual(_parse_cron_table("No cron jobs"), [])
        self.assertEqual(_parse_cron_table("no cron execution"), [])
    
    def test_parse_real_multiline_format(self):
        """Parse real Hermes multi-line block format."""
        output = """
  7cb2a72c1cc8 [active]
    Name:      form-pipeline-health
    Schedule:  0 14 * * *
    Repeat:    ∞
    Next run:  2026-09-06T14:00:00+00:00
    Deliver:   origin
    Workdir:   /data/workspaces/saa-homes
    Last run:  2026-09-05T14:00:10.773343+00:00  ok
    Dispatch:  on time (...)
    Execution: completed  b47c6c018b4348239ae05959c50d5e22

  240631fc9f22 [active]
    Name:      daily-ranking-strike
    Schedule:  0 13 * * 1-5
    Deliver:   origin
    Workdir:   /data/workspaces/saa-homes
"""
        jobs = _parse_cron_table(output)
        self.assertEqual(len(jobs), 2)
        
        # First job
        self.assertEqual(jobs[0]["id"], "7cb2a72c1cc8")
        self.assertEqual(jobs[0]["name"], "form-pipeline-health")
        self.assertEqual(jobs[0]["schedule"], "0 14 * * *")
        self.assertEqual(jobs[0]["deliver"], "origin")
        
        # Second job
        self.assertEqual(jobs[1]["id"], "240631fc9f22")
        self.assertEqual(jobs[1]["name"], "daily-ranking-strike")
        self.assertEqual(jobs[1]["schedule"], "0 13 * * 1-5")
    
    def test_parse_paused_job(self):
        """Parse paused jobs correctly."""
        output = """
  abc123def456 [paused]
    Name:      test-job
    Schedule:  every 1h
    Deliver:   local
"""
        jobs = _parse_cron_table(output)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "abc123def456")
        self.assertEqual(jobs[0]["name"], "test-job")
        self.assertEqual(jobs[0]["schedule"], "every 1h")
    
    def test_reject_label_words(self):
        """Reject lines with label words, not hex job IDs."""
        output = """
  Name: form-pipeline [active]
    Name:      fake-job
    Schedule:  0 14 * * *
  
  Next [active]
    Name:      another-fake
    Schedule:  every 1h
    
  Execution: something [active]
    Name:      also-fake
    Schedule:  0 9 * * *
"""
        jobs = _parse_cron_table(output)
        # Should reject all because "Name:", "Next", "Execution:" are not valid hex IDs
        self.assertEqual(len(jobs), 0)
    
    def test_real_saa_homes_fixture(self):
        """Parse real SAA Homes cron jobs (multi-line format)."""
        output = """
  7cb2a72c1cc8 [active]
    Name:      form-pipeline-health
    Schedule:  0 14 * * *
    Repeat:    ∞
    Next run:  2026-09-06T14:00:00+00:00
    Deliver:   origin
    Workdir:   /data/workspaces/saa-homes
    Last run:  2026-09-05T14:00:10.773343+00:00  ok
    Dispatch:  on time (...)
    Execution: completed  b47c6c018b4348239ae05959c50d5e22

  240631fc9f22 [active]
    Name:      daily-ranking-strike
    Schedule:  0 13 * * 1-5
    Deliver:   origin
"""
        jobs = _parse_cron_table(output)
        self.assertEqual(len(jobs), 2)
        
        # Verify real job names are extracted
        names = [j["name"] for j in jobs]
        self.assertIn("form-pipeline-health", names)
        self.assertIn("daily-ranking-strike", names)
        
        # Verify schedules are clean
        schedules = [j["schedule"] for j in jobs]
        self.assertIn("0 14 * * *", schedules)
        self.assertIn("0 13 * * 1-5", schedules)
        
        # IDs should be hex-like
        self.assertEqual(jobs[0]["id"], "7cb2a72c1cc8")
        self.assertEqual(jobs[1]["id"], "240631fc9f22")


class TestCronListJSONFallback(unittest.TestCase):
    """Test that cron_list prefers JSON and falls back gracefully."""
    
    def test_cron_list_structure(self):
        """cron_list returns consistent structure."""
        from openbot.hermes import cron_list
        
        # When hermes binary is missing
        result = cron_list()
        self.assertIn("ok", result)
        # When binary is missing, may return "error" instead of "code"
        self.assertTrue("code" in result or "error" in result)
        # text may be empty string when binary missing
        self.assertTrue("text" in result or "error" in result)
        self.assertIn("jobs", result)
        self.assertIsInstance(result["jobs"], list)


class TestJobIdValidation(unittest.TestCase):
    """Test guard against junk job IDs (hex-like, 12+ chars)."""
    
    def test_is_valid_job_id(self):
        """Helper to validate job IDs before using them."""
        # Good IDs (hex-like, 12+ chars)
        self.assertTrue(is_valid_job_id("7cb2a72c1cc8"))
        self.assertTrue(is_valid_job_id("240631fc9f22"))
        self.assertTrue(is_valid_job_id("abc123def456"))
        self.assertTrue(is_valid_job_id("b47c6c018b4348239ae05959c50d5e22"))
        
        # Bad IDs (label words, too short, or not hex-like)
        self.assertFalse(is_valid_job_id("Name:"))
        self.assertFalse(is_valid_job_id("Schedule:"))
        self.assertFalse(is_valid_job_id("Next"))
        self.assertFalse(is_valid_job_id("Execution:"))
        self.assertFalse(is_valid_job_id("Skills:"))
        self.assertFalse(is_valid_job_id("Deliver:"))
        self.assertFalse(is_valid_job_id("Last"))
        self.assertFalse(is_valid_job_id("Dispatch:"))
        self.assertFalse(is_valid_job_id("│"))
        self.assertFalse(is_valid_job_id("--"))
        self.assertFalse(is_valid_job_id(""))
        self.assertFalse(is_valid_job_id("abc"))  # Too short
        self.assertFalse(is_valid_job_id("form-pipeline-health"))  # Name, not ID

    def test_cron_outcome_silent_and_fail(self):
        healthy, nxt = cron_outcome("ok", "## Response\n[SILENT] nothing new")
        self.assertIn("Healthy", healthy)
        self.assertIn("No action", nxt)
        failed, fix = cron_outcome("error", "## Response\nGateway shutdown")
        self.assertTrue(failed.startswith("Failed"))
        self.assertIn("Retry", fix)
        gated, cred = cron_outcome("error", "", "cron endpoint returned 401")
        self.assertIn("401", gated)
        self.assertIn("credential", cred)
        ok_copy, nxt2 = cron_outcome("ok", "")
        self.assertIn("Healthy on the live box", ok_copy)

    def test_cron_digest_plain_story(self):
        rows = [
            {
                "id": "a",
                "name": "form-pipeline-health",
                "enabled": True,
                "last_run_at": "2026-09-07T23:00:00+00:00",
                "last_status": "ok",
                "outcome": "Healthy. Nothing new to report.",
            },
            {
                "id": "b",
                "name": "monthly-market-blog",
                "enabled": True,
                "last_run_at": "2026-09-03T12:00:00+00:00",
                "last_status": "error",
                "outcome": "Failed. The Hermes gateway stopped mid-run.",
            },
        ]
        pack = cron_digest(rows, hours=48, next_ask="Pin Think and send GBP listing corrections.")
        self.assertIn("Site and form check", pack["story"])
        self.assertIn("Monthly market blog", pack["story"])
        self.assertIn("GBP", pack["story"])
        self.assertEqual(cron_title("form-pipeline-health"), "Site and form check")

    def test_cron_digest_stale_copy_points_at_live_hermes(self):
        rows = [
            {
                "id": "a",
                "name": "form-pipeline-health",
                "enabled": True,
                "last_run_at": "2026-08-01T14:00:00+00:00",
                "last_status": "ok",
                "outcome": "Healthy. Nothing new to report.",
            },
            {
                "id": "b",
                "name": "indexation-patrol",
                "enabled": True,
                "last_run_at": "2026-08-02T13:30:00+00:00",
                "last_status": "error",
                "outcome": "Failed. The last run did not finish.",
            },
        ]
        pack = cron_digest(rows, hours=48, next_ask="Open Hermes to confirm the schedule")
        self.assertIn("older than two days", pack["story"])
        self.assertIn("Telegram", pack["story"])
        self.assertNotIn("Open Hermes to confirm", pack["story"])
        self.assertIn("Indexation patrol", pack["story"])

    def test_read_home_crons_from_jobs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            out = home / "cron" / "output" / "7cb2a72c1cc8"
            out.mkdir(parents=True)
            (home / "cron" / "jobs.json").write_text(
                json.dumps({
                    "jobs": [{
                        "id": "7cb2a72c1cc8",
                        "name": "form-pipeline-health",
                        "schedule_display": "0 14 * * *",
                        "enabled": True,
                        "model": "deepseek-v4-flash",
                        "provider": "opencode-go",
                        "last_run_at": datetime.now(timezone.utc).isoformat(),
                        "last_status": "ok",
                    }]
                }),
                encoding="utf-8",
            )
            (out / "2026-09-06_23-29-53.md").write_text(
                "## Response\n[SILENT] healthy\n",
                encoding="utf-8",
            )
            listed = read_home_crons(home, results=False)
            self.assertEqual(listed[0]["name"], "form-pipeline-health")
            self.assertEqual(listed[0]["last_result"], "")
            detailed = read_home_crons(home, results=True)
            self.assertEqual(detailed[0]["last_result"], "")
            self.assertIn("Healthy", detailed[0]["outcome"])
            self.assertEqual(detailed[0]["provider"], "opencode-go")
            self.assertEqual(detailed[0]["model"], "deepseek-v4-flash")
            when = datetime.now(timezone.utc)
            (home / "cron" / "jobs.json").write_text(
                json.dumps({
                    "jobs": [{
                        "id": "7cb2a72c1cc8",
                        "name": "form-pipeline-health",
                        "schedule_display": "0 14 * * *",
                        "enabled": True,
                        "model": "deepseek-v4-flash",
                        "provider": "opencode-go",
                        "last_run_at": when.isoformat(),
                        "last_status": "ok",
                    }]
                }),
                encoding="utf-8",
            )
            (out / f"{when.strftime('%Y-%m-%d_%H-%M-%S')}.md").write_text(
                "## Response\n[SILENT] healthy\n",
                encoding="utf-8",
            )
            fresh = read_home_crons(home, results=True)
            self.assertIn("[SILENT]", fresh[0]["last_result"])
            dump = home / "cron" / "output" / "deadjob"
            dump.mkdir(parents=True)
            (home / "cron" / "jobs.json").write_text(
                json.dumps({
                    "jobs": [{
                        "id": "deadjob",
                        "name": "indexation-patrol",
                        "enabled": True,
                        "last_run_at": when.isoformat(),
                        "last_status": "error",
                        "last_error": "Gateway shutdown (final-cleanup)",
                    }]
                }),
                encoding="utf-8",
            )
            (dump / f"{when.strftime('%Y-%m-%d_%H-%M-%S')}.md").write_text(
                "# Cron Job: indexation-patrol\n## Prompt\nDo the patrol.\n",
                encoding="utf-8",
            )
            failed = read_home_crons(home, results=True)
            self.assertEqual(failed[0]["last_result"], "")
            self.assertIn("gateway", failed[0]["outcome"].lower())

    def test_cron_digest_now_running_and_due(self):
        now = datetime.now(timezone.utc)
        rows = [
            {
                "id": "run1",
                "name": "daily-ranking-strike",
                "enabled": True,
                "state": "running",
                "last_status": "running",
                "last_run_at": now.isoformat(),
                "next_run_at": (now + timedelta(hours=24)).isoformat(),
            },
            {
                "id": "due1",
                "name": "form-pipeline-health",
                "enabled": True,
                "state": "scheduled",
                "last_status": "ok",
                "last_run_at": (now - timedelta(hours=20)).isoformat(),
                "next_run_at": (now + timedelta(minutes=8)).isoformat(),
                "outcome": "Healthy. Nothing new to report.",
            },
            {
                "id": "done1",
                "name": "indexation-patrol",
                "enabled": True,
                "state": "scheduled",
                "last_status": "ok",
                "last_run_at": (now - timedelta(minutes=4)).isoformat(),
                "next_run_at": (now + timedelta(hours=6)).isoformat(),
                "outcome": "Healthy. Nothing new to report.",
            },
        ]
        pack = cron_digest(rows, live_runs=[{"project_id": "saa-homes", "preset": "think"}])
        self.assertEqual(pack["running"][0]["name"], "daily-ranking-strike")
        stale = cron_digest([{
            "id": "95222909917e",
            "name": "indexation-patrol",
            "enabled": True,
            "state": "scheduled",
            "last_status": "error",
            "fire_claim": {"at": (now - timedelta(hours=1)).isoformat(), "by": "test"},
            "last_run_at": (now - timedelta(hours=1)).isoformat(),
            "last_error": "Gateway shutdown (final-cleanup)",
        }])
        self.assertEqual(stale["running"], [])
        retrying = cron_digest([{
            "id": "cacaa7f4ab75",
            "name": "Neighborhood audit + expansion (weekly)",
            "enabled": True,
            "state": "scheduled",
            "last_status": "error",
            "fire_claim": {"at": now.isoformat(), "by": "box:1223"},
            "last_run_at": (now - timedelta(hours=1)).isoformat(),
            "last_error": "Gateway shutdown (final-cleanup)",
        }])
        self.assertEqual(retrying["running"][0]["id"], "cacaa7f4ab75")
        self.assertEqual(retrying["failed"], [])
        self.assertEqual(pack["due"][0]["name"], "form-pipeline-health")
        self.assertEqual(pack["just_finished"][0]["name"], "indexation-patrol")
        self.assertIn("Now running", pack["live_story"])
        self.assertIn("This chat is answering now", pack["live_story"])
        self.assertEqual(pack["latest"]["name"], "daily-ranking-strike")
        self.assertTrue(any(row["name"] == "form-pipeline-health" for row in pack["upcoming"]))

    def test_cron_digest_overdue_counts_as_due(self):
        now = datetime.now(timezone.utc)
        rows = [
            {
                "id": "late1",
                "name": "form-pipeline-health",
                "enabled": True,
                "state": "scheduled",
                "last_status": "ok",
                "last_run_at": (now - timedelta(days=3)).isoformat(),
                "next_run_at": (now - timedelta(days=1)).isoformat(),
            }
        ]
        pack = cron_digest(rows, hours=48)
        self.assertEqual(pack["due"][0]["name"], "form-pipeline-health")
        self.assertIn("form-pipeline-health", pack["next_up"]["name"])

    def test_parse_skill_list_skips_installed_chrome(self):
        names = parse_skill_list(
            "Installed skills\n"
            "Name\n"
            "----\n"
            "github\n"
            "web-search\n"
            "Installed\n"
        )
        self.assertEqual(names, ["github", "web-search"])

    def test_live_snapshot_names_the_chat(self):
        start("live-test-1", {"project_id": "saa-homes", "preset": "think", "title": "check rankings"})
        try:
            rows = snapshot()
            self.assertTrue(any(row["id"] == "live-test-1" and row["project_id"] == "saa-homes" for row in rows))
        finally:
            finish("live-test-1")
        self.assertFalse(any(row["id"] == "live-test-1" for row in snapshot()))

    def test_apply_cron_status_overlay_and_skip(self):
        from openbot.hermes import SAA_CRON_SKIP, apply_cron_status_overlay, saa_live_cron_run

        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            cron = home / "cron"
            cron.mkdir()
            (cron / "jobs.json").write_text(json.dumps({
                "jobs": [{
                    "id": "1172c8911e5d",
                    "name": "weekly-war-room",
                    "last_status": "error",
                    "last_error": "Gateway shutdown",
                    "prompt": "keep",
                }]
            }), encoding="utf-8")
            n = apply_cron_status_overlay(home, [{
                "id": "1172c8911e5d",
                "last_status": "ok",
                "last_error": None,
                "last_run_at": "2026-09-09T16:00:00+00:00",
            }])
            self.assertEqual(n, 1)
            jobs = json.loads((cron / "jobs.json").read_text(encoding="utf-8"))["jobs"]
            self.assertEqual(jobs[0]["last_status"], "ok")
            self.assertEqual(jobs[0]["prompt"], "keep")
        self.assertIn("7bdaa3b6fb9e", SAA_CRON_SKIP)
        skipped = saa_live_cron_run("7bdaa3b6fb9e")
        self.assertFalse(skipped["ok"])
        self.assertEqual(skipped["text"], "skipped")
        from openbot.hermes import SAA_CRON_PIN_GO, pin_saa_live_jobs_json, saa_ssh_payload
        payload = saa_ssh_payload(["python3", "-c", "import json; print(1)"])
        self.assertIn("python3", payload)
        self.assertIn("print(1)", payload)
        self.assertTrue("'" in payload)
        data = {
            "jobs": [
                {"id": "dadd8574d37f", "model": None, "provider": None, "deliver": "origin", "prompt": "keep"},
                {"id": "7cb2a72c1cc8", "model": "deepseek-v4-flash", "provider": "opencode-go", "deliver": "origin"},
            ]
        }
        changed = pin_saa_live_jobs_json(data)
        self.assertEqual(changed, ["dadd8574d37f"])
        self.assertEqual(data["jobs"][0]["model"], "deepseek-v4-flash")
        self.assertEqual(data["jobs"][0]["provider"], "opencode-go")
        self.assertEqual(data["jobs"][0]["deliver"], "origin")
        self.assertEqual(data["jobs"][0]["prompt"], "keep")
        self.assertIn("dadd8574d37f", SAA_CRON_PIN_GO)
        from openbot.hermes import nudge_saa_job_due, saa_catchup_next

        row = {
            "id": "38041c7a6501",
            "enabled": True,
            "state": "scheduled",
            "deliver": "origin",
            "prompt": "keep",
            "last_status": "error",
            "fire_claim": {"at": "x"},
        }
        blob = {"jobs": [row]}
        self.assertTrue(nudge_saa_job_due(blob, "38041c7a6501", "2026-09-09T20:00:00+00:00"))
        self.assertEqual(row["next_run_at"], "2026-09-09T20:00:00+00:00")
        self.assertIsNone(row["fire_claim"])
        self.assertEqual(row["deliver"], "origin")
        self.assertEqual(row["prompt"], "keep")
        self.assertFalse(nudge_saa_job_due(blob, "7bdaa3b6fb9e", "2026-09-09T20:00:00+00:00"))
        nxt = saa_catchup_next([{"id": "38041c7a6501", "last_status": "error", "state": "scheduled", "enabled": True}])
        self.assertEqual(nxt, "38041c7a6501")
        caught = saa_catchup_next([{"id": "38041c7a6501", "last_status": "ok", "state": "scheduled", "enabled": True}])
        self.assertEqual(caught, "77bfe1c9f7a1")


if __name__ == "__main__":
    unittest.main()
