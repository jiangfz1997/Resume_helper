"""
Trigger local LangGraph Studio pipelines via the LangGraph SDK.

Usage:
    python scripts/trigger_studio.py --graph profile_parse
    python scripts/trigger_studio.py --graph v2_resume
    python scripts/trigger_studio.py --graph all

Prerequisites:
    pip install langgraph-sdk
    langgraph dev          # starts Studio at http://localhost:2024
"""

import argparse
import asyncio
import json
import uuid
from typing import Any

from langgraph_sdk import get_client

STUDIO_URL = "http://localhost:2024"

# ---------------------------------------------------------------------------
# Sample inputs
# ---------------------------------------------------------------------------

SAMPLE_RESUME_TEXT = """
John Doe
john.doe@email.com | github.com/johndoe | Vancouver, BC

SUMMARY
Backend engineer with 5 years of experience building distributed systems and APIs.

EXPERIENCE

Software Engineer
Acme Corp | Jan 2021 - Present
- Designed and implemented a distributed job queue using Redis and Python, reducing task latency by 60%.
- Led migration of monolithic service to microservices architecture, improving deploy frequency from monthly to daily.
- Built CI/CD pipelines with GitHub Actions and Docker, cutting release time by 40%.

Backend Developer
StartupXYZ | Jun 2019 - Dec 2020
- Developed REST APIs using FastAPI and PostgreSQL serving 50k daily active users.
- Implemented JWT authentication and RBAC permission system.
- Optimized slow SQL queries, reducing p99 response time from 2s to 180ms.

EDUCATION

Bachelor of Science in Computer Science
University of British Columbia | Sep 2015 - Apr 2019

PROJECTS

Distributed Task Scheduler
- Built a distributed cron scheduler in Go supporting 10k+ concurrent jobs with leader election via etcd.
- Designed fault-tolerant task retry logic with exponential backoff and dead-letter queues.
Tech: Go, etcd, PostgreSQL, Docker

SKILLS
Languages: Python, Go, TypeScript, SQL
Frameworks: FastAPI, Django, React
Infrastructure: Docker, Kubernetes, AWS, Terraform
Databases: PostgreSQL, Redis, MongoDB
"""

SAMPLE_V2_INPUT: dict[str, Any] = {
    "profile": {
        "user_id": str(uuid.uuid4()),
        "full_name": "John Doe",
        "summary": "Backend engineer with 5 years of experience building distributed systems.",
        "work_experiences": [
            {
                "company": "Acme Corp",
                "title": "Software Engineer",
                "start_date": "2021-01",
                "end_date": None,
                "description": [
                    "Designed a distributed job queue using Redis, reducing latency by 60%.",
                    "Led migration to microservices architecture.",
                ],
            }
        ],
        "educations": [
            {
                "institution": "University of British Columbia",
                "degree": "Bachelor of Science in Computer Science",
                "field_of_study": "Computer Science",
                "start_date": "2015-09",
                "end_date": "2019-04",
                "gpa": None,
            }
        ],
        "projects": [
            {
                "name": "Distributed Task Scheduler",
                "description": "Distributed cron scheduler in Go supporting 10k+ concurrent jobs.",
                "bullets": [
                    "Built with leader election via etcd.",
                    "Fault-tolerant retry logic with exponential backoff.",
                ],
                "tech_stack": ["Go", "etcd", "PostgreSQL", "Docker"],
                "url": None,
            }
        ],
        "skills": [
            {"category": "Languages", "name": "Python", "proficiency": "expert"},
            {"category": "Languages", "name": "Go", "proficiency": "intermediate"},
            {"category": "Infrastructure", "name": "Docker", "proficiency": "expert"},
        ],
        "base_resume": None,
    },
    "jd": {
        "title": "Senior Backend Engineer",
        "company": "TechCorp",
        "hard_requirements": ["Python", "distributed systems", "REST API", "PostgreSQL"],
        "core_keywords": ["microservices", "Docker", "Kubernetes", "CI/CD"],
        "soft_skills": ["ownership", "communication", "collaboration"],
        "preferred_qualifications": ["Go", "Kafka", "AWS"],
    },
    "matching_report": {
        "matched_skills": ["Python", "Docker", "PostgreSQL", "REST API", "microservices", "CI/CD"],
        "missing_skills": ["Kubernetes", "Kafka"],
        "highlighted_experiences": ["Acme Corp migration to microservices"],
        "relevance_notes": "Strong match on core backend skills. Missing container orchestration experience.",
    },
    "config": {
        "initial_threshold": 0.75,
        "decay_per_retry": 0.05,
        "min_threshold": 0.6,
        "max_retries": 3,
    },
    "tailored_draft": None,
    "feedback": None,
    "best_tailored_draft": None,
    "best_score": 0.0,
    "retry_count": 0,
    "current_threshold": 0.75,
    "status": "in_progress",
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_graph(graph_name: str, input_data: dict[str, Any]) -> None:
    client = get_client(url=STUDIO_URL)

    print(f"\n{'='*60}")
    print(f"Graph   : {graph_name}")
    print(f"Studio  : {STUDIO_URL}")
    print(f"{'='*60}\n")

    thread = await client.threads.create()
    thread_id: str = thread["thread_id"]
    print(f"Thread  : {thread_id}\n")

    async for chunk in client.runs.stream(
        thread_id,
        assistant_id=graph_name,
        input=input_data,
        stream_mode="events",
    ):
        event: str = chunk.event
        data: Any = chunk.data

        if event == "metadata":
            run_id = data.get("run_id", "")
            print(f"[run_id] {run_id}")
            print(f"  Studio URL: {STUDIO_URL}/threads/{thread_id}/runs/{run_id}\n")

        elif event == "events":
            name = data.get("name", "")
            kind = data.get("event", "")
            if kind in ("on_chain_start", "on_chain_end", "on_chain_error"):
                status = kind.split("_")[-1].upper()
                node = data.get("metadata", {}).get("langgraph_node", name)
                if node:
                    print(f"  [{status:5}] node={node}")
                    if kind == "on_chain_end" and "output" in data:
                        output_keys = list(data["output"].keys()) if isinstance(data["output"], dict) else []
                        if output_keys:
                            print(f"          output_keys={output_keys}")
                    elif kind == "on_chain_error":
                        print(f"          error={data.get('data', {}).get('error', '')}")

        elif event == "error":
            print(f"\n[ERROR] {json.dumps(data, indent=2)}")

        elif event == "end":
            print(f"\n[DONE] graph={graph_name} thread={thread_id}")


async def main(graphs: list[str]) -> None:
    inputs: dict[str, dict[str, Any]] = {
        "profile_parse": {"raw_text": SAMPLE_RESUME_TEXT, "draft": None},
        "v2_resume": SAMPLE_V2_INPUT,
    }

    for graph_name in graphs:
        if graph_name not in inputs:
            print(f"[SKIP] Unknown graph: {graph_name}. Available: {list(inputs)}")
            continue
        try:
            await run_graph(graph_name, inputs[graph_name])
        except Exception as exc:
            print(f"[ERROR] {graph_name}: {exc}")
            print("  Is 'langgraph dev' running?")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger LangGraph Studio pipelines")
    parser.add_argument(
        "--graph",
        default="all",
        choices=["profile_parse", "v2_resume", "all"],
        help="Which graph to trigger (default: all)",
    )
    args = parser.parse_args()

    target = list({"profile_parse": ["profile_parse"], "v2_resume": ["v2_resume"], "all": ["profile_parse", "v2_resume"]}[args.graph])
    asyncio.run(main(target))
