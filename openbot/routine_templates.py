"""Routine templates: presets for common workflows."""

from __future__ import annotations


def get_routine_templates() -> list[dict]:
    """Return predefined routine templates for common workflows."""
    return [
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
        }
    ]


def get_template_by_id(template_id: str) -> dict | None:
    """Get a specific template by ID."""
    templates = get_routine_templates()
    for template in templates:
        if template["id"] == template_id:
            return template
    return None
