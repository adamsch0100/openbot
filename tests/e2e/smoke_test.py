#!/usr/bin/env python3
"""E2E smoke test against live Railway OpenBot.

Tests critical paths:
- Builder: create file + Accept diff
- Research: fetch public doc
- Ops: create/verify cron or equivalent ops path

Run against live: https://openbot-production-9334.up.railway.app
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin
from typing import Any

# HTTP client (stdlib only)
try:
    from http.client import HTTPSConnection
    from urllib.parse import urlparse
except ImportError:
    print("ERROR: Missing stdlib http.client or urllib.parse")
    sys.exit(1)


class OpenBotE2EClient:
    """Minimal HTTP client for OpenBot E2E tests."""

    def __init__(self, base_url: str, pin: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.pin = pin
        self.session_cookies = {}
        parsed = urlparse(base_url)
        self.host = parsed.netloc
        self.scheme = parsed.scheme
        self.conn = None

    def _connect(self):
        if self.conn is None:
            if self.scheme == "https":
                self.conn = HTTPSConnection(self.host, timeout=30)
            else:
                # For http, use HTTPConnection
                from http.client import HTTPConnection
                self.conn = HTTPConnection(self.host, timeout=30)

    def _request(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
        """Make HTTP request and return JSON response."""
        self._connect()
        
        full_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            full_headers.update(headers)
        
        # Add cookies if we have them
        if self.session_cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self.session_cookies.items())
            full_headers["Cookie"] = cookie_str

        body_bytes = json.dumps(body).encode("utf-8") if body else None
        
        try:
            self.conn.request(method, path, body=body_bytes, headers=full_headers)
            response = self.conn.getresponse()
            response_data = response.read()
            
            # Parse Set-Cookie headers
            for header_name, header_value in response.getheaders():
                if header_name.lower() == "set-cookie":
                    # Simple cookie parsing (name=value)
                    cookie_parts = header_value.split(";")[0].strip()
                    if "=" in cookie_parts:
                        name, value = cookie_parts.split("=", 1)
                        self.session_cookies[name] = value
            
            if response.status >= 400:
                print(f"HTTP {response.status} for {method} {path}")
                print(f"Response: {response_data.decode('utf-8', errors='replace')[:500]}")
                return {"error": f"HTTP {response.status}", "status": response.status}
            
            if response_data:
                return json.loads(response_data.decode("utf-8"))
            return {}
        except Exception as e:
            print(f"Request failed: {e}")
            return {"error": str(e)}

    def unlock(self) -> bool:
        """Unlock board with PIN (if required).
        
        Success if ANY of:
        - Set-Cookie openbot_unlock captured, OR
        - Body has token (also set as cookie), OR
        - needs_unlock is False, OR
        - unlocked is true, OR
        - HTTP 200 with work_dir and no error
        
        Master server.py auth: Cookie openbot_unlock only.
        Token from Set-Cookie or JSON body → store as session cookie.
        """
        if not self.pin:
            print("WARN: No PIN provided, skipping unlock")
            return True
        
        result = self._request("POST", "/api/unlock", {"pin": self.pin})
        
        # Check for error response
        if result.get("error") or result.get("status", 200) >= 400:
            print(f"✗ Unlock failed: {result}")
            return False
        
        # Success criteria (CoS confirmed)
        unlocked = result.get("unlocked")
        token = result.get("token")
        needs_unlock = result.get("needs_unlock")
        work_dir = result.get("work_dir")
        has_cookie = "openbot_unlock" in self.session_cookies
        
        success = (
            has_cookie  # Set-Cookie captured
            or (isinstance(token, str) and token)  # Body token
            or needs_unlock is False
            or unlocked is True
            or (work_dir and not result.get("error"))  # HTTP 200 config
        )
        
        if success:
            print("✓ Board unlocked")
            # Store token if present in body (also as cookie for auth)
            if isinstance(token, str) and token:
                self.session_cookies["openbot_unlock"] = token
            return True
        else:
            print(f"✗ Unlock failed: {result}")
            return False

    def get_status(self) -> dict:
        """Get board status (health check).
        
        Uses /api/health or /api/config (NOT /api/status - 404 when unlocked on master).
        """
        # Try health endpoint first
        result = self._request("GET", "/api/health")
        if not result.get("error") and result.get("status", 200) < 400:
            return result
        
        # Fallback to config endpoint (not status - no handler on master when unlocked)
        return self._request("GET", "/api/config")

    def send_message(self, message: str, seat: str = "cos", project: str = "openbot") -> dict:
        """Send message to OpenBot and get job ID.
        
        Uses 'preset' parameter (server naming), returns job['id'].
        """
        return self._request("POST", "/api/chat", {
            "message": message,
            "preset": seat,  # Server uses 'preset' not 'seat'
            "project_id": project,
        })

    def get_job(self, job_id: str) -> dict:
        """Get job details."""
        return self._request("GET", f"/api/jobs/{job_id}")

    def accept_diff(self, job_id: str) -> dict:
        """Accept a diff."""
        return self._request("POST", f"/api/jobs/{job_id}/accept")

    def reject_diff(self, job_id: str) -> dict:
        """Reject a diff."""
        return self._request("POST", f"/api/jobs/{job_id}/reject")

    def list_jobs(self, project: str = "openbot") -> list[dict]:
        """List jobs for a project."""
        result = self._request("GET", f"/api/jobs?project={project}")
        return result.get("jobs", [])

    def get_routines(self, project: str = "openbot") -> list[dict]:
        """Get routines for a project."""
        result = self._request("GET", f"/api/routines?project_id={project}")
        return result.get("routines", [])
    
    def create_routine(self, name: str, schedule: str, steps: list, project: str = "openbot", enabled: bool = True) -> dict:
        """Create a new routine (cron).
        
        POST /api/routines with name, schedule, steps.
        """
        return self._request("POST", "/api/routines", {
            "name": name,
            "schedule": schedule,
            "steps": steps,
            "project_id": project,
            "enabled": enabled,
        })


class E2ETestRunner:
    """Run E2E smoke tests against live OpenBot."""

    def __init__(self, base_url: str, pin: str | None = None, evidence_dir: Path | None = None):
        self.client = OpenBotE2EClient(base_url, pin)
        self.base_url = base_url
        self.evidence_dir = evidence_dir or Path("tests/e2e/evidence")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.results = []
        self.run_id = uuid.uuid4().hex[:8]

    def log(self, message: str):
        """Log to console and evidence."""
        print(message)
        log_file = self.evidence_dir / f"run_{self.run_id}.log"
        with open(log_file, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")

    def record_result(self, test_name: str, passed: bool, details: str = ""):
        """Record test result."""
        result = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": time.time(),
        }
        self.results.append(result)
        status = "✅ PASS" if passed else "❌ FAIL"
        self.log(f"{status}: {test_name}")
        if details:
            self.log(f"  → {details}")

    def save_evidence(self):
        """Save test evidence to JSON."""
        evidence_file = self.evidence_dir / f"run_{self.run_id}.json"
        evidence = {
            "run_id": self.run_id,
            "base_url": self.base_url,
            "timestamp": time.time(),
            "results": self.results,
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r["passed"]),
                "failed": sum(1 for r in self.results if not r["passed"]),
            }
        }
        with open(evidence_file, "w") as f:
            json.dump(evidence, f, indent=2)
        self.log(f"Evidence saved: {evidence_file}")
        return evidence

    def wait_for_job(self, job_id: str, timeout: int = 120) -> dict | None:
        """Wait for job to complete (or timeout)."""
        start = time.time()
        while time.time() - start < timeout:
            job = self.client.get_job(job_id)
            if job.get("error"):
                self.log(f"  Job lookup error: {job['error']}")
                return None
            
            status = job.get("status", "")
            if status in ("completed", "failed", "rejected"):
                return job
            
            time.sleep(2)
        
        self.log(f"  Job {job_id} timed out after {timeout}s")
        return None

    def test_health_check(self) -> bool:
        """Test 1: Health check / status endpoint."""
        self.log("\n=== Test 1: Health Check ===")
        status = self.client.get_status()
        
        if status.get("error"):
            self.record_result("health_check", False, f"Status check failed: {status.get('error')}")
            return False
        
        # Check if we got a valid response
        has_version = "version" in status or "status" in status or "ok" in status
        if has_version or status:
            self.record_result("health_check", True, f"Status: {status}")
            return True
        else:
            self.record_result("health_check", False, "Empty status response")
            return False

    def test_builder_flow(self) -> bool:
        """Test 2: Builder flow (create file + Accept)."""
        self.log("\n=== Test 2: Builder Flow ===")
        
        # Send message to Builder
        test_file = f"e2e_test_{self.run_id}.txt"
        message = f"Create a file called {test_file} with content: E2E test from {self.run_id}"
        
        self.log(f"  Sending message to Builder: {message[:80]}...")
        response = self.client.send_message(message, seat="builder", project="openbot")
        
        if response.get("error"):
            self.record_result("builder_flow", False, f"Message send failed: {response.get('error')}")
            return False
        
        # Job ID is in 'id' field, not 'job_id'
        job_id = response.get("id") or response.get("job_id")
        if not job_id:
            self.record_result("builder_flow", False, "No job id in response")
            return False
        
        self.log(f"  Job created: {job_id}")
        
        # Wait for job to complete
        self.log(f"  Waiting for job to complete...")
        job = self.wait_for_job(job_id, timeout=180)
        
        if not job:
            self.record_result("builder_flow", False, "Job did not complete in time")
            return False
        
        # Check if diff is ready
        has_diff = job.get("has_diff") or job.get("diff")
        if not has_diff:
            self.record_result("builder_flow", False, f"No diff in job (status: {job.get('status')})")
            return False
        
        self.log(f"  Diff ready, attempting Accept...")
        
        # Accept the diff
        accept_result = self.client.accept_diff(job_id)
        if accept_result.get("error"):
            self.record_result("builder_flow", False, f"Accept failed: {accept_result.get('error')}")
            return False
        
        if accept_result.get("accepted") or accept_result.get("ok"):
            self.record_result("builder_flow", True, f"File created and accepted: {test_file}")
            return True
        else:
            self.record_result("builder_flow", False, f"Accept response unclear: {accept_result}")
            return False

    def test_research_flow(self) -> bool:
        """Test 3: Research flow (fetch public doc)."""
        self.log("\n=== Test 3: Research Flow ===")
        
        # Send message to Research
        message = "Fetch and summarize the README from https://github.com/adamsch0100/openbot"
        
        self.log(f"  Sending message to Research: {message[:80]}...")
        response = self.client.send_message(message, seat="research", project="openbot")
        
        if response.get("error"):
            self.record_result("research_flow", False, f"Message send failed: {response.get('error')}")
            return False
        
        # Job ID is in 'id' field, not 'job_id'
        job_id = response.get("id") or response.get("job_id")
        if not job_id:
            self.record_result("research_flow", False, "No job id in response")
            return False
        
        self.log(f"  Job created: {job_id}")
        
        # Wait for job to complete
        self.log(f"  Waiting for job to complete...")
        job = self.wait_for_job(job_id, timeout=180)
        
        if not job:
            self.record_result("research_flow", False, "Job did not complete in time")
            return False
        
        status = job.get("status")
        if status == "completed":
            # Check if we got output
            result = job.get("result", "")
            if result and len(result) > 50:
                self.record_result("research_flow", True, f"Doc fetched (result: {len(result)} chars)")
                return True
            else:
                self.record_result("research_flow", False, f"Job completed but result too short: {result[:100]}")
                return False
        else:
            self.record_result("research_flow", False, f"Job status: {status}")
            return False

    def test_ops_flow(self) -> bool:
        """Test 4: Ops flow (create cron via POST /api/routines).
        
        Must exercise POST /api/routines (create + attach cron), not just GET.
        """
        self.log("\n=== Test 4: Ops Flow (Create Routine) ===")
        
        # Create a test routine via POST
        routine_name = f"e2e_test_routine_{self.run_id}"
        schedule = "0 0 * * 0"  # Weekly on Sunday
        steps = [
            {
                "instruction": "Check project status and report any issues",
                "preset": "cos",
            }
        ]
        
        self.log(f"  Creating routine: {routine_name}")
        result = self.client.create_routine(routine_name, schedule, steps, project="openbot", enabled=False)
        
        # Check for 404 (missing routines endpoint on prod)
        if result.get("status") == 404:
            self.record_result("ops_flow", False, "POST /api/routines returned 404 - production missing routines endpoint")
            return False
        
        if result.get("error"):
            self.record_result("ops_flow", False, f"Routine creation failed: {result.get('error')}")
            return False
        
        routine_id = result.get("routine_id")
        if not routine_id:
            self.record_result("ops_flow", False, f"No routine_id in response: {result}")
            return False
        
        self.log(f"  Routine created: {routine_id}")
        
        # Verify we can list routines and see ours
        self.log(f"  Verifying routine via GET...")
        routines = self.client.get_routines("openbot")
        
        if not isinstance(routines, list):
            self.record_result("ops_flow", False, f"Failed to list routines: {routines}")
            return False
        
        found = any(r.get("id") == routine_id or r.get("name") == routine_name for r in routines)
        if not found:
            self.record_result("ops_flow", False, f"Created routine not found in list")
            return False
        
        self.record_result("ops_flow", True, f"Routine created and verified: {routine_id}")
        return True

    def run_all_tests(self) -> dict:
        """Run all E2E smoke tests."""
        self.log(f"=== OpenBot E2E Smoke Test ===")
        self.log(f"Run ID: {self.run_id}")
        self.log(f"Target: {self.base_url}")
        self.log(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
        
        # Unlock board if PIN provided
        if self.client.pin:
            if not self.client.unlock():
                self.log("FATAL: Board unlock failed, aborting tests")
                return self.save_evidence()
        
        # Run tests
        self.test_health_check()
        self.test_builder_flow()
        self.test_research_flow()
        self.test_ops_flow()
        
        # Save evidence
        evidence = self.save_evidence()
        
        # Print summary
        self.log("\n=== Test Summary ===")
        self.log(f"Total: {evidence['summary']['total']}")
        self.log(f"Passed: {evidence['summary']['passed']}")
        self.log(f"Failed: {evidence['summary']['failed']}")
        
        all_passed = evidence['summary']['failed'] == 0
        self.log(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
        
        return evidence


def main():
    """Run E2E smoke test from command line."""
    # Check for PIN in env or args
    pin = os.environ.get("OPENBOT_PIN")
    base_url = os.environ.get("OPENBOT_URL", "https://openbot-production-9334.up.railway.app")
    
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    if len(sys.argv) > 2:
        pin = sys.argv[2]
    
    print(f"OpenBot E2E Smoke Test")
    print(f"Target: {base_url}")
    print(f"PIN: {'<provided>' if pin else '<not provided>'}")
    print()
    
    runner = E2ETestRunner(base_url, pin)
    evidence = runner.run_all_tests()
    
    # Exit with failure code if any tests failed
    if evidence['summary']['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
