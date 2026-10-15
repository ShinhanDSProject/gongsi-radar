"""InMemory Job Store. AI 서버를 재기동하면 사라진다 — 리포트 정본은 Spring이 analysis_report에 저장한다."""
import uuid
from typing import Dict, Any
from ..schemas.analysis import JobStatus


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobStatus] = {}

    def create(self) -> JobStatus:
        job_id = str(uuid.uuid4())
        job = JobStatus(jobId=job_id, status="RUNNING", progress=0.0,
                        currentStep="INITIALIZING")
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs: Any) -> None:
        job = self._jobs[job_id]
        for k, v in kwargs.items():
            setattr(job, k, v)


job_store = JobStore()

