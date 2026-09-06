"""Routine templates: presets for common workflows."""

from __future__ import annotations


def expand_self_build_instruction() -> str:
    """Generate dynamic instruction for self-build routine based on next ROADMAP item."""
    from .roadmap import next_roadmap_item, roadmap_instruction
    
    item = next_roadmap_item()
    if not item:
        return "No unshipped ROADMAP items found. Check docs/ROADMAP.md to add next work item."
    
    return roadmap_instruction(item)


def get_routine_templates() -> list[dict]:
    """Return predefined routine templates for common workflows."""
    return [
        {
            "id": "self-build",
            "name": "Weekly Self-Build",
            "description": "OpenBot implements next ROADMAP item and opens PR (dogfooding)",
            "schedule": "every Monday at 10am",
            "steps": [
                {
                    "seat": "builder",
                    "instruction": "SELF_BUILD_PLACEHOLDER"
                },
                {
                    "seat": "think",
                    "instruction": "Review the diff for correctness: check that changes follow AGENTS.md and OPENBOT.md, verify no secrets in files, confirm tests exist, ensure documentation is updated"
                },
                {
                    "seat": "ops",
                    "instruction": "Open a PR with the title from ROADMAP item and body including acceptance checklist. Use gh CLI: gh pr create --title '[TITLE]' --body '[BODY]' --draft"
                }
            ]
        },
        {
            "id": "morning-standup",
            "name": "Morning Standup",
            "description": "Daily status check and planning",
            "schedule": "every morning at 8am",
            "steps": [
                {
                    "seat": "builder",
                    "instruction": "Check git status in the project folder and list uncommitted changes"
                },
                {
                    "seat": "think",
                    "instruction": "Summarize the current project status from INDEX and identify any blockers"
                },
                {
                    "seat": "ops",
                    "instruction": "Post a brief standup note to INDEX with today's priorities"
                }
            ]
        },
        {
            "id": "weekly-review",
            "name": "Weekly Review",
            "description": "Review progress and update documentation",
            "schedule": "every Friday at 5pm",
            "steps": [
                {
                    "seat": "think",
                    "instruction": "List all completed work from the last 7 days based on job history and INDEX updates"
                },
                {
                    "seat": "research",
                    "instruction": "Fetch the project changelog or recent PR descriptions from the repository"
                },
                {
                    "seat": "ops",
                    "instruction": "Create a weekly summary note with accomplishments and next week priorities"
                }
            ]
        },
        {
            "id": "pre-deploy-check",
            "name": "Pre-Deploy Checklist",
            "description": "Validation before deployment",
            "schedule": "manual",
            "steps": [
                {
                    "seat": "builder",
                    "instruction": "Run the test suite and lint checks for the current branch"
                },
                {
                    "seat": "think",
                    "instruction": "Review test results and check for any critical warnings or failures"
                },
                {
                    "seat": "research",
                    "instruction": "Check if there are any open deployment blockers in GitHub issues"
                },
                {
                    "seat": "ops",
                    "instruction": "Post pre-deploy validation summary to INDEX"
                }
            ]
        },
        {
            "id": "documentation-sync",
            "name": "Documentation Sync",
            "description": "Keep docs in sync with code changes",
            "schedule": "every Monday and Thursday at 2pm",
            "steps": [
                {
                    "seat": "builder",
                    "instruction": "List files changed in the last 3 days and identify which need documentation updates"
                },
                {
                    "seat": "think",
                    "instruction": "Analyze code changes and suggest documentation updates needed"
                },
                {
                    "seat": "ops",
                    "instruction": "Create documentation update tasks in INDEX"
                }
            ]
        },
        {
            "id": "dependency-audit",
            "name": "Dependency Audit",
            "description": "Check for outdated dependencies",
            "schedule": "every Monday at 9am",
            "steps": [
                {
                    "seat": "builder",
                    "instruction": "Check package.json or requirements.txt for outdated dependencies"
                },
                {
                    "seat": "research",
                    "instruction": "Look up any security advisories for current dependencies"
                },
                {
                    "seat": "ops",
                    "instruction": "Post dependency update recommendations to INDEX"
                }
            ]
        },
        {
            "id": "e2e-regression",
            "name": "E2E Regression Suite",
            "description": "Weekly E2E smoke test against live Railway OpenBot",
            "schedule": "every Sunday at 11pm",
            "steps": [
                {
                    "seat": "ops",
                    "instruction": "Run E2E smoke test against Railway: python3 tests/e2e/smoke_test.py https://openbot-production-9334.up.railway.app"
                },
                {
                    "seat": "think",
                    "instruction": "Review E2E test results and identify any failures or regressions"
                },
                {
                    "seat": "ops",
                    "instruction": "Post E2E regression results to activity feed: passed/failed counts, any blockers"
                }
            ]
        }
    ]


def get_template_by_id(template_id: str) -> dict | None:
    """Get a specific template by ID."""
    templates = get_routine_templates()
    for template in templates:
        if template["id"] == template_id:
            # Expand self-build instruction dynamically
            if template_id == "self-build":
                expanded = dict(template)
                expanded["steps"] = [dict(step) for step in template["steps"]]
                for step in expanded["steps"]:
                    if step.get("instruction") == "SELF_BUILD_PLACEHOLDER":
                        step["instruction"] = expand_self_build_instruction()
                return expanded
            return template
    return None
